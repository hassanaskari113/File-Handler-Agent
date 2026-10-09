"""Runs ONE python file with a guard against touching anything outside WORK_DIR.

Usage (done by tools.execute_file):  python sandbox_runner.py <WORK_DIR> <script.py> [args...]

A Python audit hook is installed before the script starts. It blocks (PermissionError):
  * writing / deleting / renaming / creating anything outside WORK_DIR
  * reading anything outside WORK_DIR, except the Python install itself (stdlib, site-packages)
  * launching other programs (subprocess, os.system, exec/spawn, fork), symlinks, ctypes loading
"""

import os
import runpy
import sys
import sysconfig
import traceback

WORK = os.path.normcase(os.path.realpath(sys.argv[1]))
TARGET = os.path.realpath(sys.argv[2])
ARGS = sys.argv[3:]

_py = {
    sys.prefix,
    sys.base_prefix,
    sys.exec_prefix,
    sys.base_exec_prefix,
    os.path.dirname(os.__file__),
}
_py.update(v for v in sysconfig.get_paths().values())
READ_OK = [os.path.normcase(os.path.realpath(p)) for p in _py if p]

_busy = False


def _inside(path, roots):
    try:
        p = os.path.normcase(os.path.realpath(path))
        return any(os.path.commonpath([p, r]) == r for r in roots)
    except (ValueError, OSError):
        return False


def _as_path(x):
    if isinstance(x, bytes):
        return os.fsdecode(x)
    if isinstance(x, (str, os.PathLike)):
        return os.fspath(x)
    return None


def _deny(what, path):
    raise PermissionError(
        f"Blocked by sandbox: {what} '{path}' is outside the working folder."
    )


BLOCKED = {
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.posix_spawn",
    "os.spawn",
    "os.fork",
    "os.forkpty",
    "os.startfile",
    "os.symlink",
    "os.link",
    "os.chroot",
    "ctypes.dlopen",
    "ctypes.dlsym",
    "ctypes.call_function",
}
WRITE_EVENTS = {
    "os.remove",
    "os.rmdir",
    "os.mkdir",
    "os.rename",
    "os.chmod",
    "os.chown",
    "os.truncate",
    "os.utime",
    "os.mkfifo",
    "os.mknod",
    "os.setxattr",
    "os.removexattr",
    "shutil.copyfile",
    "shutil.copymode",
    "shutil.copystat",
    "shutil.copytree",
    "shutil.move",
    "shutil.rmtree",
    "shutil.make_archive",
    "shutil.unpack_archive",
    "os.chdir",
}


def hook(event, args):
    global _busy
    if _busy:
        return
    _busy = True
    try:
        if event in BLOCKED:
            raise PermissionError(f"Blocked by sandbox: '{event}' is not allowed.")
        if event == "open":
            path, mode, flags = (list(args) + [None, None])[:3]
            p = _as_path(path)
            if p is None or p == os.devnull:
                return
            mode = str(mode or "r")
            writing = any(c in mode for c in "wax+")
            if isinstance(flags, int) and flags & (
                os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
            ):
                writing = True
            if writing:
                if not _inside(p, [WORK]):
                    _deny("writing", p)
            elif not _inside(p, [WORK] + READ_OK):
                _deny("reading", p)
        elif event in ("os.listdir", "os.scandir"):
            p = _as_path(args[0]) if args else None
            if p is not None and not _inside(p, [WORK] + READ_OK):
                _deny("listing", p)
        elif event in WRITE_EVENTS:
            for a in args:
                p = _as_path(a)
                if p is not None and not _inside(p, [WORK]):
                    _deny("changing", p)
    finally:
        _busy = False


def main():
    os.chdir(WORK)
    sys.path[0] = WORK  # keep the project's own source folder out of the import path
    sys.argv = [TARGET] + ARGS
    sys.addaudithook(hook)
    try:
        runpy.run_path(TARGET, run_name="__main__")
    except SystemExit:
        raise
    except BaseException as e:  # show a clean traceback (without runner frames)
        tb = e.__traceback__
        while tb and os.path.realpath(tb.tb_frame.f_code.co_filename) != TARGET:
            tb = tb.tb_next
        traceback.print_exception(type(e), e, tb or e.__traceback__)
        sys.exit(1)


if __name__ == "__main__":
    main()
