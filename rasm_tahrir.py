"""
rasm_tahrir.py — Ikonka va fon rasmlarini yuklash.

IKONKA MUAMMOSI (bazi kompyuterlarda ko'rinmaydi):
  win32gui.ExtractIconEx() ba'zi sistemalarda (yoki ba'zi exe turlari uchun)
  bo'sh ro'yxat qaytaradi — masalan, UWP/Store ilovalar, Python skriptlar,
  yoki ma'lum manifest formatidagi exe lar uchun. Shu sababli uchta
  usul ketma-ket sinab ko'riladi:
    1) win32gui.ExtractIconEx()        — standart pywin32 usuli
    2) ctypes + SHGetFileInfo()        — Windows Shell API (pywin32 shart emas)
    3) make_placeholder_icon()         — hech narsa ishlamasa, kulrang kvadrat
"""

import os
import ctypes
import ctypes.wintypes
from typing import Optional

from PIL import Image, ImageTk
import customtkinter as ctk

try:
    import win32gui
    import win32ui
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

DEFAULT_ICON_SIZE = (35, 35)


# ---------------------------------------------------------------------------
# 1-USUL: pywin32 (ExtractIconEx)
# ---------------------------------------------------------------------------

def _extract_via_pywin32(exe_path: str, size=DEFAULT_ICON_SIZE) -> Optional[Image.Image]:
    if not PYWIN32_AVAILABLE or not os.path.exists(exe_path):
        return None
    try:
        large, small = win32gui.ExtractIconEx(exe_path, 0)
        if not large and not small:
            return None
        hicon = large[0] if large else small[0]

        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, size[0], size[1])
        hdc_mem = hdc.CreateCompatibleDC()
        hdc_mem.SelectObject(hbmp)
        hdc_mem.DrawIcon((0, 0), hicon)

        bmpinfo = hbmp.GetInfo()
        bmpstr = hbmp.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGBA",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr, "raw", "BGRA", 0, 1,
        )
        for h in (large or []) + (small or []):
            try:
                win32gui.DestroyIcon(h)
            except Exception:
                pass
        return img.resize(size)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 2-USUL: ctypes + SHGetFileInfo (pywin32 shart emas)
# ---------------------------------------------------------------------------
# Bu usul pywin32 o'rnatilmagan yoki ExtractIconEx ishlamagan holatlarda
# fallback sifatida ishlatiladi. Windows Shell API barcha exe lar uchun
# ikonka qaytaradi (jumladan UWP ilovalar uchun ham).

def _extract_via_ctypes(exe_path: str, size=DEFAULT_ICON_SIZE) -> Optional[Image.Image]:
    if not os.path.exists(exe_path):
        return None
    try:
        import struct

        SHGFI_ICON       = 0x000000100
        SHGFI_LARGEICON  = 0x000000000
        SHGFI_SMALLICON  = 0x000000001
        SHGFI_USEFILEATTRIBUTES = 0x000000010

        class SHFILEINFO(ctypes.Structure):
            _fields_ = [
                ("hIcon",         ctypes.wintypes.HICON),
                ("iIcon",         ctypes.c_int),
                ("dwAttributes",  ctypes.wintypes.DWORD),
                ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName",    ctypes.c_wchar * 80),
            ]

        shell32 = ctypes.windll.shell32
        shfi = SHFILEINFO()
        ret = shell32.SHGetFileInfoW(
            exe_path, 0, ctypes.byref(shfi), ctypes.sizeof(shfi),
            SHGFI_ICON | SHGFI_LARGEICON,
        )
        if not ret or not shfi.hIcon:
            return None

        # HICON → PIL Image (CreateIconIndirect yo'li bilan)
        user32  = ctypes.windll.user32
        gdi32   = ctypes.windll.gdi32

        # Ikon o'lchamini olish
        icon_info = ctypes.create_string_buffer(40)  # ICONINFO
        user32.GetIconInfo(shfi.hIcon, icon_info)

        # DIB sifatida o'qish
        ico_x = user32.GetSystemMetrics(11)  # SM_CXICON
        ico_y = user32.GetSystemMetrics(12)  # SM_CYICON

        hdc_screen = user32.GetDC(None)
        hdc_mem    = gdi32.CreateCompatibleDC(hdc_screen)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize",          ctypes.c_uint32),
                ("biWidth",         ctypes.c_int32),
                ("biHeight",        ctypes.c_int32),
                ("biPlanes",        ctypes.c_uint16),
                ("biBitCount",      ctypes.c_uint16),
                ("biCompression",   ctypes.c_uint32),
                ("biSizeImage",     ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed",       ctypes.c_uint32),
                ("biClrImportant",  ctypes.c_uint32),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize      = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth     = ico_x
        bmi.biHeight    = -ico_y   # negatif = top-down
        bmi.biPlanes    = 1
        bmi.biBitCount  = 32
        bmi.biCompression = 0      # BI_RGB

        buf = (ctypes.c_byte * (ico_x * ico_y * 4))()
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, ico_x, ico_y)
        gdi32.SelectObject(hdc_mem, hbmp)
        user32.DrawIconEx(hdc_mem, 0, 0, shfi.hIcon, ico_x, ico_y, 0, None, 3)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, ico_y, buf, ctypes.byref(bmi), 0)

        img = Image.frombytes("RGBA", (ico_x, ico_y), bytes(buf), "raw", "BGRA")

        # Tozalash
        user32.DestroyIcon(shfi.hIcon)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)

        return img.resize(size)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PLACEHOLDER
# ---------------------------------------------------------------------------

def make_placeholder_icon(size=DEFAULT_ICON_SIZE) -> Image.Image:
    return Image.new("RGBA", size, (90, 90, 90, 255))


# ---------------------------------------------------------------------------
# ASOSIY FUNKSIYA
# ---------------------------------------------------------------------------

def extract_icon_from_exe(exe_path: str, size=DEFAULT_ICON_SIZE) -> Optional[Image.Image]:
    img = _extract_via_pywin32(exe_path, size)
    if img is None:
        img = _extract_via_ctypes(exe_path, size)
    return img


def get_program_icon(program) -> "ctk.CTkImage":
    img = None
    if program.icon and os.path.exists(program.icon):
        try:
            img = Image.open(program.icon).convert("RGBA").resize(DEFAULT_ICON_SIZE)
        except Exception:
            img = None
    if img is None:
        img = extract_icon_from_exe(program.path)
    if img is None:
        img = make_placeholder_icon()
    return ctk.CTkImage(light_image=img, dark_image=img, size=DEFAULT_ICON_SIZE)


def get_wallpaper(path: str, size: tuple) -> ImageTk.PhotoImage:
    img = Image.open(path).resize(size)
    return ImageTk.PhotoImage(img)
