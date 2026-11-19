"""Real HTTP process integration on loopback; never writes the production DB."""
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from canteen_monitor.remote import Batch
from canteen_monitor.storage import Store
from canteen_monitor.uploader import UploadQueue


def test_separate_server_process_and_durable_client(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = tmp_path / 'server.toml'
    config.write_text('database_path="server.sqlite3"\n', encoding='utf-8')
    process = subprocess.Popen(
        [sys.executable, '-m', 'canteen_monitor', '--config', str(config), 'serve', '--port', str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    queue = UploadQueue(tmp_path / 'queue.sqlite3')
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=2, trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get('/api/health').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError('Temporary receiver did not start')
            response = client.post('/api/devices', headers={'X-Local-Admin':'1'}, json={
                'collector_id':'network_test', 'name':'test-only', 'source':'linux_probe'})
            assert response.status_code == 201, response.text
            token = response.json()['token']
            batch = Batch(batch_id=uuid4(), collector_id='network_test', timestamp=datetime.now(UTC), status='success', observations=[
                {'bssid':'aa:bb:cc:dd:ee:01', 'ssid':'test-only', 'station_count':0}])
            queue.enqueue(batch)
            assert queue.flush(client, '/api/collector/observations', token) == 1
            summary = client.get('/api/dashboard/summary').json()
            assert summary['collection_enabled'] is False
            assert summary['aps'][0]['station_count'] == 0
            assert client.get('/api/devices').json()[0]['online'] is True
            assert client.post('/api/collector/observations', json=batch.model_dump(mode='json')).status_code == 401
    finally:
        queue.close()
        process.terminate()
        process.wait(timeout=10)
    reopened = Store(tmp_path / 'server.sqlite3')
    try:
        assert len(reopened.history()) == 1
    finally:
        reopened.close()
