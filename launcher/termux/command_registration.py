"""Register the existing wrapper without opening app data, images or services."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

WRAPPER = b'''#!/bin/sh
PATH="$HOME/.local/share/angmoo-tools/venv/bin:$PATH"
export PATH
exec "$HOME/.local/share/angmoo-tools/venv/bin/python" "$HOME/.local/share/angmoo-tools/angmoo.py" "$@"
'''
TOOL_FILES = ("angmoo.py", "payload.py", "processes.py", "service_logs.py",
              "log_policy.py", "requirements.txt", "command_registration.py", "session_recovery.py")


class RegistrationError(Exception):
    pass


def require(value: object, code: str) -> None:
    if not value:
        raise RegistrationError(code)


def owned_directory(path: Path) -> None:
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and not info.st_mode & 0o022, "unsafe_tools_directory")


def native_prefix(home: Path) -> Path | None:
    """PREFIX alone is not evidence of a native Termux interpreter."""
    android = (sys.platform == "android" or hasattr(sys, "getandroidapilevel")
               or (Path("/system/bin/getprop").is_file() and bool(os.environ.get("TERMUX_VERSION"))))
    if not android:
        require(not os.environ.get("PREFIX", "").startswith(("/data/data/", "/data/user/")),
                "termux_host_python_required")
        return None
    raw = os.environ.get("PREFIX", "")
    require(raw and Path(raw).is_absolute(), "termux_prefix_invalid")
    prefix = Path(raw).resolve(strict=True)
    require(prefix.name == "usr" and home.name == "home" and prefix.parent == home.parent,
            "termux_private_prefix_required")
    require(not str(home).startswith(("/sdcard/", "/storage/", "/mnt/media_rw/")),
            "termux_private_home_required")
    require(Path(sys.base_prefix).resolve() == prefix
            and Path(sys.executable).resolve().is_relative_to(prefix / "bin"),
            "termux_host_python_required")
    for directory in (home, prefix, prefix / "bin"):
        owned_directory(directory)
    return prefix


def private_chain(home: Path, relative: str, *, create: bool = False) -> Path:
    current = home
    owned_directory(current)
    for part in Path(relative).parts:
        current = current / part
        if create:
            current.mkdir(mode=0o700, exist_ok=True)
        if os.path.lexists(current):
            owned_directory(current)
    return current


def wrapper_bytes(wrapper: Path) -> bytes | None:
    if not os.path.lexists(wrapper):
        return None
    info = wrapper.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and not info.st_mode & 0o022 and info.st_size <= len(WRAPPER) + 4,
            "command_wrapper_conflict")
    raw = wrapper.read_bytes()
    require(raw in (WRAPPER, WRAPPER.replace(b"\n", b"\r\n")), "command_wrapper_conflict")
    return raw


def same_link(command: Path, wrapper: Path) -> bool:
    try:
        return command.is_symlink() and command.resolve() == wrapper.resolve()
    except (OSError, RuntimeError):
        return False


def preflight(home: Path, prefix: Path | None) -> Path:
    wrapper = private_chain(home, ".local/bin") / "angmoo"
    private_chain(home, ".local/share/angmoo-tools")
    wrapper_bytes(wrapper)
    if prefix is not None:
        command = prefix / "bin/angmoo"
        require(not os.path.lexists(command) or same_link(command, wrapper), "command_name_conflict")
        directories = [Path(value).resolve() for value in os.get_exec_path() if value]
        require(prefix / "bin" in directories, "termux_prefix_not_on_path")
        found = shutil.which("angmoo")
        require(found is None or Path(found).resolve() == wrapper.resolve(), "command_path_conflict")
    return wrapper


@contextlib.contextmanager
def installation_lock(tools: Path):
    # Keep the inode: unlinking it would let a competing setup lock another file.
    import fcntl

    fd = os.open(tools / ".setup.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and not info.st_mode & 0o077, "unsafe_setup_lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RegistrationError("setup_busy") from exc
        yield
    finally:
        os.close(fd)


def atomic_file(path: Path, content: bytes, mode: int) -> None:
    if os.path.lexists(path):
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid(), "tools_file_conflict")
    fd, name = tempfile.mkstemp(prefix=".angmoo-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fchmod(output.fileno(), mode)
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def verify(home: Path, prefix: Path | None) -> bool:
    wrapper = preflight(home, prefix)
    tools = home / ".local/share/angmoo-tools"
    require(wrapper_bytes(wrapper) is not None and os.access(wrapper, os.X_OK)
            and os.access(tools / "venv/bin/python", os.X_OK)
            and (tools / "angmoo.py").is_file(), "existing_installation_incomplete")
    if prefix is None:
        return False
    require(same_link(prefix / "bin/angmoo", wrapper), "command_not_registered")
    found = shutil.which("angmoo")
    require(found is not None and Path(found).resolve() == wrapper.resolve(), "command_path_conflict")
    return True


def register(home: Path, prefix: Path | None) -> bool:
    wrapper = preflight(home, prefix)
    if prefix is not None:
        command = prefix / "bin/angmoo"
        try:
            command.symlink_to(wrapper)
        except FileExistsError:
            require(same_link(command, wrapper), "command_name_conflict")
    return verify(home, prefix)


def setup(source: Path, home: Path, prefix: Path | None, *, register_only: bool = False) -> bool:
    preflight(home, prefix)
    tools = private_chain(home, ".local/share/angmoo-tools", create=not register_only)
    require(tools.is_dir(), "existing_installation_incomplete")
    with installation_lock(tools):
        wrapper = preflight(home, prefix)
        if register_only:
            verify(home, None)  # Never create a dangling registration.
        else:
            if shutil.which("proot") is None:
                require(shutil.which("pkg") is not None, "install_python_and_proot_first")
                subprocess.run(["pkg", "install", "proot"], check=True)
            private_chain(home, ".local/bin", create=True)
            python = tools / "venv/bin/python"
            private_chain(home, ".local/share/angmoo-tools/venv/bin")
            if not os.access(python, os.X_OK):
                subprocess.run([sys.executable, "-m", "venv", str(tools / "venv")], check=True)
            subprocess.run([str(python), "-m", "pip", "install", "--require-hashes",
                            "--only-binary=:all:", "--no-deps", "-r", str(source / "requirements.txt")], check=True)
            for name in TOOL_FILES:
                atomic_file(tools / name, (source / name).read_bytes(), 0o644)
            if (source / "LICENSE").is_file():
                atomic_file(tools / "LICENSE", (source / "LICENSE").read_bytes(), 0o644)
            wrapper_bytes(wrapper)  # Recheck after external dependency installation.
            atomic_file(wrapper, WRAPPER, 0o755)
        return register(home, prefix)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in (["setup"], ["register-only"], ["verify"]):
        print("Usage: command_registration.py setup|register-only|verify", file=sys.stderr)
        return 2
    try:
        home = Path.home().resolve(strict=True)
        prefix = native_prefix(home)
        if arguments == ["verify"]:
            print("registered" if verify(home, prefix) else "not-termux")
        else:
            ready = setup(Path(__file__).resolve().parent, home, prefix,
                          register_only=arguments == ["register-only"])
            print("Command ready: angmoo" if ready else
                  "Native Termux prefix not detected; use ~/.local/bin/angmoo.")
            print("Command registration complete." if arguments == ["register-only"] else "Setup complete.")
        return 0
    except RegistrationError as exc:
        print(f"{exc}: Check the command paths. Existing app data was preserved; setup may be incomplete.", file=sys.stderr)
    except subprocess.CalledProcessError as exc:
        print(f"setup_dependency_failed (exit={exc.returncode}): Later setup steps were not run.", file=sys.stderr)
    except OSError as exc:
        print(f"command_setup_failed ({type(exc).__name__}): Check permissions and storage; setup may be incomplete.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
