"""Accept the real migration dialog of this hosted qualification's own host.

This is test automation, not a product consent override. Never select windows
by title alone or operate on the developer's installation.
"""
from __future__ import annotations

import os


def accept_owned_migration_dialog(process_id: int) -> bool:
    if (os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise ValueError("windows_pg_consent_hosted_only")
    import ctypes
    from ctypes import wintypes

    user = ctypes.WinDLL("user32", use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user.EnumChildWindows.argtypes = [wintypes.HWND, callback, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetDlgItem.restype = wintypes.HWND
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    def window_text(window):
        value = ctypes.create_unicode_buffer(8192)
        user.GetWindowTextW(window, value, len(value))
        return value.value

    matches = []

    @callback
    def visit(window, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(owner))
        kind = ctypes.create_unicode_buffer(256)
        user.GetClassNameW(window, kind, len(kind))
        if (owner.value != process_id or kind.value != "#32770"
                or window_text(window) != "Angmoo 0.1.4"):
            return True
        text = []

        @callback
        def child_text(child, _):
            text.append(window_text(child))
            return True

        user.EnumChildWindows(window, child_text, 0)
        message = "\n".join(text)
        if "PostgreSQL" in message and (
            "Migrate existing Angmoo 0.1.3 data" in message
            or "기존 Angmoo 0.1.3 데이터를" in message
        ):
            matches.append(window)
        return True

    user.EnumWindows(visit, 0)
    if len(matches) > 1:
        raise ValueError("windows_pg_ambiguous_migration_dialog")
    if not matches:
        return False
    # IDYES belongs to the confirmed dialog owned by the test host process.
    button = user.GetDlgItem(matches[0], 6)
    if not button or not user.PostMessageW(button, 0x00F5, 0, 0):  # BM_CLICK
        raise ValueError("windows_pg_migration_consent_failed")
    return True
