from types import SimpleNamespace
import pytest
from scripts import check_dependencies as deps

ERROR = '\n'.join(f'{name} {version} is not supported on this platform' for name, version in [
    ('PyYAML', '6.0.3'), ('cffi', '2.1.1'), ('tibs', '0.5.7'), ('bitarray', '3.11.0'), ('cryptography', '50.0.2')])


def fake(monkeypatch, responses):
    calls = []
    def pip(*args):
        calls.append(args)
        code, output = responses.pop(0)
        return SimpleNamespace(returncode=code, stdout=output)
    monkeypatch.setattr(deps, 'pip', pip)
    return calls


def test_all_reported_packages_repaired(monkeypatch):
    calls = fake(monkeypatch, [(1, ERROR)] + [(0, '')] * 6)
    deps.check()
    assert len([c for c in calls if c[0] == 'install']) == 5
    assert calls[-1] == ('check',)
    assert calls[1][-1] == 'PyYAML==6.0.3'
    assert '--only-binary=:all:' in calls[1]


def test_missing_wheel_falls_back_to_source(monkeypatch):
    monkeypatch.setattr(deps, 'build_tools', lambda packages, install=False: None)
    error = 'cffi 2.1.1 is not supported on this platform'
    calls = fake(monkeypatch, [(1, error), (1, 'No wheel'), (1, error), (0, ''), (0, '')])
    deps.check()
    assert '--no-binary=cffi' in calls[-2]


def test_real_dependency_conflicts_still_fail(monkeypatch):
    calls = fake(monkeypatch, [(1, 'example requires something, which is not installed')])
    with pytest.raises(RuntimeError, match='no unsupported'):
        deps.check()
    assert calls == [('check',)]


def test_repair_cannot_mask_other_conflict(monkeypatch):
    fake(monkeypatch, [(1, 'cffi 2.1.1 is not supported on this platform'), (0, ''), (1, 'Missing dependency'), (1, 'Missing dependency')])
    with pytest.raises(RuntimeError, match='still fails'):
        deps.check()


def test_reject_argument_injection():
    assert deps.unsupported('--evil 1 is not supported on this platform') == []
    assert deps.unsupported('name 1;touch is not supported on this platform') == []


def test_build_tools_only_requested_for_source_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(deps, 'build_tools', lambda packages, install=False: calls.append((packages, install)))
    error = 'cffi 2.1.1 is not supported on this platform'
    fake(monkeypatch, [(1, error), (0, ''), (0, '')])
    deps.check(install_build_tools=True)
    assert calls == []
    fake(monkeypatch, [(1, error), (1, ''), (1, error), (0, ''), (0, '')])
    deps.check(install_build_tools=True)
    assert calls == [([('cffi', '2.1.1')], True)]


def test_rust_only_for_crypto_and_no_sudo_without_opt_in(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout='')
    monkeypatch.setattr(deps.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='Pi terminal'):
        deps.build_tools([('cffi', '2.1.1')])
    assert all(c[0] == 'dpkg-query' for c in calls)
    assert not any('rustc' in c for c in calls)
    calls.clear()
    deps.build_tools([('cryptography', '50.0.2')], install=True)
    assert 'rustc' in calls[-1] and 'cargo' in calls[-1]
    assert calls[-1][:2] == ['sudo', 'apt-get']


def test_verified_metadata_skips_all_reinstallation(monkeypatch):
    monkeypatch.setattr(deps, 'verified_piwheels', lambda name, version: True)
    calls = fake(monkeypatch, [(1, ERROR)])
    deps.check()
    assert calls == [('check',)]


def test_verified_metadata_does_not_hide_conflicts(monkeypatch):
    monkeypatch.setattr(deps, 'verified_piwheels', lambda name, version: True)
    fake(monkeypatch, [(1, ERROR + '\nfoo requires bar, which is not installed.')])
    with pytest.raises(RuntimeError):
        deps.check()


def test_native_exception_checks_version_platform_abi_and_execution(monkeypatch):
    monkeypatch.setattr(deps, 'is_pi_zero', lambda: True)
    monkeypatch.setattr(deps, 'supported_tags', lambda: {'cp313-cp313-linux_armv6l'})
    wheel = SimpleNamespace(version='6.0.3', read_text=lambda _: 'Tag: cp313-cp313-linux_armv7l\n')
    monkeypatch.setattr(deps, 'distribution', lambda _: wheel)
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='')
    monkeypatch.setattr(deps.subprocess, 'run', run)
    assert deps.verified_piwheels('PyYAML', '6.0.3')
    assert len(calls) == 1
    assert not deps.verified_piwheels('PyYAML', '6.0.4')
    assert not deps.verified_piwheels('unknown', '6.0.3')
    monkeypatch.setattr(deps, 'supported_tags', lambda: {'cp312-cp312-linux_armv6l'})
    assert not deps.verified_piwheels('PyYAML', '6.0.3')
    monkeypatch.setattr(deps, 'is_pi_zero', lambda: False)
    assert not deps.verified_piwheels('PyYAML', '6.0.3')
    assert len(calls) == 1


def test_native_failure_is_not_ignored_or_rebuilt(monkeypatch):
    monkeypatch.setattr(deps, 'is_pi_zero', lambda: True)
    monkeypatch.setattr(deps, 'supported_tags', lambda: {'cp313-cp313-linux_armv6l'})
    monkeypatch.setattr(deps, 'distribution', lambda _: SimpleNamespace(version='6.0.3', read_text=lambda _: 'Tag: cp313-cp313-linux_armv7l\n'))
    monkeypatch.setattr(deps.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=-4, stdout='Illegal instruction'))
    calls = fake(monkeypatch, [(1, 'PyYAML 6.0.3 is not supported on this platform')])
    with pytest.raises(RuntimeError, match='NOT accepted'):
        deps.check()
    assert calls == [('check',)]


@pytest.mark.parametrize('native', [False, True])
def test_yaml_probe_supports_optional_c_extension(monkeypatch, native):
    import sys
    safe, accelerated = object(), object()
    used = []
    module = SimpleNamespace(SafeLoader=safe, safe_load=lambda text: {'test': True})
    def load(text, Loader):
        used.append(Loader)
        return {'test': True}
    module.load = load
    if native:
        module.CSafeLoader = accelerated
    monkeypatch.setitem(sys.modules, 'yaml', module)
    exec(deps.PIWHEELS_CHECKS['pyyaml'][1], {})
    assert used == [accelerated if native else safe]


def test_yaml_probe_still_rejects_wrong_result(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'yaml', SimpleNamespace(safe_load=lambda text: None))
    with pytest.raises(AssertionError):
        exec(deps.PIWHEELS_CHECKS['pyyaml'][1], {})
