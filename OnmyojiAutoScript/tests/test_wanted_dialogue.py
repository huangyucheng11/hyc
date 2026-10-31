"""Replay the actual stuck dialogue and unrelated game screens without game input."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from module.exception import GameStuckError
from tasks.WantedQuests.dialogue import WantedDialogue
from tasks.WantedQuests.script_task import ScriptTask


def screen(name):
    path = Path(__file__).parent / 'fixtures/wanted_dialogue' / f'{name}.png'
    crop = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[520:720, 450:850] = crop
    return frame


class ReplayScreens:
    def __init__(self, frames, working_input=True):
        self.frames, self.working_input = frames, working_input
        self.index, self.captures = 0, 0
        self.taps = []
        self.device = SimpleNamespace(image=None, click_record_clear=Mock())

    def screenshot(self):
        self.captures += 1
        self.device.image = self.frames[self.index]

    def appear(self, rule):
        return rule.match(self.device.image)

    def click(self, rule, interval):
        self.taps.append(rule.name)
        if self.working_input:
            self.index = min(self.index + 1, len(self.frames) - 1)
        return True


class ReplayTask(WantedDialogue, ReplayScreens):
    pass


class WantedDialogueTests(unittest.TestCase):
    def test_real_failure_frames_match_but_unrelated_screens_do_not(self):
        rule = WantedDialogue.I_SECRET_DIALOGUE
        for name in ('dialogue', 'dialogue_first_failure'):
            with self.subTest(name=name):
                self.assertTrue(rule.match(screen(name)), rule.last_score)
        for name in ('buff_popup', 'flower_menu', 'hyakki_round'):
            with self.subTest(name=name):
                self.assertFalse(rule.match(screen(name)), rule.last_score)

    def test_actual_wanted_task_uses_dialogue_handling_in_all_screenshot_loops(self):
        self.assertIs(ScriptTask.screenshot, WantedDialogue.screenshot)

    def test_post_battle_dialogue_advances_and_returns_a_fresh_non_dialogue_frame(self):
        final = screen('flower_menu')
        task = ReplayTask([screen('dialogue_first_failure'), screen('dialogue'), final])
        task.screenshot()
        self.assertEqual(task.taps, ['wanted_secret_dialogue_next'] * 2)
        self.assertEqual(task.captures, 3)
        self.assertIs(task.device.image, final)

    def test_restart_navigation_also_clears_leftover_dialogue(self):
        task = ReplayTask([screen('dialogue'), screen('buff_popup')])
        # Navigation's screenshot sees dialogue left behind by the previous run.
        task.screenshot()
        self.assertEqual(len(task.taps), 1)
        self.assertFalse(task.appear(task.I_SECRET_DIALOGUE))

    def test_non_dialogue_screen_sends_no_input(self):
        task = ReplayTask([screen('flower_menu')])
        task.screenshot()
        self.assertEqual(task.taps, [])
        self.assertEqual(task.captures, 1)

    def test_long_dialogue_does_not_trigger_repeated_click_guard(self):
        task = ReplayTask([screen('dialogue')] * 9 + [screen('flower_menu')])
        task.screenshot()
        self.assertEqual(len(task.taps), 9)
        task.device.click_record_clear.assert_called_once()

    def test_unresponsive_dialogue_times_out_instead_of_clicking_forever(self):
        task = ReplayTask([screen('dialogue')], working_input=False)
        with patch('tasks.WantedQuests.dialogue.Timer') as timer:
            timer.return_value.start.return_value.reached.side_effect = [False, False, True]
            with self.assertRaisesRegex(GameStuckError, '悬赏秘闻对话'):
                task.screenshot()
        self.assertEqual(len(task.taps), 2)

    def test_dialogue_fades_between_lines_still_allow_a_long_conversation(self):
        task = ReplayTask([screen('dialogue'), screen('flower_menu')])
        for _ in range(9):
            task.index = 0
            task.screenshot()
        self.assertEqual(len(task.taps), 9)
        task.device.click_record_clear.assert_called_once()


if __name__ == '__main__':
    unittest.main()
