"""Private atomic local state. Nothing here belongs in version control."""
import json
import os
import tempfile
from pathlib import Path


def private_directory(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise ValueError("状态目录不能是符号链接")
    os.chmod(directory, 0o700)
    return directory


def save_json(path, value):
    path = Path(path)
    private_directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".wechat-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(262145)
    if len(raw) > 262144:
        raise ValueError("本地状态文件过大")
    return json.loads(raw)
