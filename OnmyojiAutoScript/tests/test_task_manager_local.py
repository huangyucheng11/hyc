"""Local task controls: isolated config fixtures, never the user's live queue."""
import json
import os
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from module.server import task_manager as tm
from module.server.script_process import ScriptState
from module.server.script_router import script_app


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.original_dir = Path.cwd()
        self.fixture = json.loads(Path('config/template.json').read_text(encoding='utf-8'))
        self.temp = TemporaryDirectory(dir=self.original_dir)
        os.chdir(self.temp.name)
        Path('config').mkdir()
        for value in self.fixture.values():
            if isinstance(value, dict) and 'scheduler' in value:
                value['scheduler']['enable'] = False
        self.fixture['config_name'] = 'fixture'
        self.fixture['gold_youkai']['scheduler']['enable'] = True
        self.fixture['gold_youkai']['local_custom_setting'] = {'preserve': True}
        Path('config/fixture.json').write_text(json.dumps(self.fixture), encoding='utf-8')
        self.processes = patch.object(tm.mm, 'script_process', {})
        self.processes.start()
        app = FastAPI()
        app.include_router(tm.task_manager_app)
        app.include_router(script_app)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.processes.stop()
        os.chdir(self.original_dir)
        self.temp.cleanup()

    def read(self):
        return json.loads(Path('config/fixture.json').read_text(encoding='utf-8'))

    def test_lists_every_task_and_rejects_invalid_config_or_task(self):
        response = self.client.get('/task-manager/fixture')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()['total'], 40)
        self.assertEqual(response.json()['enabled_count'], 1)
        self.assertEqual(self.client.get('/task-manager/template').status_code, 404)
        self.assertEqual(self.client.get('/task-manager/missing').status_code, 404)
        self.assertEqual(self.client.post('/task-manager/fixture/Script', json={'action': 'remove'}).status_code, 404)
        self.assertEqual(self.client.post('/task-manager/fixture/GoldYoukai', json={'action': 'bad'}).status_code, 400)

    def test_reset_changes_all_times_and_preserves_enables_and_task_settings(self):
        before = self.read()
        response = self.client.post('/task-manager/fixture/reset-times')
        self.assertEqual(response.status_code, 200)
        after = self.read()
        for key, value in before.items():
            if isinstance(value, dict) and 'scheduler' in value:
                self.assertEqual(after[key]['scheduler']['enable'], value['scheduler']['enable'])
                dt = datetime.strptime(after[key]['scheduler']['next_run'], '%Y-%m-%d %H:%M:%S')
                self.assertLess(abs((datetime.now() - dt).total_seconds()), 5)
                for group in value:
                    if group != 'scheduler':
                        self.assertEqual(after[key][group], value[group])
        self.assertTrue(Path(response.json()['backup']).exists())

    def test_skip_postpones_without_disabling_and_remove_can_be_undone(self):
        response = self.client.post('/task-manager/fixture/GoldYoukai', json={'action': 'skip'})
        self.assertEqual(response.status_code, 200)
        scheduler = self.read()['gold_youkai']['scheduler']
        self.assertTrue(scheduler['enable'])
        self.assertGreater(datetime.strptime(scheduler['next_run'], '%Y-%m-%d %H:%M:%S'), datetime.now())
        response = self.client.post('/task-manager/fixture/GoldYoukai', json={'action': 'remove'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.read()['gold_youkai']['scheduler']['enable'])
        response = self.client.post('/task-manager/fixture/GoldYoukai', json={'action': 'toggle', 'enabled': True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.read()['gold_youkai']['scheduler']['enable'])

    def test_removing_last_running_task_stops_without_restarting(self):
        class FakeProcess:
            state = ScriptState.RUNNING
            stop = AsyncMock()
            start = AsyncMock()
            broadcast_state = AsyncMock()
        process = FakeProcess()
        tm.mm.script_process['fixture'] = process
        response = self.client.post('/task-manager/fixture/GoldYoukai', json={'action': 'remove'})
        self.assertEqual(response.status_code, 200)
        process.stop.assert_awaited_once()
        process.start.assert_not_awaited()

    def test_failed_change_restores_original_configuration(self):
        original = self.read()
        with patch.object(tm.Config, 'task_delay', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/task-manager/fixture/GoldYoukai', json={'action': 'skip'})
        self.assertEqual(self.read(), original)

    def test_empty_queue_keeps_websocket_connected(self):
        self.client.post('/task-manager/fixture/GoldYoukai', json={'action': 'remove'})
        with self.client.websocket_connect('/ws/fixture') as ws:
            self.assertEqual(ws.receive_json()['state'], 0)
            schedule = ws.receive_json()['schedule']
            self.assertEqual(schedule, {'running': {}, 'pending': [], 'waiting': []})
            ws.send_text('get_schedule')
            self.assertEqual(ws.receive_json()['schedule'], schedule)


if __name__ == '__main__':
    unittest.main()
