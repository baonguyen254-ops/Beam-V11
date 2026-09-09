"""Exercise the shipped launcher, static assets, HTTP commands, backup and restart."""
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix='beam-release-') as folder:
        data=Path(folder)/'runtime'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        env={**os.environ,'BEAM_DATA_DIR':str(data),'BEAM_ALLOWED_ORIGINS':origin}
        with (Path(folder)/'server.log').open('w+') as log,httpx.Client(base_url=origin,trust_env=False,headers={'Origin':origin},timeout=10) as client:
            proc=None
            def start():
                proc=subprocess.Popen([sys.executable,str(ROOT/'RUN_BEAM.py'),'--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log)
                for _ in range(100):
                    if proc.poll() is not None:raise RuntimeError('Launcher stopped during startup')
                    try:
                        if client.get('/health').status_code==200:return proc
                    except httpx.ConnectError:pass
                    time.sleep(.1)
                proc.terminate();proc.wait(timeout=10)
                raise RuntimeError('Launcher startup timeout')
            def stop(proc):
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
            try:
                proc=start();page=client.get('/')
                assert page.status_code==200 and 'v11.1 Hospital Intelligence' in page.text
                assets=re.findall(r'(?:src|href)="(/assets/[^"]+)"',page.text)
                assert assets
                for asset in assets:assert client.get(asset).status_code==200
                assert client.get('/api/hospital').status_code==401
                result=client.post('/api/setup',json={'key':(data/'bootstrap-key.txt').read_text(),'username':'release-test','password':'release-smoke-password'})
                assert result.status_code==200,result.text
                payload={'action':'SET_LIGHTING','value':42,'command_id':'persisted-release-command'}
                assert client.post('/api/commands',json=payload).json()['ok']
                assert client.post('/api/commands',json=payload).json()['replayed']
                for _ in range(50):
                    report=client.get('/api/energy?resolution=second').json()
                    if report['totals']['observed_seconds']>0:break
                    time.sleep(.1)
                else:raise AssertionError('No observed energy sample')
                assert client.get('/api/energy?resolution=second&format=csv').text.startswith('\ufeffperiod,')
                backup=Path(folder)/'backup.sqlite3'
                subprocess.run([sys.executable,str(ROOT/'tools/backup_data.py'),str(data/'beam.sqlite3'),str(backup)],check=True,capture_output=True)
                with sqlite3.connect(backup) as db:
                    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                    assert db.execute('SELECT COUNT(*) FROM commands').fetchone()[0]>=1
                stop(proc);proc=None;proc=start()
                assert client.get('/api/state').json()['lighting']['level_percent']==42
                assert client.post('/api/commands',json=payload).json()['replayed']
                assert client.get('/api/energy').json()['totals']['observed_seconds']>0
                assert not (data/'bootstrap-key.txt').exists()
                print('PASS release smoke: launcher, static assets, login, HTTP idempotency, observed energy/CSV, live backup and restart persistence')
            except Exception:
                log.seek(0);print(log.read());raise
            finally:
                if proc is not None:stop(proc)

if __name__=='__main__':main()
