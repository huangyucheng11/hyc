"""Replay the auto-challenge transition that closed the invitation popup mid-loop."""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from module.exception import GameStuckError
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Orochi.config import Orochi, Layer
from tasks.Orochi.script_task import ScriptTask


class InviteReplay(GeneralInvite):
    def __init__(self, *, state='unchecked', disappear=False, unresponsive=False):
        self.state, self.disappear, self.unresponsive = state, disappear, unresponsive
        self.now = 100.0
        self.taps = []

    def screenshot(self):
        self.now += 1
        if self.disappear:
            self.state = 'room'

    def appear(self, rule):
        if rule is self.I_UI_CONFIRM:
            return self.state in ('unchecked', 'checked', 'unknown_checkbox')
        if rule is self.I_UI_CHECK:
            return self.state == 'checked'
        if rule is self.I_UI_UNCHECK:
            return self.state == 'unchecked'
        return False

    def appear_then_click(self, rule, **kwargs):
        if not self.appear(rule):
            return False
        self.taps.append(rule.name)
        if not self.unresponsive:
            self.state = 'checked' if rule is self.I_UI_UNCHECK else 'room'
        return True


class TwoBattleReplay(ScriptTask):
    def __init__(self):
        conf = Orochi()
        conf.orochi_config.layer = Layer.TWELVE
        self.config = SimpleNamespace(orochi=conf)
        self.state, self.now, self.captures, self.invite_frames = 'room', 100.0, 0, 0
        self.current_count, self.limit_count = 0, 2
        self.start_time, self.limit_time = datetime.now(), timedelta(hours=1)
        self.open_team_create = Mock(return_value=True)
        self.ensure_private, self.create_ensure = Mock(), Mock()
        self.run_invite = Mock(side_effect=self.start_first_battle)
        self.exit_room, self.exit_team, self.goto_page = Mock(), Mock(), Mock()

    def screenshot(self):
        self.now += 0.5
        self.captures += 1
        if self.captures > 20:
            raise AssertionError('Still waiting for checkbox after popup disappeared')
        if self.state == 'invite':
            self.invite_frames += 1
            if self.invite_frames == 2:
                self.state = 'auto_battle'

    def appear(self, rule, **kwargs):
        return self.state == 'invite' and rule in (self.I_UI_CONFIRM, self.I_UI_UNCHECK)

    def appear_then_click(self, rule, **kwargs):
        return False

    def is_in_battle(self, is_screenshot=True):
        return self.state in ('manual_battle', 'auto_battle')

    def is_in_room(self, is_screenshot=True):
        return self.state == 'room'

    def start_first_battle(self, **kwargs):
        self.state = 'manual_battle'
        return True

    def run_general_battle(self, **kwargs):
        self.current_count += 1
        self.state = 'invite' if self.current_count == 1 else 'room'
        return True


class InviteTransitionTests(unittest.TestCase):
    def handle(self, task, default=True):
        with patch('module.base.timer.timer_time', side_effect=lambda: task.now):
            return task.check_and_invite(default)

    def test_popup_disappearing_during_checkbox_wait_returns_without_input(self):
        task = InviteReplay(disappear=True)
        self.assertTrue(self.handle(task))
        self.assertEqual(task.taps, [])

    def test_normal_default_invite_checks_then_confirms(self):
        task = InviteReplay()
        self.assertTrue(self.handle(task))
        self.assertEqual(task.taps, [task.I_UI_UNCHECK.name, task.I_UI_CONFIRM.name])

    def test_already_checked_popup_only_needs_confirmation(self):
        task = InviteReplay(state='checked')
        self.assertTrue(self.handle(task))
        self.assertEqual(task.taps, [task.I_UI_CONFIRM.name])

    def test_no_popup_returns_false_without_screenshot_or_input(self):
        task = InviteReplay(state='room')
        self.assertFalse(self.handle(task))
        self.assertEqual(task.now, 100.0)
        self.assertEqual(task.taps, [])

    def test_auto_start_during_room_entry_skips_invitation_setup(self):
        task = InviteReplay(state='room')
        task.ensure_enter = Mock(return_value=True)
        task._invite_battle_started = Mock(return_value=True)
        self.assertTrue(task.run_invite(Orochi().invite_config, is_first=True))
        self.assertEqual(task.taps, [])

    def test_auto_start_while_waiting_returns_control_to_battle_handler(self):
        task = InviteReplay(state='room')
        task.ensure_enter = Mock(return_value=True)
        task._invite_battle_started = lambda: task.state == 'battle'
        task.screenshot = lambda: setattr(task, 'state', 'battle')
        task.click_fire = Mock()
        self.assertTrue(task.run_invite(Orochi().invite_config, is_first=False))
        task.click_fire.assert_not_called()

    def test_room_entry_accepts_battle_without_waiting_for_empty_party_slots(self):
        task = InviteReplay(state='battle')
        task._invite_battle_started = Mock(return_value=True)
        self.assertTrue(task.ensure_enter())

    def test_unresponsive_checkbox_falls_back_to_confirmation(self):
        task = InviteReplay(unresponsive=True)
        # Only checkbox taps fail; confirmation still closes the popup.
        original = task.appear_then_click
        def tap(rule, **kwargs):
            if rule is task.I_UI_CONFIRM:
                task.unresponsive = False
            return original(rule, **kwargs)
        task.appear_then_click = tap
        self.assertTrue(self.handle(task))
        self.assertLess(task.now, 115)

    def test_unresponsive_confirmation_has_a_specific_bounded_error(self):
        task = InviteReplay(state='checked', unresponsive=True)
        with self.assertRaisesRegex(GameStuckError, '战后邀请弹窗确认超时'):
            self.handle(task)
        self.assertLess(task.now, 120)

    def test_default_disabled_does_not_touch_checkbox(self):
        task = InviteReplay()
        self.assertTrue(self.handle(task, default=False))
        self.assertEqual(task.taps, [task.I_UI_CONFIRM.name])

    def test_real_failure_room_is_not_an_invitation_dialog(self):
        path = Path(__file__).parent / 'fixtures/invite_transition/room_after_auto.png'
        crop = cv2.cvtColor(cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), 1), cv2.COLOR_BGR2RGB)
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        image[300:670, 490:880] = crop
        task = SimpleNamespace(I_UI_CONFIRM=GeneralInvite.I_UI_CONFIRM,
                               appear=lambda rule: rule.match(image))
        self.assertFalse(GeneralInvite.check_and_invite(task))

    def test_real_battle_frame_can_interrupt_room_wait(self):
        path = Path(__file__).parent / 'fixtures/invite_transition/battle_indicators.png'
        crop = cv2.cvtColor(cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), 1), cv2.COLOR_BGR2RGB)
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        image[:95, :360] = crop
        task = SimpleNamespace(appear=lambda rule: rule.match(image))
        self.assertTrue(GeneralInvite._invite_battle_started(task))

    def test_auto_started_second_battle_is_counted_after_popup_disappears(self):
        task = TwoBattleReplay()
        with patch('module.base.timer.timer_time', side_effect=lambda: task.now):
            self.assertTrue(task.run_leader())
        self.assertEqual(task.current_count, 2)
        task.run_invite.assert_called_once()
        task.exit_room.assert_called_once()


if __name__ == '__main__':
    unittest.main()
