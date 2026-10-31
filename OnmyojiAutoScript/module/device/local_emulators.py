"""Discover MuMu multi-instances using their actual configured ADB ports."""
import json
import socket
import subprocess
import sys
from pathlib import Path


def installation_paths():
    paths = set()
    for config in Path('config').glob('*.json'):
        try:
            data = json.loads(config.read_text(encoding='utf-8'))
            path = data.get('script', {}).get('device', {}).get('emulatorinfo_path')
            if path:
                paths.add(path)
        except (OSError, ValueError):
            continue
    if sys.platform == 'win32':
        from module.device.platform2.emulator_windows import EmulatorManager
        paths.update(emulator.path for emulator in EmulatorManager().all_emulators)
    return paths


def list_mumu_instances(paths=None, check_online=True):
    instances = {}
    for executable in (installation_paths() if paths is None else paths):
        executable = Path(executable)
        root = executable.parent.parent
        for folder in sorted((root / 'vms').glob('MuMuPlayer*')):
            try:
                config = json.loads((folder / 'configs/vm_config.json').read_text(encoding='utf-8'))
                port = int(config['vm']['nat']['port_forward']['adb']['host_port'])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if not 0 < port < 65536:
                continue
            serial = f'127.0.0.1:{port}'
            online = False
            if check_online:
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                        online = True
                except OSError:
                    pass
            instances[serial] = {'name': folder.name, 'serial': serial, 'online': online,
                                 'emulatorinfo_type': 'MuMuPlayer12', 'emulatorinfo_name': folder.name,
                                 'emulatorinfo_path': executable.as_posix()}
    return sorted(instances.values(), key=lambda row: row['name'])


def connect_instances():
    adb = Path(sys.executable).parent / 'Lib/site-packages/adbutils/binaries/adb.exe'
    for instance in list_mumu_instances():
        if instance['online']:
            try:
                result = subprocess.run([str(adb), 'connect', instance['serial']],
                                        capture_output=True, text=True, timeout=5)
                print(f"{instance['name']}: {result.stdout.strip()}")
            except (OSError, subprocess.TimeoutExpired) as error:
                print(f"{instance['name']}: {error}")


if __name__ == '__main__':
    connect_instances()
