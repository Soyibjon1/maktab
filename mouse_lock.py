import ctypes
import threading
from ctypes import wintypes

# ── Windows konstantalari ──────────────────────────────────────────────

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

# Virtual key kodlari
VK_TAB = 0x09
VK_PAUSE = 0x13       # Pause / Break tugmasi (emergency exit)
VK_ESCAPE = 0x1B
VK_F4 = 0x73
VK_F9 = 0x78          # Ratsiya push-to-talk
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12        # Alt

LLKHF_ALTDOWN = 0x20

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

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT

kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


try:
    import keyboard as py_keyboard
except Exception:
    py_keyboard = None

# ── Ichki holat ─────────────────────────────────────────────────────────

_mouse_hook = None
_mouse_thread_id = None
_mouse_thread = None
_is_mouse_locked = False
_mouse_lock = threading.Lock()

_keyboard_hook = None
_keyboard_thread_id = None
_keyboard_thread = None
_is_keyboard_locked = False
_block_win = False
_block_alt_tab = False
_allow_f9 = True
_emergency_exit_callback = None
_keyboard_lock = threading.Lock()
_py_keyboard_hook = None


def _is_vkey_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


# ── SICHQONCHA HOOKI ──────────────────────────────────────────────────

def _block_mouse(n_code, w_param, l_param):
    """Barcha sichqoncha hodisalarini bloklaydi."""
    if n_code >= 0:
        return 1
    return user32.CallNextHookEx(_mouse_hook, n_code, w_param, l_param)


_mouse_callback = HOOKPROC(_block_mouse)


def _run_mouse_loop():
    global _mouse_hook, _mouse_thread_id, _is_mouse_locked

    _mouse_thread_id = kernel32.GetCurrentThreadId()
    module_handle = kernel32.GetModuleHandleW(None)

    _mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, _mouse_callback, module_handle, 0)
    if not _mouse_hook:
        print(f"[MouseLock] Xatolik: sichqoncha hook o'rnatilmadi ({ctypes.get_last_error()})")
        _is_mouse_locked = False
        return

    print("[MouseLock] Sichqoncha butunlay bloklandi.")
    message = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            pass
    finally:
        if _mouse_hook:
            user32.UnhookWindowsHookEx(_mouse_hook)
            _mouse_hook = None
        _is_mouse_locked = False
        _mouse_thread_id = None
        print("[MouseLock] Sichqoncha blokdan chiqarildi.")


def start_mouse_lock():
    global _mouse_thread, _is_mouse_locked
    with _mouse_lock:
        if _is_mouse_locked:
            return
        _is_mouse_locked = True
        _mouse_thread = threading.Thread(target=_run_mouse_loop, daemon=True)
        _mouse_thread.start()


def stop_mouse_lock():
    global _is_mouse_locked
    with _mouse_lock:
        if not _is_mouse_locked:
            return
        _is_mouse_locked = False
        if _mouse_thread_id:
            user32.PostThreadMessageW(_mouse_thread_id, WM_QUIT, 0, 0)


def is_mouse_locked() -> bool:
    return _is_mouse_locked


# ── KLAVIATURA HOOKI ──────────────────────────────────────────────────

def _block_keyboard(n_code, w_param, l_param):
    """
    Klaviaturani to'liq yoki qisman (kiosk) bloklash hooki.
    - Favqulodda chiqish (Ctrl+Alt+Shift+Break) doim ishlaydi.
    - Ratsiya (F9) o'quvchi ustoz bilan gaplashishi uchun o'tkaziladi.
    - To'liq bloklash yoqilgan bo'lsa, qolgan hamma tugmalar yutiladi (return 1).
    - Kiosk rejimida Win, Alt+Tab, Alt+Esc, Ctrl+Esc, Alt+F4 bloklanadi.
    """
    if n_code >= 0:
        try:
            struct = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = struct.vkCode
            flags = struct.flags
            alt_down = bool(flags & LLKHF_ALTDOWN)

            # 1. Favqulodda chiqish kombinatsiyasi: Ctrl + Alt + Shift + Pause/Break
            if vk == VK_PAUSE:
                ctrl_down = _is_vkey_down(VK_CONTROL)
                shift_down = _is_vkey_down(VK_SHIFT)
                alt_active = alt_down or _is_vkey_down(VK_MENU)
                if ctrl_down and shift_down and alt_active:
                    if _emergency_exit_callback:
                        try:
                            threading.Thread(target=_emergency_exit_callback, daemon=True).start()
                        except Exception as e:
                            print(f"[KeyLock] Favqulodda chiqishda xato: {e}")
                    return 0

            # 2. Ratsiya (F9) — push-to-talk uchun ruxsat berish
            if _allow_f9 and vk == VK_F9:
                return user32.CallNextHookEx(_keyboard_hook, n_code, w_param, l_param)

            # 3. Agar to'liq klaviatura bloklangan bo'lsa — hech qanday tugma o'tmasin
            if _is_keyboard_locked:
                return 1

            # 4. Kiosk qisman cheklovlari
            if _block_win and vk in (VK_LWIN, VK_RWIN):
                return 1

            if _block_alt_tab and vk == VK_TAB and alt_down:
                return 1

            if _block_alt_tab and vk == VK_ESCAPE and alt_down:
                return 1

            if _block_win and vk == VK_ESCAPE and _is_vkey_down(VK_CONTROL):
                return 1

            if vk == VK_F4 and alt_down:
                return 1

        except Exception as e:
            if _is_keyboard_locked:
                return 1

    return user32.CallNextHookEx(_keyboard_hook, n_code, w_param, l_param)


_keyboard_callback = HOOKPROC(_block_keyboard)


def _run_keyboard_loop():
    global _keyboard_hook, _keyboard_thread_id

    _keyboard_thread_id = kernel32.GetCurrentThreadId()
    module_handle = kernel32.GetModuleHandleW(None)

    _keyboard_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _keyboard_callback, module_handle, 0)
    if not _keyboard_hook:
        print(f"[KeyLock] Xatolik: klaviatura hook o'rnatilmadi ({ctypes.get_last_error()})")
        return

    print("[KeyLock] Klaviatura hooki faollashdi.")
    message = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            pass
    finally:
        if _keyboard_hook:
            user32.UnhookWindowsHookEx(_keyboard_hook)
            _keyboard_hook = None
        _keyboard_thread_id = None
        print("[KeyLock] Klaviatura hooki to'xtatildi.")


def _ensure_keyboard_thread():
    global _keyboard_thread
    with _keyboard_lock:
        needs_hook = _is_keyboard_locked or _block_win or _block_alt_tab
        is_running = _keyboard_thread is not None and _keyboard_thread.is_alive()

        if needs_hook and not is_running:
            _keyboard_thread = threading.Thread(target=_run_keyboard_loop, daemon=True)
            _keyboard_thread.start()
        elif not needs_hook and is_running:
            if _keyboard_thread_id:
                user32.PostThreadMessageW(_keyboard_thread_id, WM_QUIT, 0, 0)


def start_keyboard_lock():
    global _is_keyboard_locked, _py_keyboard_hook
    _is_keyboard_locked = True
    print("[KeyLock] Klaviaturani to'liq bloklash yoqildi.")

    # 1-darajali himoya: Low-Level Hook
    _ensure_keyboard_thread()

    # 2-darajali himoya: keyboard kutubxonasi orqali suppress
    if py_keyboard and _py_keyboard_hook is None:
        try:
            def _suppress_handler(e):
                if not _is_keyboard_locked:
                    return True
                # F9 (ratsiya) ga ruxsat berish
                name = getattr(e, "name", "") or ""
                if _allow_f9 and name.lower() == "f9":
                    return True
                return False

            _py_keyboard_hook = py_keyboard.hook(_suppress_handler, suppress=True)
        except Exception as ex:
            print(f"[KeyLock] py_keyboard suppress ulanmadi: {ex}")


def stop_keyboard_lock():
    global _is_keyboard_locked, _py_keyboard_hook
    _is_keyboard_locked = False
    print("[KeyLock] Klaviaturani to'liq bloklash o'chirildi.")

    if py_keyboard and _py_keyboard_hook is not None:
        try:
            py_keyboard.unhook(_py_keyboard_hook)
        except Exception:
            pass
        _py_keyboard_hook = None

    _ensure_keyboard_thread()


def is_keyboard_locked() -> bool:
    return _is_keyboard_locked


def set_kiosk_key_restrictions(block_win: bool = False, block_alt_tab: bool = False):
    global _block_win, _block_alt_tab
    _block_win = bool(block_win)
    _block_alt_tab = bool(block_alt_tab)
    _ensure_keyboard_thread()


def clear_kiosk_key_restrictions():
    set_kiosk_key_restrictions(False, False)


def set_emergency_exit_callback(callback):
    global _emergency_exit_callback
    _emergency_exit_callback = callback


# Eski kod bilan moslik uchun
def is_locked() -> bool:
    return _is_mouse_locked or _is_keyboard_locked


if __name__ == "__main__":
    import time
    start_keyboard_lock()
    time.sleep(5)
    stop_keyboard_lock()
