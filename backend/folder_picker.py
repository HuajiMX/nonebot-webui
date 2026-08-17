"""Windows 系统文件夹选择对话框（供 WebUI 本地使用）。"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


def pick_folder() -> str:
    """打开系统文件夹选择对话框，返回所选绝对路径；取消或非 Windows 返回空字符串。"""
    if os.name != "nt":
        return ""

    BIF_RETURNONLYFSDIRS = 0x00000001
    BIF_NEWDIALOGSTYLE = 0x00000040

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", wintypes.LPWSTR),
            ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", wintypes.UINT),
            ("lpfn", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("iImage", ctypes.c_int),
        ]

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFO)]
    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]

    title = "选择机器人目录"
    display = ctypes.create_unicode_buffer(260)
    bi = BROWSEINFO(
        hwndOwner=None,
        pidlRoot=None,
        pszDisplayName=ctypes.cast(display, wintypes.LPWSTR),
        lpszTitle=title,
        ulFlags=BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE,
        lpfn=None,
        lParam=None,
        iImage=0,
    )
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
    if not pidl:
        return ""
    try:
        path_buf = ctypes.create_unicode_buffer(260)
        if shell32.SHGetPathFromIDListW(pidl, path_buf):
            return path_buf.value
        return ""
    finally:
        ole32.CoTaskMemFree(pidl)
