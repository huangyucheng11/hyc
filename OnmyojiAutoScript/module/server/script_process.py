# This Python file uses the following encoding: utf-8
# @author runhey
# 脚本进程
# github https://github.com/runhey
import sys, os
import signal
import multiprocessing
import time
import psutil
from queue import Empty as QueueEmpty
from asyncio import CancelledError, sleep
from enum import Enum

from module.logger import logger
from module.server.config_manager import ConfigManager
from module.server.script_websocket import ScriptWSManager


class ScriptState(int, Enum):
    INACTIVE = 0
    RUNNING = 1
    WARNING = 2
    UPDATING = 3
    PAUSED = 4


class ScriptProcess(ScriptWSManager):

    def __init__(self, config_name: str) -> None:
        super().__init__()
        if config_name not in ConfigManager.all_script_files():
            raise FileNotFoundError(f'{config_name}.json not found')
        self.config_name = config_name  # config_name
        self.log_pipe_out, self.log_pipe_in = multiprocessing.Pipe(False)
        self.state_queue = multiprocessing.Queue()
        self.state: ScriptState = ScriptState.INACTIVE
        self._process = None
        self._pause_offset = multiprocessing.Value('d', 0.0, lock=False)
        self._paused_at = None
        self.last_error = ''

    async def start(self):
        if self._process and self._process.is_alive():
            if self.state == ScriptState.PAUSED:
                return await self.resume()
            if self.state == ScriptState.RUNNING:
                await self.broadcast_state({'state': self.state})
                return True
        from module.config.config_model import ConfigModel
        from module.server.main_manager import mm
        serial = ConfigModel(self.config_name).script.device.serial
        if serial and serial != 'auto':
            for name, other in list(mm.script_process.items()):
                if name == self.config_name or other.state not in (ScriptState.RUNNING, ScriptState.PAUSED):
                    continue
                if other._process is None or not other._process.is_alive():
                    continue
                if ConfigModel(name).script.device.serial == serial:
                    message = f'{name} 正在使用模拟器 {serial}，请先停止该配置，或为当前配置选择另一个实例。'
                    logger.warning(message)
                    await self.broadcast_state({'error': message})
                    await self.broadcast_state({'state': self.state})
                    return False
        if self._process and self._process.is_alive():
            await self.stop()
        # A forcibly stopped worker may leave a partial message or an old warning.
        # Start a new channel pair so a fresh run never consumes that old state.
        self.log_pipe_out.close()
        self.log_pipe_in.close()
        self.state_queue.close()
        self.log_pipe_out, self.log_pipe_in = multiprocessing.Pipe(False)
        self.state_queue = multiprocessing.Queue()
        self._pause_offset.value = 0.0
        self._paused_at = None
        self.last_error = ''
        self._process = multiprocessing.Process(target=func,
                                                args=(self.config_name, self.state_queue, self.log_pipe_in, self._pause_offset),
                                                name=self.config_name,
                                                daemon=True
                                                )
        self._process.start()
        self.state = ScriptState.RUNNING
        await self.broadcast_state({'state': self.state})
        return True

    async def _control_failed(self, action, error):
        self.last_error = f'{self.config_name} {action}失败：{error}'
        logger.error(self.last_error)
        if self._process is None or not self._process.is_alive():
            self.state = ScriptState.WARNING
            self._paused_at = None
        await self.broadcast_state({'error': self.last_error})
        await self.broadcast_state({'state': self.state})
        return False

    async def pause(self):
        self.last_error = ''
        if self.state == ScriptState.PAUSED:
            return True
        if self.state != ScriptState.RUNNING:
            return False
        if self._process is None or not self._process.is_alive():
            return await self._control_failed('暂停', '脚本进程已经退出，请重新启动')
        try:
            # Suspend every worker thread, including fast input and inference.
            # The server and emulator remain responsive.
            psutil.Process(self._process.pid).suspend()
        except (psutil.Error, OSError) as error:
            return await self._control_failed('暂停', error)
        self._paused_at = time.monotonic()
        self.state = ScriptState.PAUSED
        logger.info(f'Script {self.config_name} paused')
        await self.broadcast_state({'state': self.state})
        return True

    async def resume(self):
        self.last_error = ''
        if self.state != ScriptState.PAUSED:
            return False
        if self._process is None or not self._process.is_alive():
            return await self._control_failed('继续运行', '脚本进程已经退出，请重新启动')
        previous_offset = self._pause_offset.value
        self._pause_offset.value += time.monotonic() - self._paused_at
        try:
            psutil.Process(self._process.pid).resume()
        except (psutil.Error, OSError) as error:
            self._pause_offset.value = previous_offset
            return await self._control_failed('继续运行', error)
        self._paused_at = None
        self.state = ScriptState.RUNNING
        logger.info(f'Script {self.config_name} resumed')
        await self.broadcast_state({'state': self.state})
        return True

    async def stop(self):
        self.state = ScriptState.INACTIVE
        await self.broadcast_state({"state": self.state})
        if self._process is None:
            logger.warning(f'Script {self.config_name} process is removed')
            return
        if not self._process.is_alive():
            logger.warning(f'Script {self.config_name} is not running')
            self._process = None
            self._paused_at = None
            return
        # terminate()/kill() also work on a suspended Windows process.
        # Do not resume it here: stopping must not send another game input.
        self._process.terminate()
        self._process.join(timeout=0.7)
        if self._process.is_alive():
            logger.error(f'Script {self.config_name} subprocess terminate failed')
            self._process.kill()
            self._process.join(timeout=0.7)
        self._process = None
        self._paused_at = None

    async def coroutine_broadcast_state(self):
        try:
            while 1:
                if self.state in (ScriptState.INACTIVE, ScriptState.PAUSED):
                    await sleep(1)
                    continue
                await sleep(0.1)
                if self.state in (ScriptState.INACTIVE, ScriptState.PAUSED):
                    continue
                try:
                    if self.state == ScriptState.RUNNING and self._process and not self._process.is_alive():
                        self.state = ScriptState.WARNING
                        await self.broadcast_state({'state': self.state})
                    if self.state_queue.empty():
                        await sleep(1)
                        continue
                    data = self.state_queue.get_nowait()
                    if not data:
                        await sleep(0.5)
                        continue
                    if 'state' in data and data['state'] == ScriptState.WARNING:
                        self.state = ScriptState.WARNING
                    await self.broadcast_state(data)
                except QueueEmpty as e:
                    logger.warning(f'QueueEmpty: {e}')
                    await sleep(0.5)
                    continue
                except Exception as e:
                    logger.error(f'Error: {e}')
                    continue
        except CancelledError as e:
            logger.warning(f'{self.config_name} state coroutine is cancelled')
            return

    async def coroutine_broadcast_log(self):
        try:
            while 1:
                if self.state == ScriptState.INACTIVE:
                    await sleep(1)
                    continue
                await sleep(0.05)
                try:
                    if not self.log_pipe_out.poll():
                        await sleep(0.3)
                        continue
                    log = self.log_pipe_out.recv()
                    if not log:
                        await sleep(0.5)
                        continue
                    await self.broadcast_log(log)
                except EOFError as e:
                    await sleep(0.5)
                    logger.warning(f'EOFError: {e}')
                    continue
                except Exception as e:
                    logger.error(f'Log Error: {e}')
                    continue
        except CancelledError as e:
            logger.warning(f'{self.config_name} log coroutine is cancelled')
            return


def func(config: str, state_queue: multiprocessing.Queue, log_pipe_in, pause_offset=None) -> None:
    from module.base.timer import set_pause_offset
    set_pause_offset(pause_offset)
    def signal_handler(signum, frame):
        logger.info(f'Script {config} received signal {signum}, exiting gracefully')
        log_pipe_in.close()
        state_queue.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    def start_log() -> None:
        try:
            from module.logger import set_file_logger, set_func_logger
            set_file_logger(name=config)
            set_func_logger(log_pipe_in.send)
        except Exception as e:
            logger.exception(f'Start log error')
            logger.error(f'Error: {e}')
            raise
    start_log()
    import time
    try:
        # while 1:
        #     time.sleep(1)
        #     logger.info(f'Script {config} is running')
        #     state_queue.put({"state": ScriptState.RUNNING})
        from script import Script
        script = Script(config_name=config)
        script.state_queue = state_queue
        script.loop()
    except SystemExit as e:
        logger.info(f'Script {config} process exit')
        logger.error(f'Error: {e}')
        state_queue.put({"state": ScriptState.WARNING})
        time.sleep(0.1)
        exit(-1)
    except Exception as e:
        logger.exception(f'Run script {config} error')
        logger.error(f'Error: {e}')
        raise


if __name__ == '__main__':
    p = ScriptProcess('oas1')
    p.start()
    from time import sleep
    sleep(10)
    logger.info(p._process.exitcode)


