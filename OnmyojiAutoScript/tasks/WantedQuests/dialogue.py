"""Dismiss recognized secret-zone dialogue during wanted-quest screenshots."""
from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.base.timer import Timer
from module.exception import GameStuckError
from module.logger import logger


class WantedDialogue:
    I_SECRET_DIALOGUE = RuleImage(
        roi_front=(500, 565, 280, 35), roi_back=(480, 545, 320, 75),
        threshold=0.85, method='Template matching',
        file='./tasks/WantedQuests/wq/wq_secret_dialogue.png')
    C_SECRET_DIALOGUE_NEXT = RuleClick(
        roi_front=(540, 620, 180, 35), roi_back=(540, 620, 180, 35),
        name='wanted_secret_dialogue_next')
    SECRET_DIALOGUE_TIMEOUT = 45

    def screenshot(self):
        # Cover battle helpers and navigation recovery as well as secret().
        # Callers must receive a fresh frame after the dialogue has disappeared.
        timeout = None
        clicks = 0
        while True:
            result = super().screenshot()
            if not self.appear(self.I_SECRET_DIALOGUE):
                if timeout is not None:
                    logger.info(f'Wanted secret dialogue finished, advanced {clicks} times')
                return result
            if timeout is None:
                timeout = Timer(self.SECRET_DIALOGUE_TIMEOUT).start()
                logger.info('Wanted secret dialogue detected; advance conversation')
            if timeout.reached():
                raise GameStuckError('悬赏秘闻对话在 45 秒内未结束，请检查对话画面或点击接口')
            if self.click(self.C_SECRET_DIALOGUE_NEXT, interval=0.8):
                clicks += 1
                self._wanted_dialogue_clicks = getattr(self, '_wanted_dialogue_clicks', 0) + 1
                if self._wanted_dialogue_clicks % 8 == 0:
                    # Long conversations legitimately repeat this same safe tap.
                    self.device.click_record_clear()
