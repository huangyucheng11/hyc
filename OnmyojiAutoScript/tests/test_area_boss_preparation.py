"""Replay delayed loading and dropped prepare taps without touching the game."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameStuckError
from tasks.AreaBoss.script_task import ScriptTask
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import GeneralBattle


class PreparationReplay(ScriptTask):
    def __init__(self, *, loading=0, preset_seconds=0, accepted_tap=1,
                 animation_frames=0, initial='prepare', locked=False):
        # Keep real battle methods, replacing only time, image recognition and input.
        self.now = 100.0
        self.loaded_at = self.now + loading
        self.preset_seconds = preset_seconds
        self.animation_frames = animation_frames
        self.accepted_tap = accepted_tap
        self.state = initial
        self.frame = None
        self.taps = []
        self.current_count = 1
        self.battle_config = GeneralBattleConfig(preset_enable=True, lock_team_enable=locked)
        self.switches = 0
        self.buffs = 0
        self.device = SimpleNamespace()
        self.green_mark = Mock()
        self.battle_wait = Mock(return_value=True)

    def screenshot(self):
        self.now += 0.5
        if self.now < self.loaded_at:
            self.frame = 'loading'
        elif self.animation_frames and self.switches:
            self.frame = 'animation'
            self.animation_frames -= 1
        else:
            self.frame = self.state

    def is_in_real_battle(self, is_screenshot=True):
        return self.frame == 'battle'

    def is_in_battle(self, is_screenshot=True):
        return self.frame == 'battle'

    def appear(self, rule, **kwargs):
        if rule is self.I_PREPARE_HIGHLIGHT:
            return self.frame == 'prepare'
        return self.frame == 'result' and rule is self.I_WIN

    def is_in_prepare(self, is_screenshot=True):
        return self.frame in ('prepare', 'animation')

    def appear_then_click(self, rule, **kwargs):
        if not self.appear(rule):
            return False
        self.taps.append((rule.name, self.frame))
        if len(self.taps) >= self.accepted_tap:
            self.state = 'battle'
        return True

    def switch_preset_team(self, *args):
        self.switches += 1
        self.now += self.preset_seconds
        # The last image held by switch_preset_team can still contain the popup.
        self.frame = 'preset_popup'

    def check_and_open_buff(self, buff):
        self.buffs += 1


class AreaBossPreparationTests(unittest.TestCase):
    def run_preparation(self, task, *, method=ScriptTask.battle_before, **kwargs):
        with patch('module.base.timer.timer_time', side_effect=lambda: task.now), \
             patch('tasks.Component.GeneralBattle.general_battle.sleep',
                   side_effect=lambda duration: setattr(task, 'now', task.now + duration)):
            return method(task, None, task.battle_config, **kwargs)

    def test_slow_loading_longer_than_old_five_second_window(self):
        task = PreparationReplay(loading=8)
        self.assertTrue(self.run_preparation(task))
        self.assertEqual(len(task.taps), 1)
        self.assertEqual(task.frame, 'battle')

    def test_long_preset_gets_fresh_frame_and_new_start_budget(self):
        task = PreparationReplay(preset_seconds=6, animation_frames=2)
        self.assertTrue(self.run_preparation(task, method=GeneralBattle.battle_before, timeout=5))
        self.assertEqual(task.taps, [(task.I_PREPARE_HIGHLIGHT.name, 'prepare')])
        self.assertEqual(task.switches, 1)
        self.assertEqual(task.buffs, 1)
        self.assertEqual(task.frame, 'battle')

    def test_dropped_first_prepare_tap_is_retried_until_battle_visible(self):
        task = PreparationReplay(preset_seconds=4, animation_frames=2, accepted_tap=2)
        self.assertTrue(self.run_preparation(task))
        self.assertEqual(len(task.taps), 2)
        self.assertEqual(task.switches, 1)
        self.assertEqual(task.frame, 'battle')

    def test_later_boss_does_not_reselect_first_battle_preset(self):
        task = PreparationReplay(accepted_tap=2)
        task.current_count = 2
        self.assertTrue(self.run_preparation(task))
        self.assertEqual(len(task.taps), 2)
        self.assertEqual(task.switches, 0)

    def test_already_in_battle_sends_no_prepare_input(self):
        task = PreparationReplay(initial='battle')
        self.assertTrue(self.run_preparation(task))
        self.assertEqual(task.taps, [])
        self.assertEqual(task.switches, 0)

    def test_fast_battle_already_at_result_can_continue_to_settlement(self):
        task = PreparationReplay(initial='result')
        self.assertTrue(self.run_preparation(task))
        self.assertEqual(task.taps, [])

    def test_locked_team_keeps_existing_automatic_prepare_behavior(self):
        task = PreparationReplay(locked=True)
        self.assertFalse(self.run_preparation(task, method=GeneralBattle.battle_before, timeout=2))
        self.assertEqual(task.taps, [])
        self.assertEqual(task.switches, 0)

    def test_timeout_never_enters_battle_result_wait_loop(self):
        task = PreparationReplay(loading=1000)
        with patch('module.base.timer.timer_time', side_effect=lambda: task.now), \
             patch('tasks.Component.GeneralBattle.general_battle.sleep',
                   side_effect=lambda duration: setattr(task, 'now', task.now + duration)):
            with self.assertRaisesRegex(GameStuckError, '地域鬼王.*超时'):
                task.run_general_battle(task.battle_config)
        task.battle_wait.assert_not_called()
        self.assertEqual(task.taps, [])
        self.assertLess(task.now, 132)


if __name__ == '__main__':
    unittest.main()
