# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import re
import copy
from pathlib import Path

from module.logger import logger
from module.config.utils import read_file, write_file

class ConfigManager:

    @staticmethod
    def all_script_files() -> list[str]:
        """
        获取所有的脚本文件 除了tmplate
        :return: ['oas1', 'oas2']
        """
        # 获取某个路径的所有json文件名
        config_path = Path.cwd() / 'config'
        json_files = config_path.glob('*.json')
        result = []
        for json in json_files:
            if json.stem == 'template':
                continue
            result.append(json.stem)
        if len(result) == 0:
            # 如果没有脚本文件 则创建一个
            ConfigManager.copy(file='oas1', template='template')
            result.append('oas1')
        result.sort()
        return result

    @staticmethod
    def all_json_file() -> list:
        """
        获取所有的json文件
        :return: ['oas1', 'oas2']
        """
        # 获取某个路径的所有json文件名
        config_path = Path.cwd() / 'config'
        json_files = config_path.glob('*.json')
        result = []
        for json in json_files:
            if json.stem == 'template':
                result.insert(0, json.stem)
            else:
                result.append(json.stem)
        return result

    @staticmethod
    def copy(file: str, template: str = 'template', device_serial: str = None,
             package_name: str = None) -> None:
        """
        复制一个配置文件
        :param file:  不带json后缀
        :param template:
        :return:
        """
        config_path = Path.cwd() / 'config'
        if not re.fullmatch(r'[\w-]+', file) or file == 'template':
            raise ValueError('配置名称只能使用字母、数字、中文、下划线和短横线')
        if not re.fullmatch(r'[\w-]+', template):
            raise ValueError('无效的模板名称')
        template_path = config_path / f'{template}.json'
        file_path = config_path / f'{file}.json'
        if file_path.exists():
            raise ValueError('同名配置已经存在')
        if not template_path.is_file():
            raise ValueError('复制来源不存在')
        from tasks.Script.config_device import PackageName
        from module.device.local_emulators import list_mumu_instances
        if package_name is not None and package_name not in {package.value for package in PackageName}:
            raise ValueError('不支持的客户端包名')
        selected_device = None
        if device_serial:
            selected_device = next((row for row in list_mumu_instances(check_online=False)
                                    if row['serial'] == device_serial), None)
            if not selected_device:
                raise ValueError('未找到所选 MuMu 实例，请刷新实例列表后重试')
        data = read_file(str(template_path))
        data['config_name'] = file
        data['running_task'] = ''
        if template == 'template':
            # New profiles share a connection only when there is one unambiguous
            # local device. Task settings still come from the clean template.
            devices = {}
            for existing in sorted(config_path.glob('*.json')):
                if existing.stem == 'template':
                    continue
                try:
                    device = read_file(str(existing)).get('script', {}).get('device', {})
                except (OSError, ValueError):
                    continue
                serial = device.get('serial', 'auto')
                if serial and serial != 'auto':
                    devices.setdefault(serial, device)
            if len(devices) == 1:
                device = copy.deepcopy(next(iter(devices.values())))
                device['package_name'] = 'auto'
                data.setdefault('script', {})['device'] = device
        device = data.setdefault('script', {}).setdefault('device', {})
        if selected_device:
            for key in ('serial', 'emulatorinfo_type', 'emulatorinfo_name', 'emulatorinfo_path'):
                device[key] = selected_device[key]
            device['handle'] = ''
            # Stable across Android versions; the user may opt into faster IPC later.
            device['screenshot_method'] = 'ADB'
        if package_name is not None:
            device['package_name'] = package_name
        write_file(str(file_path), data)
        logger.info(f'copy {template_path} to {file_path}')


    @staticmethod
    def generate_script_name() -> str:
        """
        生成一个新的配置的名字
        :return:
        """
        all_script_files = ConfigManager.all_script_files()
        if not all_script_files:
            return 'oas1'

        script_numbers = []
        for script_file in all_script_files:
            match = re.search(r'\d+', script_file)
            if match:
                script_number = int(match.group())
                script_numbers.append(script_number)

        if not script_numbers:
            return 'oas1'
        script_numbers.sort()
        new_script_number = script_numbers[-1] + 1
        return f'oas{new_script_number}'

    @staticmethod
    def rename(old_name: str, new_name: str) -> bool:
        """
        重命名一个配置文件
        :param old_name: 旧的配置文件名称
        :param new_name: 新的配置文件名称
        :return: True or False
        """
        config_path = Path.cwd() / 'config'
        old_path = config_path / f'{old_name}.json'
        new_path = config_path / f'{new_name}.json'
        if not old_path.exists():
            logger.error(f'{old_path} is not exists')
            return False
        if new_path.exists():
            logger.error(f'{new_path} is exists')
            return False
        try:
            old_path.rename(new_path)
            logger.info(f'rename {old_path} to {new_path}')
            return True
        except Exception as e:
            logger.error(f'rename {old_path} to {new_path} failed: {e}')
            return False

    @staticmethod
    def delete(file: str) -> bool:
        """
        删除一个配置文件
        :param file:  不带json后缀
        :return: True or False
        """
        config_path = Path.cwd() / 'config'
        file_path = config_path / f'{file}.json'
        if not file_path.exists():
            logger.error(f'{file_path} is not exists')
            return False
        try:
            file_path.unlink()
            logger.info(f'delete {file_path}')
            return True
        except Exception as e:
            logger.error(f'delete {file_path} failed: {e}')
            return False
