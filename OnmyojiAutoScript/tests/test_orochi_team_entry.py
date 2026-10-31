"""Replay courtyard team selection and configured invitation behaviour."""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from module.exception import GameStuckError
from tasks.Component.GeneralInvite.config_invite import InviteConfig, InviteNumber, FindMode
from tasks.Component.GeneralInvite.general_invite import GeneralInvite, RoomType
from tasks.Component.GeneralRoom.assets import GeneralRoomAssets
from tasks.GameUi.page import page_team
from tasks.Orochi.config import Orochi, Layer
from tasks.Orochi.script_task import ScriptTask
from tasks.Orochi.team_entry import OrochiTeamEntry


def frame(name):
    path = Path(__file__).parent / 'fixtures/orochi_team' / f'{name}.png'
    crop = cv2.cvtColor(cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), 1), cv2.COLOR_BGR2RGB)
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[135:630, 280:1000] = crop
    return image


class ReplayWheel(OrochiTeamEntry, GeneralRoomAssets):
    def __init__(self, before, *, responsive=True):
        self.device = SimpleNamespace(image=before, swipe_adb=Mock(side_effect=self.drag))
        self.responsive = responsive
        self.now = 100.0

    def screenshot(self):
        self.now += 0.3

    def appear(self, rule):
        return rule.match(self.device.image)

    def drag(self, p1, p2, **kwargs):
        self.assert_inside_wheel(p1)
        self.assert_inside_wheel(p2)
        if self.responsive:
            self.device.image = frame('selected_shenfa')

    def assert_inside_wheel(self, point):
        assert (300 <= point[0] <= 740 and 186 <= point[1] <= 418), point


class OrochiTeamEntryTests(unittest.TestCase):
    def test_selected_row_recognized_but_visible_unselected_shenfa_is_rejected(self):
        self.assertTrue(OrochiTeamEntry.I_TEAM_SHENFA_SELECTED.match(frame('selected_shenfa')))
        self.assertFalse(OrochiTeamEntry.I_TEAM_SHENFA_SELECTED.match(frame('selected_bishou')))
        self.assertFalse(OrochiTeamEntry.I_TEAM_SOUL_SELECTED.match(frame('selected_awake')))

    def test_switches_from_other_dungeon_with_drag_inside_the_popup(self):
        task = ReplayWheel(frame('selected_awake'))
        with patch('module.base.timer.timer_time', side_effect=lambda: task.now):
            task.select_shenfa_team()
        task.device.swipe_adb.assert_called_once()
        p1, p2 = task.device.swipe_adb.call_args.args
        self.assertEqual(p1[0], 402)
        self.assertLess(p2[1], p1[1])

    def test_visible_shenfa_below_selected_biming_must_be_dragged_to_center(self):
        task = ReplayWheel(frame('selected_bishou'))
        with patch('module.base.timer.timer_time', side_effect=lambda: task.now):
            task.select_shenfa_team()
        task.device.swipe_adb.assert_called_once()
        self.assertEqual(task.device.swipe_adb.call_args.args[0][0], 640)

    def test_correct_selection_does_not_move_any_wheel(self):
        task = ReplayWheel(frame('selected_shenfa'))
        task.select_shenfa_team()
        task.device.swipe_adb.assert_not_called()

    def test_unresponsive_wheel_stops_without_creating_wrong_room(self):
        task = ReplayWheel(frame('selected_bishou'), responsive=False)
        with patch('module.base.timer.timer_time', side_effect=lambda: task.now):
            with self.assertRaisesRegex(GameStuckError, '未能选中.*神罚'):
                task.select_shenfa_team()
        self.assertEqual(task.device.swipe_adb.call_count, 24)

    def test_missing_dialog_sends_no_input(self):
        task = ReplayWheel(np.zeros((720, 1280, 3), dtype=np.uint8))
        with self.assertRaisesRegex(GameStuckError, '未检测到创建队伍窗口'):
            task.select_shenfa_team()
        task.device.swipe_adb.assert_not_called()

    def test_shenfa_uses_courtyard_team_entry_without_solo_page_or_lock_button(self):
        config = Orochi()
        config.orochi_config.layer = Layer.TWELVE
        task = SimpleNamespace(config=SimpleNamespace(orochi=config), goto_page=Mock(),
                               screenshot=Mock(), create_room=Mock(return_value=True),
                               select_shenfa_team=Mock())
        self.assertTrue(ScriptTask.open_team_create(task))
        task.goto_page.assert_called_once_with(page_team)
        task.create_room.assert_called_once()
        task.select_shenfa_team.assert_called_once()
        self.assertFalse(config.general_battle_config.lock_team_enable)

    def test_leader_creates_private_room_then_passes_invite_settings_unchanged(self):
        for number in InviteNumber:
            with self.subTest(invite_number=number):
                task = object.__new__(ScriptTask)
                config = Orochi()
                config.orochi_config.layer = Layer.TWELVE
                config.invite_config.invite_number = number
                config.invite_config.find_mode = FindMode.RECENT_FRIEND
                task.config = SimpleNamespace(orochi=config)
                task.current_count, task.limit_count = 0, 1
                task.start_time, task.limit_time = datetime.now(), timedelta(hours=1)
                events = []
                task.open_team_create = Mock(return_value=True)
                task.ensure_private = Mock(side_effect=lambda: events.append('private'))
                task.create_ensure = Mock(side_effect=lambda: events.append('create'))
                task.screenshot = Mock()
                task.check_and_invite = Mock(return_value=False)
                task.appear_then_click = Mock(return_value=False)
                task.is_in_battle = Mock(return_value=False)
                task.is_in_room = Mock(return_value=True)
                task.run_invite = Mock(return_value=True)
                task.run_general_battle = Mock(side_effect=lambda **kw: setattr(task, 'current_count', 1))
                task.exit_room, task.exit_team, task.goto_page = Mock(), Mock(), Mock()
                self.assertTrue(task.run_leader())
                self.assertEqual(events, ['private', 'create'])
                task.run_invite.assert_called_once_with(config=config.invite_config, is_first=True)
                self.assertEqual(config.invite_config.invite_number, number)

    def test_blank_names_in_shenfa_leave_invitation_to_user(self):
        task = object.__new__(ScriptTask)
        config = Orochi()
        config.orochi_config.layer = Layer.TWELVE
        task.config = SimpleNamespace(orochi=config)
        with patch.object(GeneralInvite, 'invite_friends') as automatic:
            task.invite_friends(config.invite_config)
        automatic.assert_not_called()

    def test_manual_party_starts_at_exactly_the_configured_teammate_count(self):
        for number, expected in [(InviteNumber.ONE, 1), (InviteNumber.TWO, 2)]:
            with self.subTest(invite_number=number):
                task = SimpleNamespace(room_type=RoomType.NORMAL_3,
                    _invite_battle_started=Mock(return_value=False),
                    ensure_enter=Mock(return_value=True), ensure_room_type=Mock(),
                    invite_friends=Mock(), is_in_room=Mock(return_value=True),
                    click_fire=Mock(), timer_emoji=None, members=-1)
                for name in ('I_MATCHING', 'I_ADD_1', 'I_ADD_2'):
                    setattr(task, name, getattr(GeneralInvite, name))
                task.screenshot = lambda: setattr(task, 'members', task.members + 1)
                task.appear = lambda rule: ((rule is task.I_ADD_1 and task.members < 1)
                    or (rule is task.I_ADD_2 and task.members < 2))
                conf = InviteConfig(invite_number=number)
                self.assertTrue(GeneralInvite.run_invite(task, conf, is_first=True))
                self.assertEqual(task.members, expected)
                task.click_fire.assert_called_once()

    def test_named_friends_and_other_layers_keep_automatic_invitation(self):
        for layer, name in [(Layer.TWELVE, '指定好友'), (Layer.ELEVEN, '')]:
            task = object.__new__(ScriptTask)
            config = Orochi()
            config.orochi_config.layer = layer
            config.invite_config.friend_1 = name
            task.config = SimpleNamespace(orochi=config)
            with patch.object(GeneralInvite, 'invite_friends') as automatic:
                task.invite_friends(config.invite_config)
            automatic.assert_called_once_with(config.invite_config)


if __name__ == '__main__':
    unittest.main()
