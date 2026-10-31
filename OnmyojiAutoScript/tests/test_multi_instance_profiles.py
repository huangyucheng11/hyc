"""Multi-account profiles, channel selection, and instance isolation."""
import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from module.device.local_emulators import list_mumu_instances
from module.device.onmyoji_packages import select_package
from module.server.config_manager import ConfigManager
from module.server.script_process import ScriptProcess, ScriptState
from tasks.Script.config_device import Device, PackageName
from tests.test_task_manager_local import TaskManagerTests

OFFICIAL = 'com.netease.onmyoji'
TENCENT = 'com.tencent.tmgp.yys.zqb'


class PackageSelectionTests(unittest.TestCase):
    def test_tencent_is_a_valid_package_and_is_exposed_in_settings(self):
        device = Device(package_name=TENCENT)
        self.assertEqual(device.package_name, PackageName.TENCENT_APP_STORE)
        self.assertIn(TENCENT, Device.model_json_schema()['$defs']['PackageName']['enum'])

    def test_single_channel_auto_selects(self):
        self.assertEqual(select_package([TENCENT]), TENCENT)

    def test_multiple_clients_choose_foreground_only(self):
        dump = f'Hist #1: ActivityRecord{{u0 {OFFICIAL}/.Client}}\n' \
               f'topResumedActivity=ActivityRecord{{abcd u0 {TENCENT}/.Client t12}}'
        self.assertEqual(select_package([OFFICIAL, TENCENT], dump), TENCENT)
        self.assertIsNone(select_package([OFFICIAL, TENCENT], f'Hist #1: {OFFICIAL}/.Client'))
        self.assertIsNone(select_package([OFFICIAL, TENCENT], 'mCurrentFocus=Window{u0 com.android.launcher/.Main}'))

    def test_new_instances_are_discovered_on_refresh(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / 'nx_main/MuMuNxMain.exe'
            for index, port in enumerate((16384, 16555)):
                path = root / f'vms/MuMuPlayer-15.0-{index}/configs/vm_config.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({'vm': {'nat': {'port_forward': {'adb': {'host_port': str(port)}}}}}))
                rows = list_mumu_instances([executable], check_online=False)
                self.assertEqual(len(rows), index + 1)
            self.assertEqual([row['serial'] for row in rows], ['127.0.0.1:16384', '127.0.0.1:16555'])


class ProfileCreationTests(TaskManagerTests):
    def setUp(self):
        super().setUp()
        Path('config/template.json').write_text(json.dumps(self.fixture), encoding='utf-8')

    def test_new_profile_binds_selected_instance_and_channel_and_connects_ws(self):
        instance = {'serial': '127.0.0.1:16555', 'emulatorinfo_type': 'MuMuPlayer12',
                    'emulatorinfo_name': 'MuMuPlayer-15.0-1', 'emulatorinfo_path': 'E:/MuMu/nx_main/MuMuNxMain.exe'}
        before = Path('config/fixture.json').read_bytes()
        with patch('module.device.local_emulators.list_mumu_instances', return_value=[instance]):
            result = self.client.post('/config_copy', params={'file': 'oas2', 'device_serial': instance['serial'],
                                                            'package_name': TENCENT})
        self.assertEqual(result.status_code, 200)
        self.assertIn('oas2', result.json())
        data = json.loads(Path('config/oas2.json').read_text(encoding='utf-8'))
        self.assertEqual(data['config_name'], 'oas2')
        self.assertEqual(data['running_task'], '')
        self.assertEqual(data['script']['device']['serial'], instance['serial'])
        self.assertEqual(data['script']['device']['package_name'], TENCENT)
        self.assertEqual(Path('config/fixture.json').read_bytes(), before)
        with self.client.websocket_connect('/ws/oas2') as ws:
            self.assertEqual(ws.receive_json()['state'], 0)
            self.assertIn('schedule', ws.receive_json())
        self.assertEqual(self.client.get('/task-manager/oas2').status_code, 200)

    def test_invalid_instance_and_duplicate_name_do_not_overwrite(self):
        before = Path('config/fixture.json').read_bytes()
        result = self.client.post('/config_copy', params={'file': 'fixture'})
        self.assertEqual(result.status_code, 400)
        with patch('module.device.local_emulators.list_mumu_instances', return_value=[]):
            result = self.client.post('/config_copy', params={'file': 'oas2', 'device_serial': '127.0.0.1:9999'})
        self.assertEqual(result.status_code, 400)
        self.assertFalse(Path('config/oas2.json').exists())
        self.assertEqual(Path('config/fixture.json').read_bytes(), before)

    def test_two_running_profiles_cannot_control_the_same_instance(self):
        from module.server.main_manager import mm
        self.fixture['script']['device']['serial'] = '127.0.0.1:16384'
        for name in ('fixture', 'oas2'):
            Path(f'config/{name}.json').write_text(json.dumps(self.fixture), encoding='utf-8')
        other = SimpleNamespace(state=ScriptState.RUNNING, _process=Mock(is_alive=lambda: True))
        target = ScriptProcess('oas2')
        target.broadcast_state = AsyncMock()
        mm.script_process.update({'fixture': other, 'oas2': target})
        self.assertFalse(asyncio.run(target.start()))
        self.assertEqual(target.state, ScriptState.INACTIVE)
        self.assertIsNone(target._process)
        self.assertIn('正在使用模拟器', target.broadcast_state.await_args_list[0].args[0]['error'])


if __name__ == '__main__':
    unittest.main()
