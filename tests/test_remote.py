from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from canteen_monitor.api import create_app
from canteen_monitor.config import Config
from canteen_monitor.remote import Batch, ingest
from canteen_monitor.storage import Store, devices, observations, registry, sessions
from canteen_monitor.uploader import UploadQueue

HEADERS = {"X-Local-Admin": "1"}


@pytest.fixture
def system(tmp_path):
    config = Config(database_path=tmp_path / "remote.sqlite3")
    with TestClient(create_app(config), base_url="http://localhost", client=("127.0.0.1", 5000)) as client:
        yield client, config


def register(client, collector="probe_01"):
    response = client.post('/api/devices', headers=HEADERS, json={"collector_id": collector, "name": "Canteen", "location": "Entrance", "source": "esp32_c5"})
    assert response.status_code == 201, response.text
    return response.json()['token']


def batch(collector="probe_01", **updates):
    result = {"schema_version": 1, "batch_id": str(uuid4()), "collector_id": collector,
              "timestamp": datetime.now(UTC).isoformat(), "status": "success", "observations": [
                  {"ssid": "Campus-Demo", "bssid": "AA:BB:CC:DD:EE:01", "station_count": 0, "channel_utilization_raw": 0, "rssi_dbm": -65, "band": "5GHz", "channel": 36}]}
    result.update(updates)
    return result


def upload(client, token, body):
    return client.post('/api/collector/observations', headers={"Authorization": f"Bearer {token}"}, json=body)


def test_registration_and_secret_storage(system):
    client, config = system
    token = register(client)
    listing = client.get('/api/devices').json()
    assert len(listing) == 1 and listing[0]['online'] is False
    assert token not in json.dumps(listing) and 'token_hash' not in listing[0]
    store = Store(config.database_path)
    with store.engine.connect() as conn:
        saved = conn.execute(select(devices)).mappings().one()
        assert saved['token_hash'] != token
    store.close()
    assert client.post('/api/devices', headers=HEADERS, json={"collector_id":"probe_01","name":"duplicate"}).status_code == 409


def test_auth_scope_disable_rotate(system):
    client, _ = system
    token = register(client)
    other = register(client, "other")
    assert upload(client, "wrong", batch()).status_code == 401
    assert upload(client, other, batch()).status_code == 401
    rotated = client.post('/api/devices/probe_01/rotate-key', headers=HEADERS).json()['token']
    assert upload(client, token, batch()).status_code == 401
    assert upload(client, rotated, batch()).status_code == 200
    assert client.put('/api/devices/probe_01', headers=HEADERS, json={"name":"updated","location":"east","interval_seconds":120,"enabled":False}).status_code == 200
    assert upload(client, rotated, batch()).status_code == 401
    assert client.get('/api/devices').json()[0]['online'] is False


def test_ingestion_retry_and_conflict(system):
    client, config = system
    token = register(client)
    body = batch()
    first = upload(client, token, body)
    assert first.status_code == 200
    retry = upload(client, token, body)
    assert retry.json()['duplicate'] is True
    body['observations'][0]['station_count'] = 10
    assert upload(client, token, body).status_code == 409
    summary = client.get('/api/dashboard/summary').json()
    assert summary['aps'][0]['station_count'] == 0
    assert summary['aps'][0]['rssi_dbm'] == -65
    assert summary['aps'][0]['signal'] is None
    assert summary['aps'][0]['channel_utilization_percent'] == 0
    assert summary['collection_enabled'] is False
    assert summary['collectors'][0]['scan_location'] == 'Entrance'
    store=Store(config.database_path)
    assert len(store.history()) == 1
    store.close()


def test_old_backfill_does_not_replace_latest(system):
    client, _ = system
    token = register(client)
    assert upload(client, token, batch()).status_code == 200
    old = batch(timestamp=(datetime.now(UTC)-timedelta(days=2)).isoformat())
    old['observations'][0]['station_count'] = 50
    old['observations'][0]['ssid'] = "old"
    assert upload(client, token, old).status_code == 200
    summary = client.get('/api/dashboard/summary').json()
    assert summary['aps'][0]['station_count'] == 0
    assert summary['registry'][0]['ssid'] == 'Campus-Demo'
    device = client.get('/api/devices').json()[0]
    assert device['online'] and device['data_fresh']


def test_backfill_online_but_stale_and_failure(system):
    client, _ = system
    token = register(client)
    assert upload(client,token,batch(timestamp=(datetime.now(UTC)-timedelta(days=2)).isoformat())).status_code == 200
    device=client.get('/api/devices').json()[0]
    assert device['online'] and not device['data_fresh']
    assert upload(client,token,batch(status='failed',error='radio unavailable',observations=[])).status_code == 200
    summary=client.get('/api/dashboard/summary').json()
    assert summary['aps'] == []
    assert summary['collectors'][0]['status'] == 'failed'
    assert client.get('/api/devices').json()[0]['last_error'] == 'radio unavailable'


@pytest.mark.parametrize("modify", [
    lambda b: b.update(timestamp="2026-01-01T00:00:00"),
    lambda b: b.update(timestamp=(datetime.now(UTC)+timedelta(hours=1)).isoformat()),
    lambda b: b['observations'][0].update(station_count=-1),
    lambda b: b['observations'][0].update(station_count=True),
    lambda b: b['observations'][0].update(channel_utilization_raw=256),
    lambda b: b['observations'].append(b['observations'][0]),
    lambda b: b.update(status='failed'),
    lambda b: b['observations'][0].update(client_mac='not allowed'),
])
def test_invalid_batches_atomic(system, modify):
    client, config = system
    token = register(client)
    body=batch();modify(body)
    assert upload(client,token,body).status_code == 422
    store=Store(config.database_path)
    assert store.history() == []
    with store.engine.connect() as conn:
        assert conn.execute(select(sessions)).first() is None
    store.close()


def test_payload_limit_and_admin_origin(system):
    client, _ = system
    token=register(client)
    assert client.post('/api/collector/observations',headers={"Authorization":f"Bearer {token}"},content=b'x'*262145).status_code==413
    assert client.post('/api/devices/probe_01/rotate-key').status_code==403
    assert client.post('/api/devices/probe_01/rotate-key',headers={**HEADERS,"Origin":"https://evil.example"}).status_code==403


def test_remote_cannot_admin(tmp_path):
    with TestClient(create_app(Config(database_path=tmp_path/'db')),base_url='http://localhost',client=('10.1.1.9',123)) as client:
        assert client.post('/api/devices',headers={**HEADERS,'X-Forwarded-For':'127.0.0.1'},json={'collector_id':'remote','name':'remote'}).status_code==403


def test_concurrent_retry(system):
    client, config=system
    token=register(client)
    body=Batch.model_validate(batch())
    store=Store(config.database_path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:ingest(store,token,body),range(2)))
    assert sorted(r['duplicate'] for r in results)==[False,True]
    assert len(store.history())==1
    store.close()


def test_durable_upload_queue(system,tmp_path):
    client, _=system
    token=register(client)
    path=tmp_path/'queue.sqlite3'
    queue=UploadQueue(path)
    body=Batch.model_validate(batch())
    queue.enqueue(body)
    class Offline:
        def post(self,*args,**kwargs):
            raise httpx.ConnectError('offline')
    assert queue.flush(Offline(),'/api/collector/observations',token)==0
    queue.close()
    queue=UploadQueue(path)
    # Simulate accepted data whose response was lost: retry receives duplicate ack.
    assert upload(client,token,body.model_dump(mode='json')).status_code==200
    assert queue.flush(client,'/api/collector/observations',token)==1
    assert queue.connection.execute('SELECT COUNT(*) FROM pending').fetchone()[0]==0
    queue.close()
