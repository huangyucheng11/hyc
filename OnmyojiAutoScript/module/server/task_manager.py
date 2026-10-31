"""Task overview and queue controls used by the local OASX interface."""
import asyncio
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from module.config.config import Config
from module.config.config_model import ConfigModel
from module.config.utils import convert_to_underscore, read_file, write_file
from module.server.main_manager import mm
from module.server.script_process import ScriptState

task_manager_app = APIRouter(prefix='/task-manager', tags=['Task manager'])
_locks = defaultdict(asyncio.Lock)


class TaskAction(BaseModel):
    action: str
    enabled: bool | None = None


def config_path(name):
    if name == 'template' or name not in mm.all_script_files():
        raise HTTPException(404, '配置不存在')
    return Path('config') / f'{name}.json'


def task_rows(data):
    rows = []
    for key, value in data.items():
        if not isinstance(value, dict) or 'scheduler' not in value:
            continue
        scheduler = value['scheduler']
        rows.append({'name': ConfigModel.type(key), 'key': key,
                     'enabled': scheduler['enable'], 'next_run': str(scheduler['next_run']),
                     'priority': scheduler['priority']})
    return rows


def overview(name):
    data = ConfigModel(name).model_dump()
    process = mm.script_process.get(name)
    state = process.state if process else ScriptState.INACTIVE
    # A persisted running_task can outlive a subprocess after a device error.
    running = data.get('running_task', '') if state in (ScriptState.RUNNING, ScriptState.PAUSED) else ''
    rows = task_rows(data)
    now = datetime.now().replace(microsecond=0)
    for row in rows:
        row['running'] = row['name'] == running
        row['due'] = datetime.strptime(row['next_run'], '%Y-%m-%d %H:%M:%S') <= now
    return {'tasks': rows, 'state': int(state), 'running': running,
            'enabled_count': sum(row['enabled'] for row in rows), 'total': len(rows)}


async def broadcast(name):
    config = Config(name)
    config.update_scheduler()
    process = mm.script_process.get(name)
    if not process:
        return
    # Do not call get_next(): an empty queue is valid in the management UI.
    running = config.model.running_task if process.state in (ScriptState.RUNNING, ScriptState.PAUSED) else ''
    schedule = {'running': {}, 'pending': [], 'waiting': []}
    for task in config.pending_task + config.waiting_task:
        item = {'name': task.command, 'next_run': str(task.next_run)}
        if task.command == running:
            schedule['running'] = item
        elif task in config.pending_task:
            schedule['pending'].append(item)
        else:
            schedule['waiting'].append(item)
    await process.broadcast_state({'schedule': schedule})


@task_manager_app.get('/{name}')
async def get_tasks(name: str):
    config_path(name)
    return overview(name)


@task_manager_app.post('/{name}/reset-times')
async def reset_times(name: str):
    return await mutate(name, None, TaskAction(action='reset'))


@task_manager_app.post('/{name}/{task}')
async def change_task(name: str, task: str, body: TaskAction):
    if body.action not in ('toggle', 'skip', 'remove'):
        raise HTTPException(400, '不支持的任务操作')
    if body.action == 'toggle' and body.enabled is None:
        raise HTTPException(400, '需要提供启用状态')
    return await mutate(name, task, body)


async def mutate(name, task, body):
    path = config_path(name)
    async with _locks[name]:
        model = ConfigModel(name)
        key = convert_to_underscore(task) if task else None
        if key and key not in {row['key'] for row in task_rows(model.model_dump())}:
            raise HTTPException(404, '任务不存在')
        process = mm.script_process.get(name)
        was_running = process is not None and process.state == ScriptState.RUNNING
        if process:
            # Prevent an active task from overwriting an edited schedule on completion.
            await process.stop()
        backup = Path('config/task_backups')
        backup.mkdir(exist_ok=True)
        backup_file = backup / f'{name}-{datetime.now():%Y%m%d-%H%M%S-%f}.json'
        write_file(str(backup_file), read_file(str(path)))
        try:
            model = ConfigModel(name)
            data = read_file(str(path))
            defaults = model.model_dump()
            if body.action == 'reset':
                now = datetime.now().replace(microsecond=0)
                for row in task_rows(defaults):
                    entry = data.setdefault(row['key'], defaults[row['key']])
                    entry.setdefault('scheduler', defaults[row['key']]['scheduler'])['next_run'] = str(now)
            elif body.action in ('toggle', 'remove'):
                entry = data.setdefault(key, defaults[key])
                entry.setdefault('scheduler', defaults[key]['scheduler'])['enable'] = body.enabled if body.action == 'toggle' else False
            else:
                # Reuse the task's normal success interval / server reset policy.
                next_run = Config(name).task_delay(task=task, success=True, persist=False)
                entry = data.setdefault(key, defaults[key])
                entry.setdefault('scheduler', defaults[key]['scheduler'])['next_run'] = str(next_run)
            data['running_task'] = ''
            write_file(str(path), data)
            if was_running and any(row['enabled'] for row in task_rows(ConfigModel(name).model_dump())):
                await process.start()
            await broadcast(name)
            result = overview(name)
            result['backup'] = str(backup_file)
            return result
        except Exception:
            write_file(str(path), read_file(str(backup_file)))
            raise
