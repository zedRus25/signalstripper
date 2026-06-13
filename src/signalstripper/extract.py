from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


class ExtractionError(Exception):
    pass


@contextmanager
def decrypted_db(backup_path: Path, passphrase: str, signalbackup_tools: Path) -> Generator[Path, None, None]:
    """Invokes signalbackup-tools via subprocess, yields path to SQLite DB, wipes on exit."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="signalstripper_"))
    db_path = tmp_dir / "signal.db"
    try:
        _invoke_signalbackup_tools(backup_path, passphrase, db_path, signalbackup_tools)
        yield db_path
    finally:
        _secure_wipe(tmp_dir)


def _invoke_signalbackup_tools(
    backup_path: Path, passphrase: str, out_path: Path, binary: Path
) -> None:
    raise NotImplementedError(
        "Phase 0 (decryption wrapper) is deferred. "
        "Provide a pre-decrypted SQLite DB via --db."
    )


def _secure_wipe(path: Path) -> None:
    if path.is_file():
        size = path.stat().st_size
        with open(path, "r+b") as f:
            f.write(b"\x00" * size)
            f.flush()
            os.fsync(f.fileno())
        path.unlink()
    elif path.is_dir():
        for child in path.iterdir():
            _secure_wipe(child)
        path.rmdir()
