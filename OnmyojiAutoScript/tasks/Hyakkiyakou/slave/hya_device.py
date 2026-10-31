import timeit
import numpy as np
from datetime import datetime

from module.base.timer import Timer
from module.logger import logger
from module.base.utils import point2str
from module.exception import RequestHumanTakeover, GameStuckError
from tasks.base_task import BaseTask

from tasks.Hyakkiyakou.config import ScreenshotMethod, ControlMethod

def image_black(img) -> bool:
    return img is None or img.size == 0 or not np.any(img)


class HyaDevice(BaseTask):
    """
    这个类主要是是优化截屏点击速度
    1. 使用特别的method
    2. 扔掉中间的冗余校验
    3. 考虑JIT加速
    我宣布世界上最好的 Linux 系统是 Windows
    """
    hya_screenshot_interval = Timer(0.2)  # 300ms
    hya_fs_check_timer = Timer(3 * 60)

    def _has_window_handle(self):
        return getattr(self.device, 'root_node', None) is not None and bool(
            getattr(self.device, 'root_handle_num', 0))

    def _backend_candidates(self, requested, configured, window_method, cached):
        requested = getattr(requested, 'value', requested)
        configured = getattr(configured, 'value', configured)
        desired = configured if requested == 'auto' else requested
        candidates = [cached, desired, configured, 'ADB' if window_method == 'window_background' else 'adb']
        return list(dict.fromkeys(method for method in candidates if method and method != 'auto'
                                  and (method != window_method or self._has_window_handle())))

    def fast_screenshot(self, screenshot: ScreenshotMethod = ScreenshotMethod.AUTO):
        self.hya_screenshot_interval.wait()
        self.hya_screenshot_interval.reset()
        methods = self.device.screenshot_methods
        previous = getattr(self, '_hya_capture_backend', None)
        candidates = self._backend_candidates(screenshot, self.config.script.device.screenshot_method,
                                              'window_background', previous)
        failures = []
        for method in candidates:
            capture = methods.get(method)
            if capture is None:
                continue
            try:
                frame = capture()
                if image_black(frame):
                    raise ValueError('截图为空或全黑')
                if frame.shape[:2] != (720, 1280):
                    raise ValueError(f'截图尺寸为 {frame.shape[1]}x{frame.shape[0]}，需要 1280x720')
            except Exception as error:
                failures.append(f'{method}: {error}')
                logger.warning(f'Hyakkiyakou screenshot {method} failed, try fallback: {error}')
                continue
            self.device.image = frame
            self._hya_capture_backend = method
            if previous != method:
                logger.info(f'Hyakkiyakou screenshot backend: {method}')
            break
        else:
            raise RequestHumanTakeover('百鬼截图检查失败：' + '; '.join(failures))
        if self.hya_fs_check_timer.reached():
            logger.error('Fast screenshot check timer reached')
            logger.error('Hyakkiyakou has not ended in three minutes, please check the game')
            raise GameStuckError
        if self.config.script.error.save_error:
            self.device.screenshot_deque.append({'time': datetime.now(), 'image': self.device.image})
        return self.device.image

    def fast_click(self, x: int, y: int, control_method: ControlMethod = ControlMethod.AUTO) -> None:
        logger.info(
            'Click %s @ %s' % (point2str(x, y), 'Click')
        )
        previous = getattr(self, '_hya_control_backend', None)
        candidates = self._backend_candidates(control_method, self.config.script.device.control_method,
                                              'window_message', previous)
        failures = []
        for method in candidates:
            click = self.device.click_methods.get(method) or self.device.click_methods.get(method.upper())
            if click is None:
                continue
            try:
                if method == 'window_message':
                    click(x=x, y=y, fast=True)
                else:
                    click(x=x, y=y)
            except Exception as error:
                failures.append(f'{method}: {error}')
                logger.warning(f'Hyakkiyakou input {method} failed, try fallback: {error}')
                continue
            self._hya_control_backend = method
            if previous != method:
                logger.info(f'Hyakkiyakou input backend: {method}')
            return
        raise RequestHumanTakeover('百鬼点击检查失败：' + '; '.join(failures))

    def prepare_fast_io(self, screenshot, control_method, interval):
        """Check capture before consuming a ticket; input selection sends no tap."""
        if not 100 < interval < 1000:
            raise RequestHumanTakeover('百鬼截图间隔必须大于 100 且小于 1000 毫秒')
        self._hya_capture_backend = None
        self._hya_control_backend = None
        self.set_fast_screenshot_interval(interval)
        self.hya_fs_check_timer = Timer(3 * 60).start()
        self.fast_screenshot(screenshot)
        candidates = self._backend_candidates(control_method, self.config.script.device.control_method,
                                              'window_message', None)
        available = [method for method in candidates if
                     self.device.click_methods.get(method) is not None or
                     self.device.click_methods.get(method.upper()) is not None]
        if not available:
            raise RequestHumanTakeover('没有可用的百鬼点击方式，请检查设备控制设置')
        self._hya_control_backend = available[0]
        logger.info(f'Hyakkiyakou input backend: {available[0]}')

    def set_fast_screenshot_interval(self, interval: float):
        """

        @param interval: ms
        @return:
        """
        self.hya_screenshot_interval = Timer(interval / 1000.)


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    hd = HyaDevice(c, d)

    # def screenshot():
    #     global hd
    #     # hd.fast_screenshot()
    #     hd.fast_click(420, 370)
    #     hd.fast_click(750, 400)
    # execution_time = timeit.timeit(screenshot, number=50)
    # print(f"执行总的时间: {execution_time * 1000} ms")

    hd.fast_screenshot()

