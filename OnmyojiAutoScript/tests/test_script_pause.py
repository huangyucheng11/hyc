"""Pause real disposable workers; never control the user's emulator or queue."""
import asyncio
import json
import multiprocessing
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import psutil

from module.base.timer import Timer, set_pause_offset
from module.server.main_manager import mm
from module.server.script_process import ScriptProcess, ScriptState
from tests import test_task_manager_local as fixtures


def counter_worker(counter, elapsed, offset, ready):
    set_pause_offset(offset)
    timer = Timer(10).start()
    ready.set()
    while True:
        counter.value += 1
        elapsed.value = timer.current()
        time.sleep(0.01)


class ScriptPauseTests(unittest.TestCase):
    setUp = fixtures.TaskManagerTests.setUp

    def tearDown(self):
        for process in list(mm.script_process.values()):
            if isinstance(process, ScriptProcess):
                asyncio.run(process.stop())
        fixtures.TaskManagerTests.tearDown(self)

    def worker(self):
        process = ScriptProcess('fixture')
        counter = multiprocessing.Value('i', 0, lock=False)
        elapsed = multiprocessing.Value('d', 0.0, lock=False)
        ready = multiprocessing.Event()
        process._process = multiprocessing.Process(
            target=counter_worker,
            args=(counter, elapsed, process._pause_offset, ready), daemon=True)
        process._process.start()
        process.state = ScriptState.RUNNING
        mm.script_process['fixture'] = process
        self.assertTrue(ready.wait(15), 'disposable worker did not start')
        time.sleep(0.1)
        return process, counter, elapsed

    def test_real_worker_freezes_and_resumes_same_process_without_counting_pause(self):
        process, counter, elapsed = self.worker()
        original = Path('config/fixture.json').read_bytes()
        pid = process._process.pid
        response = self.client.post('/scripts/pause').json()
        self.assertEqual(response['states']['fixture'], 4)
        frozen_count, frozen_elapsed = counter.value, elapsed.value
        time.sleep(0.6)
        self.assertEqual(counter.value, frozen_count)
        self.assertEqual(elapsed.value, frozen_elapsed)
        # Repeated pause and start are safe; start resumes rather than restarting.
        self.assertTrue(asyncio.run(process.pause()))
        self.assertTrue(asyncio.run(process.start()))
        time.sleep(0.15)
        self.assertEqual(process._process.pid, pid)
        self.assertGreater(counter.value, frozen_count)
        self.assertLess(elapsed.value - frozen_elapsed, 0.4)
        self.assertEqual(Path('config/fixture.json').read_bytes(), original)
        self.assertTrue(asyncio.run(process.start()))
        self.assertEqual(process._process.pid, pid)

    def test_stop_suspended_worker_never_resumes_game_input(self):
        process, counter, _ = self.worker()
        self.client.post('/scripts/fixture/pause')
        worker = process._process
        frozen = counter.value
        with patch('module.server.script_process.psutil.Process') as os_process:
            self.client.get('/fixture/stop')
            os_process.assert_not_called()
        self.assertFalse(worker.is_alive())
        self.assertEqual(counter.value, frozen)
        self.assertEqual(process.state, ScriptState.INACTIVE)
        self.assertIsNone(process._process)

    def test_control_error_does_not_report_false_success(self):
        process, _, _ = self.worker()
        with patch('module.server.script_process.psutil.Process', side_effect=psutil.AccessDenied()):
            result = self.client.post('/scripts/pause').json()
        self.assertEqual(result['changed'], [])
        self.assertIn('fixture', result['errors'])
        self.assertEqual(result['states']['fixture'], 1)

    def test_global_actions_only_touch_matching_states_and_report_all_profiles(self):
        def fake(state):
            process = SimpleNamespace(state=state, last_error='')
            async def pause():
                process.state = ScriptState.PAUSED
                return True
            async def resume():
                process.state = ScriptState.RUNNING
                return True
            process.pause, process.resume = AsyncMock(side_effect=pause), AsyncMock(side_effect=resume)
            return process
        mm.script_process.update({
            'fixture': fake(ScriptState.RUNNING), 'oas2': fake(ScriptState.RUNNING),
            'idle': fake(ScriptState.INACTIVE), 'failed': fake(ScriptState.WARNING)})
        result = self.client.post('/scripts/pause').json()
        self.assertEqual(set(result['changed']), {'fixture', 'oas2'})
        result = self.client.post('/scripts/resume').json()
        self.assertEqual(result['states'], {'fixture': 1, 'oas2': 1, 'idle': 0, 'failed': 2})
        mm.script_process['idle'].resume.assert_not_awaited()
        mm.script_process['failed'].resume.assert_not_awaited()
        self.assertEqual(self.client.post('/scripts/missing/pause').status_code, 404)
        self.assertEqual(self.client.post('/scripts/fixture/invalid').status_code, 400)

    def test_failed_resume_keeps_worker_paused_and_dead_worker_cannot_resume(self):
        process, counter, _ = self.worker()
        self.client.post('/scripts/pause')
        frozen = counter.value
        with patch('module.server.script_process.psutil.Process', side_effect=psutil.AccessDenied()):
            result = self.client.post('/scripts/resume').json()
        self.assertEqual(result['states']['fixture'], 4)
        self.assertIn('fixture', result['errors'])
        self.assertEqual(process._pause_offset.value, 0.0)
        self.assertEqual(counter.value, frozen)
        process._process.kill()
        process._process.join(1)
        result = self.client.post('/scripts/resume').json()
        self.assertEqual(result['states']['fixture'], 2)
        self.assertIn('fixture', result['errors'])

    def test_paused_profile_retains_schedule_on_reconnect_and_locks_its_device(self):
        process, _, _ = self.worker()
        self.fixture['running_task'] = 'GoldYoukai'
        self.fixture['script']['device']['serial'] = '127.0.0.1:16384'
        for name in ('fixture', 'oas2'):
            Path(f'config/{name}.json').write_text(json.dumps(self.fixture), encoding='utf-8')
        self.client.post('/scripts/fixture/pause')
        with self.client.websocket_connect('/ws/fixture') as ws:
            self.assertEqual(ws.receive_json()['state'], 4)
            self.assertEqual(ws.receive_json()['schedule']['running']['name'], 'GoldYoukai')
            ws.send_text('get_state')
            self.assertEqual(ws.receive_json()['state'], 4)
            ws.send_text('resume')
            self.assertEqual(ws.receive_json()['state'], 1)
        asyncio.run(process.pause())
        other = ScriptProcess('oas2')
        other.broadcast_state = AsyncMock()
        self.assertFalse(asyncio.run(other.start()))
        self.assertIsNone(other._process)

    def test_editing_queue_while_paused_stays_stopped(self):
        process, _, _ = self.worker()
        self.client.post('/scripts/pause')
        worker = process._process
        result = self.client.post('/task-manager/fixture/reset-times')
        self.assertEqual(result.status_code, 200)
        self.assertFalse(worker.is_alive())
        self.assertEqual(process.state, ScriptState.INACTIVE)
        self.assertEqual(self.client.post('/scripts/resume').json()['changed'], [])


if __name__ == '__main__':
    unittest.main()
