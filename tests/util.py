"""Tools for testing."""

import datetime
import os
from pathlib import Path

from rsp_scratchpurger.models.plan import FileReason
from safir.pydantic import _validate_human_timedelta


def set_age(path: Path, whichtime: FileReason, h_age: str) -> None:
    v_age = _validate_human_timedelta(h_age)
    if isinstance(v_age, float):
        age = datetime.timedelta(seconds=v_age)
    elif isinstance(v_age, datetime.timedelta):
        age = v_age
    now = datetime.datetime.now(tz=datetime.UTC)
    then = int((now - age).timestamp())
    stat = path.stat()
    o_atime = stat.st_atime
    o_mtime = stat.st_mtime
    match whichtime:
        case FileReason.ATIME:
            os.utime(path, times=(then, o_mtime))
        case FileReason.CTIME:
            raise ValueError("Cannot set ctime")
        case FileReason.MTIME:
            os.utime(path, times=(o_atime, then))
        case _:
            raise ValueError(f"{then} is not a file access time category")
