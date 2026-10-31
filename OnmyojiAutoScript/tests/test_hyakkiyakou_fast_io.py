"""Fast game IO must work without a Windows window tree, including legacy profiles."""
from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from module.exception import RequestHumanTakeover
from tasks.Hyakkiyakou.config import DebugConfig, ScreenshotMethod, ControlMethod
from tasks.Hyakkiyakou.slave.hya_device import HyaDevice, image_black
from tasks.Hyakkiyakou.script_task import ScriptTask


def make_io():
    io = object.__new__(HyaDevice)
    io.config = SimpleNamespace(script=SimpleNamespace(
        device=SimpleNamespace(screenshot_method='nemu_ipc', control_method='minitouch'),
        error=SimpleNamespace(save_error=True)))
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[100:200, 100:200] = 200  # Black borders do not mean a black frame.
    io.device = SimpleNamespace(
        screenshot_methods={'nemu_ipc': Mock(return_value=frame),
                            'ADB': Mock(return_value=frame),
                            'window_background': Mock(side_effect=AttributeError('root_node'))},
        click_methods={'minitouch': Mock(), 'ADB': Mock(),
                       'window_message': Mock(side_effect=AttributeError('root_node'))},
        screenshot_deque=deque(maxlen=3))
    io.hya_screenshot_interval = Mock()
    io.hya_fs_check_timer = Mock(reached=Mock(return_value=False))
    return io


class FastIOTests(unittest.TestCase):
    def test_defaults_follow_the_configured_device(self):
        self.assertEqual(DebugConfig().hya_screenshot_method, ScreenshotMethod.AUTO)
        self.assertEqual(DebugConfig().hya_control_method, ControlMethod.AUTO)

    def test_legacy_window_settings_work_without_root_node(self):
        io = make_io()
        frame = io.fast_screenshot(ScreenshotMethod.WINDOW_BACKGROUND)
        io.fast_click(600, 400, ControlMethod.WINDOW_MESSAGE)
        self.assertEqual(frame.shape, (720, 1280, 3))
        io.device.screenshot_methods['nemu_ipc'].assert_called_once()
        io.device.click_methods['minitouch'].assert_called_once_with(x=600, y=400)
        io.device.screenshot_methods['window_background'].assert_not_called()
        io.device.click_methods['window_message'].assert_not_called()
        self.assertEqual(len(io.device.screenshot_deque), 1)

    def test_failed_fast_capture_and_control_use_adb_and_remember_it(self):
        io = make_io()
        io.device.screenshot_methods['nemu_ipc'].side_effect = RuntimeError('IPC not available')
        io.device.click_methods['minitouch'].side_effect = RuntimeError('touch disconnected')
        for _ in range(2):
            io.fast_screenshot(ScreenshotMethod.AUTO)
            io.fast_click(500, 300, ControlMethod.AUTO)
        io.device.screenshot_methods['nemu_ipc'].assert_called_once()
        io.device.click_methods['minitouch'].assert_called_once()
        self.assertEqual(io.device.screenshot_methods['ADB'].call_count, 2)
        self.assertEqual(io.device.click_methods['ADB'].call_count, 2)

    def test_valid_window_settings_are_preserved(self):
        io = make_io()
        io.device.root_node = object()
        io.device.root_handle_num = 42
        io.device.screenshot_methods['window_background'].side_effect = None
        io.device.screenshot_methods['window_background'].return_value = np.ones((720, 1280, 3), np.uint8)
        io.device.click_methods['window_message'].side_effect = None
        io.fast_screenshot(ScreenshotMethod.WINDOW_BACKGROUND)
        io.fast_click(500, 300, ControlMethod.WINDOW_MESSAGE)
        io.device.click_methods['window_message'].assert_called_once_with(x=500, y=300, fast=True)
        io.device.screenshot_methods['nemu_ipc'].assert_not_called()

    def test_empty_and_black_frames_are_rejected_but_black_borders_are_valid(self):
        io = make_io()
        self.assertFalse(image_black(io.device.screenshot_methods['nemu_ipc']()))
        self.assertTrue(image_black(np.zeros((720, 1280, 3), np.uint8)))
        self.assertTrue(image_black(None))
        io.device.screenshot_methods['nemu_ipc'].return_value = None
        io.device.screenshot_methods['ADB'].return_value = np.zeros((720, 1280, 3), np.uint8)
        with self.assertRaises(RequestHumanTakeover):
            io.fast_screenshot()

    def test_preflight_sends_no_click_and_validates_interval(self):
        io = make_io()
        io.prepare_fast_io(ScreenshotMethod.WINDOW_BACKGROUND, ControlMethod.WINDOW_MESSAGE, 300)
        io.device.click_methods['minitouch'].assert_not_called()
        self.assertEqual(io._hya_control_backend, 'minitouch')
        with self.assertRaises(RequestHumanTakeover):
            io.prepare_fast_io(ScreenshotMethod.AUTO, ControlMethod.AUTO, 0)

    def test_round_reaches_agent_and_throw_after_boss_selection(self):
        io = make_io()
        task = object.__new__(ScriptTask)
        task.__dict__.update(io.__dict__)
        debug = SimpleNamespace(hya_screenshot_method=ScreenshotMethod.WINDOW_BACKGROUND,
                                hya_control_method=ControlMethod.WINDOW_MESSAGE, hya_interval=300,
                                hya_show=False, hya_info=False, continuous_learning=False, hya_save_result=False)
        task.config.hyakkiyakou = SimpleNamespace(debug_config=debug,
            hyakkiyakou_config=SimpleNamespace(hya_invite_friend=False))
        task.device.stuck_record_add = Mock()
        task.ui_click = Mock()
        task.wait_until_appear = Mock()
        task._select_best_boss = Mock()
        task.screenshot = Mock()
        task.bean_05to10 = Mock()
        task.update_state = Mock(return_value=[250, 36, 10, -1, -1, -1, -1])
        task.__dict__['tracker'] = Mock(return_value=[])
        task.__dict__['agent'] = SimpleNamespace(decision=Mock(return_value=[600, 400, True, 10]))
        task.__dict__['debugger'] = Mock()
        capture = task.device.screenshot_methods['nemu_ipc']
        task.appear = lambda rule: (rule == task.I_HACCESS or
            rule == task.I_CHECK_RUN or rule == task.I_HEND and capture.call_count >= 3)
        with patch('tasks.Hyakkiyakou.script_task.time.sleep'), patch.object(task, 'set_fast_screenshot_interval'):
            task.one()
        task._select_best_boss.assert_called_once()
        task.agent.decision.assert_called_once()
        task.device.click_methods['minitouch'].assert_called_once_with(x=600, y=400)
        self.assertEqual(task.ui_click.call_count, 2)


if __name__ == '__main__':
    unittest.main()
