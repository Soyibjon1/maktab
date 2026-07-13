import ctypes
import threading
from ctypes import wintypes

# ── Windows konstantalari ──────────────────────────────────────────────

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012

VK_END = 0x23  # END tugmasi

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HHOOK = wintypes.HANDLE

HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = HHOOK

user32.UnhookWindowsHookEx.argtypes = [HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.CallNextHookEx.argtypes = [HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


# ── Ichki holat ─────────────────────────────────────────────────────────

_mouse_hook = None
_keyboard_hook = None
_lock_thread_id = None
_lock_thread = None
_is_locked = False


def _block_mouse(n_code, w_param, l_param):
    """Barcha sichqoncha hodisalarini bloklaydi (har doim 1 qaytaradi -
    ya'ni voqea yutib yuboriladi, boshqa hech kimga yetib bormaydi)."""
    if n_code >= 0:
        return 1
    return user32.CallNextHookEx(_mouse_hook, n_code, w_param, l_param)


# Callback obyektlari xotiradan o'chib ketmasligi uchun modul darajasida saqlanadi
_mouse_callback = HOOKPROC(_block_mouse)

def _run_lock_loop():
    global _mouse_hook, _keyboard_hook, _lock_thread_id, _is_locked

    _lock_thread_id = kernel32.GetCurrentThreadId()
    module_handle = kernel32.GetModuleHandleW(None)

    _mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, _mouse_callback, module_handle, 0)
    if not _mouse_hook:
        print(f"[MouseLock] Xatolik: sichqoncha hook o'rnatilmadi ({ctypes.get_last_error()})")
        return

    _is_locked = True
    print("[MouseLock] Sichqoncha butunlay bloklandi.")

    message = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            pass
    finally:
        if _mouse_hook:
            user32.UnhookWindowsHookEx(_mouse_hook)
            _mouse_hook = None
        if _keyboard_hook:
            user32.UnhookWindowsHookEx(_keyboard_hook)
            _keyboard_hook = None
        _is_locked = False
        print("[MouseLock] Sichqoncha blokdan chiqarildi.")

def start_mouse_lock():
    global _lock_thread
    if _is_locked:
        return
    _lock_thread = threading.Thread(target=_run_lock_loop, daemon=True)
    _lock_thread.start()

def stop_mouse_lock():
    if _is_locked and _lock_thread_id is not None:
        user32.PostThreadMessageW(_lock_thread_id, WM_QUIT, 0, 0)


def is_mouse_locked() -> bool:
    return _is_locked

if __name__ == "__main__":
    _run_lock_loop()
