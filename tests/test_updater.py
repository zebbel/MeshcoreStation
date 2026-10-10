import json
from pathlib import Path
import subprocess
import pytest
from flask import Flask
from meshcorestation import updater as u
from meshcorestation.web.update_api import register_update_routes


@pytest.fixture
def area(tmp_path, monkeypatch):
    monkeypatch.setattr(u, 'ROOT', tmp_path)
    monkeypatch.setattr(u, 'STATE', tmp_path / '.updates')
    monkeypatch.setattr(u, 'ready', lambda: True)
    return tmp_path


def test_lock_rejects_concurrency(area):
    with u.lock():
        with pytest.raises(RuntimeError, match='already running'):
            with u.lock():
                pass


def test_queue_requires_checked_commit_and_clean_source(area, monkeypatch):
    monkeypatch.setattr(u, 'validate_checkout', lambda: None)
    monkeypatch.setattr(u, 'local_revision', lambda: 'a'*40)
    u.write('check.json', {'latest': 'b'*40, 'current': 'a'*40, 'available': True})
    with pytest.raises(RuntimeError, match='Check for updates'):
        u.queue('c'*40)
    u.queue('b'*40)
    assert u.read('request.json')['target'] == 'b'*40
    with pytest.raises(RuntimeError, match='already'):
        u.queue('b'*40)


def test_api_origin_and_bad_actions(area, monkeypatch):
    monkeypatch.setattr(u, 'local_revision', lambda: 'a'*40)
    app = Flask(__name__)
    register_update_routes(app)
    client = app.test_client()
    assert client.get('/api/update').status_code == 403
    headers = {'X-Meshcore-Control': '1'}
    assert client.get('/api/update', headers=headers).json['ok']
    assert client.post('/api/update', headers={**headers, 'Origin': 'https://evil.example'}, json={'action': 'install'}).status_code == 403
    assert client.post('/api/update', headers=headers, json={'action':'bad'}).status_code == 400
    assert client.get('/api/update/health').json['revision'] == 'a'*40


@pytest.mark.parametrize('fail_at', ['none', 'pip', 'health', 'backup'])
def test_worker_success_and_rollback(area, monkeypatch, fail_at):
    from meshcorestation import config
    data = area / 'data'; data.mkdir(); (data / 'db').write_text('original data')
    venv = area / '.venv'; venv.mkdir(); (venv / 'package').write_text('old dependency')
    (area / 'meshcorestation.env').write_text('original settings')
    monkeypatch.setattr(config, 'DATA_DIR', data)
    monkeypatch.setattr(config, 'PORT', 8080)
    monkeypatch.setattr(u, 'validate_checkout', lambda: None)
    monkeypatch.setattr(u, 'local_revision', lambda: 'a'*40)
    monkeypatch.setattr(u, 'prepare_dependencies', lambda *a: area/'wheels')
    services, resets = [], []
    monkeypatch.setattr(u, 'service', services.append)
    def run(*args, **kwargs):
        if args[:3] == ('git','reset','--hard'):
            resets.append(args[-1])
        if 'install' in args:
            (venv / 'package').write_text('new dependency')
            if fail_at == 'pip': raise RuntimeError('pip failed')
        return ''
    monkeypatch.setattr(u, 'run', run)
    def health(target, port):
        if target == 'b'*40:
            (data / 'db').write_text('migrated data')
            if fail_at == 'health': raise RuntimeError('health failed')
    monkeypatch.setattr(u, 'healthy', health)
    if fail_at == 'backup':
        monkeypatch.setattr(u.shutil, 'copytree', lambda *a, **k: (_ for _ in ()).throw(OSError('disk full')))
    u.write('request.json', {'current':'a'*40, 'target':'b'*40})
    u.worker()
    result = u.read('status.json')
    assert not u.read('transaction.json')
    if fail_at == 'none':
        assert result['phase'] == 'complete'
        assert (data/'db').read_text() == 'migrated data'
        assert (Path(result['backup'])/'data/db').read_text() == 'original data'
    else:
        assert result['phase'] == 'failed'
        assert 'restored' in result['message']
        assert (data/'db').read_text() == 'original data'
        assert (venv/'package').read_text() == 'old dependency'
        assert resets == ([] if fail_at == 'backup' else ['b'*40, 'a'*40])
    assert services[-1] == 'start'
    assert (area/'meshcorestation.env').read_text() == 'original settings'


def test_real_git_check_and_dirty_refusal(area, monkeypatch):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=area, text=True).strip()
    git('init','-b','main'); git('config','user.email','test@example.test'); git('config','user.name','Test')
    (area/'.gitignore').write_text('.updates/\n')
    package = area/'meshcorestation'; package.mkdir(); (package/'__init__.py').write_text('__version__ = "2.1.0"')
    git('add','.'); git('commit','-m','initial'); git('remote','add','origin', u.REMOTE)
    real = u.run
    def run(*args, **kwargs):
        if args[:2] == ('git','fetch'):
            (area/'.git/FETCH_HEAD').write_text(git('rev-parse','HEAD')+'\n')
            return ''
        return real(*args, **kwargs)
    monkeypatch.setattr(u,'run',run)
    result = u.check()
    assert not result['available'] and result['latest_version']=='2.1.0'
    (package/'__init__.py').write_text('local edit')
    with pytest.raises(RuntimeError, match='Local source changes'):
        u.check()


def test_interrupted_update_recovers(area, monkeypatch):
    data = area/'data'; data.mkdir(); (data/'db').write_text('new')
    venv = area/'.venv'; venv.mkdir(); (venv/'pkg').write_text('new')
    backup = area/'.updates/backup'; (backup/'data').mkdir(parents=True); (backup/'venv').mkdir()
    (backup/'data/db').write_text('old'); (backup/'venv/pkg').write_text('old')
    (backup/'meshcorestation.env').write_text('settings')
    monkeypatch.setattr(u,'run',lambda *a,**k:'')
    monkeypatch.setattr(u,'service',lambda action:None)
    monkeypatch.setattr(u,'healthy',lambda *a:None)
    u.write('transaction.json', {'old':'a'*40,'target':'b'*40,'backup':str(backup),'data':str(data),'port':80,'backup_complete':True})
    u.worker()
    assert (data/'db').read_text()=='old'
    assert not u.read('transaction.json')
    assert 'rolled back' in u.read('status.json')['message']


def test_unavailable_worker_and_changed_revision_refuse_install(area, monkeypatch):
    u.write('check.json', {'latest':'b'*40,'current':'a'*40,'available':True})
    monkeypatch.setattr(u,'ready',lambda:False)
    with pytest.raises(RuntimeError, match='one-time'):
        u.queue('b'*40)
    monkeypatch.setattr(u,'ready',lambda:True)
    monkeypatch.setattr(u,'validate_checkout',lambda:None)
    monkeypatch.setattr(u,'local_revision',lambda:'c'*40)
    with pytest.raises(RuntimeError,match='installed code changed'):
        u.queue('b'*40)
    assert not (u.STATE/'request.json').exists()


def test_health_requires_consecutive_correct_replies(monkeypatch):
    from io import StringIO
    responses = iter(['new', 'old', 'new', 'new', 'new'])
    seen = []
    def response(*a, **k):
        revision = next(responses); seen.append(revision)
        return StringIO(json.dumps({'revision':revision}))
    monkeypatch.setattr(u.urllib.request,'urlopen',response)
    monkeypatch.setattr(u.time,'sleep',lambda seconds:None)
    u.healthy('new',80)
    assert len(seen)==5


def test_dependency_preparation_fast_path_and_binary_download(area, monkeypatch):
    calls=[]
    def run(*args,**kwargs):
        calls.append(args)
        if args[:2]==('git','show'):return 'dash==3.4.0'
        return ''
    monkeypatch.setattr(u,'run',run)
    assert u.prepare_dependencies('a','b') is None
    assert any('--check-only' in c for c in calls)
    assert not any('download' in c or 'install' in c for c in calls)
    calls.clear()
    def changed(*args,**kwargs):
        calls.append(args)
        if args[:2]==('git','show'):return 'dash=='+('3.4.0' if args[2].startswith('a:') else '3.5.0')
        return ''
    monkeypatch.setattr(u,'run',changed)
    wheels=u.prepare_dependencies('a','b')
    assert (wheels/'requirements.txt').read_text().strip()=='dash==3.5.0'
    assert any('download' in c and '--only-binary=:all:' in c for c in calls)
    assert not any('install' in c for c in calls)


def test_missing_wheels_does_not_stop_station(area,monkeypatch):
    monkeypatch.setattr(u,'validate_checkout',lambda:None)
    monkeypatch.setattr(u,'local_revision',lambda:'a'*40)
    services=[]
    monkeypatch.setattr(u,'service',services.append)
    def run(*args,**kwargs):
        if args[:2]==('git','show'):return args[2]
        if 'download' in args:raise RuntimeError('No matching distribution')
        return ''
    monkeypatch.setattr(u,'run',run)
    u.write('request.json',{'current':'a'*40,'target':'b'*40})
    u.worker()
    assert not services
    assert 'not stopped' in u.read('status.json')['message']


@pytest.mark.parametrize('failure',[False,True])
def test_fast_update_never_copies_or_restores_venv(area,monkeypatch,failure):
    from meshcorestation import config
    data=area/'data';data.mkdir();(data/'db').write_text('old')
    venv=area/'.venv';venv.mkdir();(venv/'pkg').write_text('untouched')
    (area/'meshcorestation.env').write_text('settings')
    monkeypatch.setattr(config,'DATA_DIR',data);monkeypatch.setattr(config,'PORT',80)
    monkeypatch.setattr(u,'validate_checkout',lambda:None)
    monkeypatch.setattr(u,'local_revision',lambda:'a'*40)
    monkeypatch.setattr(u,'prepare_dependencies',lambda *a:None)
    monkeypatch.setattr(u,'service',lambda action:None)
    calls=[]
    monkeypatch.setattr(u,'run',lambda *a,**k:calls.append(a) or '')
    def health(target,port):
        if target=='b'*40:
            (data/'db').write_text('new')
            if failure:raise RuntimeError('unhealthy')
    monkeypatch.setattr(u,'healthy',health)
    u.write('request.json',{'current':'a'*40,'target':'b'*40})
    u.worker()
    status=u.read('status.json')
    assert status['phase']==('failed' if failure else 'complete')
    assert not (Path(status['backup'])/'venv').exists()
    assert (venv/'pkg').read_text()=='untouched'
    assert (data/'db').read_text()==('old' if failure else 'new')
    assert not any('pip' in c for c in calls)


def test_streaming_output_and_timeout(area,monkeypatch):
    import sys
    chunks=[]
    monkeypatch.setattr(u,'_progress',chunks.append)
    assert u.run(sys.executable,'-c',"print('progress',flush=True)")=='progress'
    assert 'progress' in ''.join(chunks)
    with pytest.raises(subprocess.TimeoutExpired):
        u.run(sys.executable,'-c','import time; time.sleep(10)',timeout=.05)


def test_interrupted_fast_update_keeps_venv(area,monkeypatch):
    data=area/'data';data.mkdir();(data/'db').write_text('new')
    venv=area/'.venv';venv.mkdir();(venv/'pkg').write_text('keep')
    backup=area/'.updates/backup';(backup/'data').mkdir(parents=True)
    (backup/'data/db').write_text('old');(backup/'meshcorestation.env').write_text('settings')
    monkeypatch.setattr(u,'run',lambda *a,**k:'')
    monkeypatch.setattr(u,'service',lambda *a:None);monkeypatch.setattr(u,'healthy',lambda *a:None)
    u.recover(dict(old='a'*40,target='b'*40,backup=str(backup),data=str(data),port=80,backup_complete=True,backup_venv=False))
    assert (venv/'pkg').read_text()=='keep'
    assert (data/'db').read_text()=='old'
