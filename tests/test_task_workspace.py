import io
import json
import threading
import zipfile
from types import SimpleNamespace
from unittest.mock import patch
import pytest


def test_podcast_and_video_share_the_bounded_executor():
    from api.routers.processing import PROCESSING_EXECUTOR
    from api.routers.video_notes import VIDEO_EXECUTOR
    assert PROCESSING_EXECUTOR is VIDEO_EXECUTOR
    assert PROCESSING_EXECUTOR._max_workers == 2


def test_media_gate_serializes_ffmpeg_and_releases_after_failure():
    from resource_scheduler import run_media_process
    from concurrent.futures import ThreadPoolExecutor
    count=0; maximum=0; lock=threading.Lock()
    def work(*args,**kwargs):
        nonlocal count,maximum
        import time
        with lock: count+=1;maximum=max(maximum,count)
        time.sleep(.03)
        with lock:count-=1
    with patch('resource_scheduler.subprocess.run',side_effect=work),ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _:run_media_process(['ffmpeg','-version']),range(3)))
    assert maximum==1
    with patch('resource_scheduler.subprocess.run',side_effect=RuntimeError('failed')):
        with pytest.raises(RuntimeError):run_media_process(['ffmpeg'])
    with patch('resource_scheduler.subprocess.run',return_value='recovered'):
        assert run_media_process(['ffmpeg'])=='recovered'


def backup_client(corrupt=False):
    objects={};queries=[]
    class Query:
        def __init__(self,table):self.table=table
        def select(self,fields):return self
        def order(self,key):queries.append((self.table,key));return self
        def range(self,start,end):assert end-start<100;return self
        def execute(self):return SimpleNamespace(data=[{'user_id':'owner','id':'record','value':'private content'}])
    class Bucket:
        def __init__(self,name):self.name=name
        def upload(self,name,content,file_options):
            assert self.name=='application-backups';assert file_options['upsert']=='false';objects[name]=content
        def download(self,name):
            if self.name!='application-backups':return b'private image bytes'
            return b'corrupt' if corrupt else objects[name]
    storage=SimpleNamespace(get_bucket=lambda _:SimpleNamespace(public=False),from_=lambda name:Bucket(name))
    return SimpleNamespace(table=Query,storage=storage),objects,queries


def test_private_backup_is_streamed_read_back_and_checked_before_manifest_publish():
    from scripts import backup_application as backup
    client,objects,queries=backup_client()
    with patch('api.supabase_client.get_supabase_admin_client',return_value=client),patch('screenshot_extractor._iter_bucket_objects',return_value=[{'name':'frame.jpg'}]):
        report=backup.backup()
    assert report['verified']==1 and report['tables']==10 and report['records']==10
    manifest=json.loads(next(value for key,value in objects.items() if key.endswith('.manifest.json')))
    content=b''.join(objects[name] for name in manifest['parts'])
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        assert len(json.loads(archive.read('database/episodes.json')))==1
        assert archive.read('media/screenshots/frame.jpg')==b'private image bytes'
    assert ('user_settings','user_id') in queries


def test_corrupted_backup_never_publishes_a_verified_manifest():
    from scripts import backup_application as backup
    client,objects,_=backup_client(corrupt=True)
    with patch('api.supabase_client.get_supabase_admin_client',return_value=client),patch('screenshot_extractor._iter_bucket_objects',return_value=[]):
        with pytest.raises(RuntimeError,match='verification failed'):backup.backup()
    assert not any(name.endswith('.manifest.json') for name in objects)


def test_maintenance_selects_the_application_container_not_the_proxy(monkeypatch,capsys):
    from scripts import admin_runtime
    monkeypatch.setenv('CONTAINER_INSTANCE_ID','fixture')
    def oci(args,query):
        if 'container-instance' in args:return ['edge','app']
        return {} if args[-1]=='edge' else {'SUPABASE_URL':'https://fixture.test','SUPABASE_SERVICE_KEY':'synthetic','SUPABASE_KEY':'synthetic'}
    captured={}
    def child(args,env,**kwargs):
        captured.update(env)
        return SimpleNamespace(stdout='{"operation":"backup","verified":1}',returncode=0)
    with patch.object(admin_runtime,'oci_json',side_effect=oci),patch.object(admin_runtime.subprocess,'run',side_effect=child):
        assert admin_runtime.run_private_child('fixture.py')==0
    assert captured['SUPABASE_URL']=='https://fixture.test'
    assert 'synthetic' not in capsys.readouterr().out


def test_backup_refuses_a_public_destination_without_uploading_data():
    from scripts import backup_application as backup
    client,objects,_=backup_client()
    client.storage.get_bucket=lambda _:{'public':True}
    with patch('api.supabase_client.get_supabase_admin_client',return_value=client):
        with pytest.raises(RuntimeError,match='private'):backup.backup()
    assert objects=={}
