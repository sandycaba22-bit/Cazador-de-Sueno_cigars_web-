"""Escritura atómica (tmp + rename) y lock por archivo para JSON compartidos."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def escribir_json(path: Path, data: dict, *, indent: int = 2) -> None:
    """Lock exclusivo, escribe .tmp y reemplaza. Un corte no deja JSON a medias."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    fd = _tomar_lock(lock)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
        _soltar_lock(fd, lock)


def _tomar_lock(lock: Path):
    for _ in range(40):
        try:
            return os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 30:
                    lock.unlink()
                    continue
            except OSError:
                pass
            time.sleep(0.05)
    try:
        lock.unlink()
    except OSError:
        pass
    return os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)


def _soltar_lock(fd, lock: Path) -> None:
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        lock.unlink()
    except OSError:
        pass
