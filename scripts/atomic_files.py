"""Stage complete output bundles, then publish with rollback on write errors."""
import os
from pathlib import Path
import shutil
import tempfile


def write_json(path, value):
    import json
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def publish(stage, output, names):
    """Atomic directory rename for a new target; rollback for existing user folders."""
    stage, output = Path(stage), Path(output)
    if not output.exists():
        os.rename(stage,output)
        return
    installed = []
    try:
        for name in names:
            target = output/name
            if target.exists():
                raise FileExistsError(f'Результат уже существует: {target}')
            # Exclusive creation closes the race with another run using this folder.
            with target.open('xb') as dest:
                installed.append(target)
                with (stage/name).open('rb') as source:
                    shutil.copyfileobj(source,dest)
    except BaseException:
        for target in reversed(installed):
            target.unlink(missing_ok=True)
        raise


def remove_stage(stage, parent):
    stage, parent = Path(stage), Path(parent)
    if stage.is_symlink() or stage.resolve().parent != parent.resolve() or not stage.name.startswith('.normokontrol-result-'):
        raise ValueError('Некорректный путь временной папки результата.')
    if stage.exists():
        shutil.rmtree(stage)
