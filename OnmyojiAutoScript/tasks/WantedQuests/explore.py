from time import sleep

from module.atom.image import RuleImage
from module.base.timer import Timer
from module.logger import logger
from tasks.Exploration.base import BaseExploration, Scene
from tasks.Exploration.version import HighLight


class ExploreWantedBoss(Exception):
    # 出现一种情况，要求的怪是仅仅最后的Boss，其他小怪不是
    pass


class WQExplore(BaseExploration, HighLight):
    _cnt_exploration: int = 0

    def explore(self, goto: RuleImage, num: int):
        logger.info(f'Start exploring with number: {num}')
        explore_init = False
        explore_only_boss: bool = True
        _cnt_exploration = 0
        search_fail_cnt = 0
        search_fail_timer = Timer(1.5)  # 空闲这么久没看到悬赏高亮，就向右滑动找怪
        unknown_timer = Timer(2.5)  # 未知场景(如奖励结算页)空等超时后点击屏幕继续
        swipe_cnt = 0  # 本次进图滑动次数，仅用于日志
        # https://github.com/runhey/OnmyojiAutoScript/pull/1697 云景阆苑 皮肤
        from tasks.Component.Costume.config import MainType
        if self.config.model.global_game.costume_config.costume_main_type == MainType.COSTUME_MAIN_13:
            self.TEMPLATE_GIF.match = self.TEMPLATE_GIF.match_with_multi_scale
            logger.info("Costume '云景阆苑' detected, enable multi-scale matching for highlight")
        else:
            self.TEMPLATE_GIF.match = self.TEMPLATE_GIF.match_origin
        while 1:
            self.screenshot()
            if self.appear(self.I_UI_BACK_YELLOW) and self.appear(self.I_E_EXPLORATION_CLICK):
                break
            if self.appear_then_click(goto, interval=2):
                continue

        while 1:
            scene = self.get_current_scene(reuse_screenshot=False)
            # 进入探索
            if scene == Scene.ENTRANCE:
                if _cnt_exploration >= num:
                    logger.info('Execution exploration end')
                    # --退出到探索大世界--
                    self.ui_click(self.I_UI_BACK_YELLOW, stop=self.I_CHECK_EXPLORATION, interval=4)
                    if explore_only_boss:
                        raise ExploreWantedBoss
                    break
                self.ui_click(self.I_E_EXPLORATION_CLICK, stop=self.I_E_SETTINGS_BUTTON)
                continue
            # 探索大世界
            elif scene == Scene.WORLD:
                self.wait_until_stable(
                    self.I_CHECK_EXPLORATION,
                    timer=Timer(limit=0.5, count=2),
                    timeout=Timer(2, count=10)
                )
                curr_scene = self.get_current_scene(reuse_screenshot=False)
                if curr_scene == Scene.WORLD and _cnt_exploration >= num:
                    logger.info('All Done')
                    break
                continue
            # 探索里面
            elif scene == Scene.MAIN:
                # if not explore_init:
                #     count = 0
                #     while count < 5:
                #         if self.appear(self.I_E_AUTO_ROTATE_ON):
                #             break
                #         if self.appear(self.I_E_AUTO_ROTATE_OFF, interval=1.5):
                #             self.click(self.I_E_AUTO_ROTATE_OFF)
                #             count += 1
                #     explore_init = True
                #     continue
                # 小纸人
                if self.appear(self.I_BATTLE_REWARD):
                    if self.ui_get_reward(self.I_BATTLE_REWARD):
                        continue
                # boss
                if self.appear(self.I_BOSS_BATTLE_BUTTON):
                    if self.fire(self.I_BOSS_BATTLE_BUTTON):
                        logger.info(f'Boss battle, minions cnt {self.minions_cnt}')
                        _cnt_exploration += 1
                        explore_only_boss = False
                    continue
                # 小怪
                if self.appear(self.TEMPLATE_GIF) and self.fire(self.TEMPLATE_GIF):
                    explore_only_boss = False
                    logger.info(f'Fight, minions cnt {self.minions_cnt}')
                    continue
                # 向后拉,寻找怪
                # 2026-11-01 修复: 原来用 _match_end(I_SWIPE_END) 判断"已到地图尽头", 实测严重误判——
                #   进图只滑动一次就报 "Animation Stable @ RES_SWIPE_END", 随即 Quit explore,
                #   于是妖怪在右侧时永远走不到, 还会引发 GameTooManyClick / GameStuckError。
                #   改为对比滑动前后画面(与 tasks/Exploration/solo.py 一致)。
                if search_fail_timer.reached():
                    search_fail_timer.reset()
                    before_image = self.device.image
                    self.swipe(self.S_SWIPE_BACKGROUND_RIGHT)
                    sleep(0.3)
                    self.screenshot()
                    unchanged = self.is_swipe_unchanged(before_image, self.device.image)
                    if unchanged:
                        # 单次可能是动画没结束, 再确认一次
                        sleep(0.3)
                        self.screenshot()
                        unchanged = self.is_swipe_unchanged(before_image, self.device.image)
                    # 滑动途中可能弹确认框/进入战斗, 交给下一轮循环判断
                    if self.get_current_scene() != Scene.MAIN:
                        continue
                    if unchanged:
                        logger.info(f'Reached the right boundary after {swipe_cnt} swipes, this area is cleared')
                        _cnt_exploration += 1
                        self.quit_explore()
                        continue
                    self.device.click_record_remove(self.S_SWIPE_BACKGROUND_RIGHT.name)
                    swipe_cnt += 1
                    logger.info(f'Swipe right to look for wanted monster, {swipe_cnt}')
                    continue
                if not search_fail_timer.started():
                    search_fail_timer.start()
            elif scene == Scene.BATTLE_PREPARE:
                self.ui_click_until_disappear(self.I_PREPARE_HIGHLIGHT, interval=0.5)
            elif scene in (Scene.UNKNOWN, Scene.BATTLE_FIGHTING):
                # 2026-10-28: 悬赏完成后会弹出"点击屏幕继续"的奖励结算页,
                # 该页会被判定为 BATTLE_FIGHTING 或 UNKNOWN, 而循环里没有对应分支,
                # 结果是画面静止直到 GameStuckError。这里改为轻点屏幕中间继续。
                if unknown_timer.reached():
                    unknown_timer.reset()
                    logger.info('Unknown/battle scene, tap center to continue')
                    # 2026-11-01: 结算页可能停留较久, 反复点同一个坐标会触发
                    #   GameTooManyClickError(与 swipe 交替时也会), 每次点前清空点击记录
                    self.device.click_record_clear()
                    self.device.click(640, 360, control_name='wq_unknown_continue')
                elif not unknown_timer.started():
                    unknown_timer.start()
                continue


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    from tasks.WantedQuests.assets import WantedQuestsAssets

    config = Config('oas1')
    device = Device(config)
    t = WQExplore(config, device)
    t.explore(goto=WantedQuestsAssets.I_GOTO_1, num=2)
