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
