"""Select the dungeon in the courtyard's create-team dialog."""

from module.atom.image import RuleImage
from module.atom.list import RuleList
from module.base.timer import Timer
from module.exception import GameStuckError
from module.logger import logger


class OrochiTeamEntry:
    # The highlighted middle row is the selected value, not another visible row.
    I_TEAM_SOUL_SELECTED = RuleImage(
        roi_front=(370, 284, 73, 34), roi_back=(350, 280, 115, 43),
        threshold=0.85, method='Template matching',
        file='./tasks/Orochi/o/o_team_soul_selected.png')
    I_TEAM_SHENFA_SELECTED = RuleImage(
        roi_front=(604, 283, 70, 37), roi_back=(585, 280, 110, 43),
        threshold=0.85, method='Template matching',
        file='./tasks/Orochi/o/o_team_shenfa_selected.png')

    L_TEAM_DUNGEON = RuleList(
        folder='./tasks/Orochi', direction='vertical', mode='ocr',
        roi_back=(300, 186, 205, 232), size=(185, 45),
        array=['探索（困难）', '觉醒业火轮', '觉醒风转符', '觉醒水灵鲤', '觉醒天雷鼓',
               '御魂', '日轮之陨', '永生之海', '彼世逢魔', '妖气封印', '经验妖怪',
               '金币妖怪', '年兽', '石距', '愤怒的石距', '结界突破', '真·八岐大蛇',
               '对弈社', '斗町', '连携召唤', '契灵之境'])
    L_TEAM_SOUL_LAYER = RuleList(
        folder='./tasks/Orochi', direction='vertical', mode='ocr',
        roi_back=(540, 186, 200, 232), size=(180, 45),
        array=['壹层', '贰层', '叁层', '肆层', '伍层', '陆层', '柒层', '捌层',
               '玖层', '拾层', '悲鸣', '神罚', '虚无'])

    def select_shenfa_team(self):
        """Leave a verified 御魂/神罚 dialog open for privacy and confirmation."""
        self._select_team_value(self.L_TEAM_DUNGEON, '御魂', self.I_TEAM_SOUL_SELECTED)
        self._select_team_value(self.L_TEAM_SOUL_LAYER, '神罚', self.I_TEAM_SHENFA_SELECTED)
        self.screenshot()
        if not (self.appear(self.I_TEAM_SOUL_SELECTED) and self.appear(self.I_TEAM_SHENFA_SELECTED)):
            raise GameStuckError('神罚组队：副本或难度确认失败，取消建房')
        logger.info('神罚组队：已确认副本为御魂、难度为神罚')

    def _select_team_value(self, options, name, selected):
        for _ in range(24):
            self.screenshot()
            if not (self.appear(self.I_CREATE_ENSURE) or self.appear(self.I_CREATE_ENSURE_2)):
                raise GameStuckError('神罚组队：未检测到创建队伍窗口')
            if self.appear(selected):
                return
            pos = options.ocr_appear(self.device.image, name)
            x, y, w, h = options.roi_back
            # These are scroll wheels: tapping an off-centre label does not select it.
            center_x, center_y = x + w // 2, y + h // 2
            if isinstance(pos, tuple) and x <= pos[0] < x + w and y <= pos[1] < y + h:
                delta = max(-90, min(90, center_y - pos[1]))
            elif isinstance(pos, int) and pos:
                delta = -45 if pos > 0 else 45
            else:
                raise GameStuckError(f'神罚组队：创建队伍窗口未找到“{name}”')
            if abs(delta) > 5:
                # Use a slow drag: quick minitouch swipes add inertia and skip rows.
                # Do not use RuleList.swipe_pos, whose centre formula assumes x/y=0.
                self.device.swipe_adb(
                    (center_x, center_y), (center_x + 1, center_y + delta), duration=0.65)
            # Wait for the wheel to settle, rather than repeatedly tapping a moving row.
            settled = Timer(0.8).start()
            while not settled.reached():
                self.screenshot()
                if self.appear(selected):
                    return
        raise GameStuckError(f'神罚组队：未能选中“{name}”，取消建房')
