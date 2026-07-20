import os
def _do_update():
    from updater import check_and_update
    updated = check_and_update()
    if updated:
        print("[Updater] Yangilandi, qayta ishga tushirilmoqda...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        print("[Updater] Yangilanish yo'q yoki xato.")
_do_update()
import sys
import json
import platform
import subprocess
from dataclasses import dataclass
from itertools import cycle
from threading import Thread

import customtkinter as ctk
import keyboard
import pywinstyles
import ctypes

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

ctypes.windll.kernel32.SetThreadExecutionState(
    ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

from client_agent import ClientAgent, SERVER_HOST
from mouse_lock import start_mouse_lock, stop_mouse_lock
from rasm_tahrir import get_program_icon, get_wallpaper
from screen_share import StudentScreenShareViewer
from voice_radio import StudentVoiceRadioClient

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
agent = None
_voice_radio = None

# ---------------------------------------------------------------------------
# KONSOL YASHIRISH
# ---------------------------------------------------------------------------
if platform.system() == "Windows":
    try:
        _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if _hwnd:
            ctypes.windll.user32.ShowWindow(_hwnd, 0)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# MA'LUMOTLAR MODELI
# ---------------------------------------------------------------------------

@dataclass
class ProgramEntry:
    name: str
    path: str
    allowed: bool = False
    icon: str = ""

# ---------------------------------------------------------------------------
# ASOSIY OYNA
# ---------------------------------------------------------------------------

root = ctk.CTk()
root.attributes("-fullscreen", True)
root.attributes("-topmost", True)
root.protocol("WM_DELETE_WINDOW", lambda: None)
ctk.set_appearance_mode("dark")

olcham = root.winfo_screenwidth(), root.winfo_screenheight()

folder = os.path.join(BASE_DIR, "fon")
raslar = [
    os.path.join(folder, f) for f in os.listdir(folder)
    if os.path.splitext(f)[1].lower() in {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
]
_rasm_aylanma = cycle(raslar) if raslar else cycle([os.path.join(folder, "dark.png")])

wp = ctk.CTkLabel(root, text="", image=get_wallpaper(os.path.join(folder, "dark.png"), olcham))
wp.place(x=0, y=0)


def keyingi_rasm():
    return next(_rasm_aylanma)

class NameLabel(ctk.CTkFrame):
    READONLY_COLOR = "#4b3621"   # fon bilan bir xil - "yashirin" ko'rinish uchun
    EDIT_BG_COLOR = "#1e1e2e"    # standart tahrirlash foni
    EDIT_TEXT_COLOR = "#cdd6f4"  # standart tahrirlash yozuv rangi
    LONG_PRESS_MS = 2000         # necha millisekund bosib turish kerak

    def __init__(self, master, initial_name: str, on_rename, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_rename = on_rename
        self._press_after_id = None

        self.entry = ctk.CTkEntry(
            self, width=220, height=34,
            font=ctk.CTkFont("Arial", 22, "bold"),
            justify="right",
            state="readonly",
        )
        self.entry.pack()
        self._set_value(initial_name)
        self._apply_readonly_style()

        # Sichqoncha CHAP tugmasi bosilganda - taymer boshlanadi (2 soniya)
        self.entry.bind("<ButtonPress-1>", self._on_press)
        self.entry.bind("<ButtonRelease-1>", self._on_release)
        self.entry.bind("<Return>", lambda e: self._confirm_edit())
        # Fokusdan chiqib ketsa ham (masalan boshqa joyga bossa) - qabul qilamiz
        self.entry.bind("<FocusOut>", lambda e: self._confirm_edit())
        pywinstyles.set_opacity(self, color="#4b3621")

    # ------------------------------------------------------------------

    def _set_value(self, text: str):
        """Entry qiymatini state'dan qat'iy nazar yozadi (readonly bo'lsa
        ham ichki qiymatni o'zgartirish uchun vaqtincha normal qilinadi)."""
        prev_state = self.entry.cget("state")
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.configure(state=prev_state)

    def _apply_readonly_style(self):
        """Yashirin/label-kabi ko'rinish: barcha ranglar fon bilan bir xil."""
        self.entry.configure(
            state="readonly",
            fg_color=self.READONLY_COLOR,
            border_color=self.READONLY_COLOR,
            bg_color=self.READONLY_COLOR,
            text_color="white",
        )

    def _apply_edit_style(self):
        """Tahrirlash holati: standart, ko'zga tashlanadigan ranglar."""
        self.entry.configure(
            state="normal",
            fg_color=self.EDIT_BG_COLOR,
            border_color="#89b4fa",
            text_color=self.EDIT_TEXT_COLOR,
        )

    # ------------------------------------------------------------------

    def _on_press(self, event=None):
        # Agar allaqachon tahrirlash holatida bo'lsa - qayta taymer
        # boshlash shart emas (foydalanuvchi matn ustida bosib, kursorni
        # joylashtirmoqchi bo'lishi mumkin)
        if str(self.entry.cget("state")) == "normal":
            return
        self._press_after_id = self.after(self.LONG_PRESS_MS, self._enter_edit_mode)

    def _on_release(self, event=None):
        # 2 soniyaga yetmasdan tugma qo'yib yuborilsa - taymerni bekor qilamiz
        if self._press_after_id is not None:
            self.after_cancel(self._press_after_id)
            self._press_after_id = None

    def _enter_edit_mode(self):
        self._press_after_id = None
        self._apply_edit_style()
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def _confirm_edit(self):
        if str(self.entry.cget("state")) != "normal":
            return  # allaqachon readonly - qilinadigan ish yo'q
        new_name = self.entry.get().strip()
        if not new_name:
            new_name = self.entry.get()  # bo'sh bo'lsa eski qiymat qoladi
        self._set_value(new_name)
        self._apply_readonly_style()
        if new_name and self.on_rename:
            self.on_rename(new_name)


class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, on_login):
        super().__init__(master, fg_color="#4b3621", corner_radius=0)
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()
        self.on_login = on_login
        wp = ctk.CTkLabel(self, text="", image=get_wallpaper(os.path.join(folder, "dark.png"), olcham))
        wp.place(x=0, y=0)
        kard = ctk.CTkFrame(self, fg_color="#1e1e2e", corner_radius=20, width=420, bg_color="#4b3621")
        kard.place(relx=0.5, rely=0.5, anchor="center")
        kard.grid_propagate(False)

        ctk.CTkLabel(
            kard, text="👋  Xush kelibsiz!",
            font=ctk.CTkFont("Arial", 24, "bold"), text_color="#cdd6f4",
        ).pack(pady=(32, 8))

        ctk.CTkLabel(
            kard, text="Ismingizni kiriting:",
            font=ctk.CTkFont("Arial", 14), text_color="#a6adc8",
        ).pack()

        self.entry = ctk.CTkEntry(
            kard, width=300, height=44,
            font=ctk.CTkFont("Arial", 16),
            placeholder_text="Ism Familiya",
            justify="center",
        )
        self.entry.pack(pady=(12, 8), padx=40)
        self.entry.bind("<Return>", lambda e: self._submit())
        self.entry.focus()

        ctk.CTkButton(
            kard, text="Kirish", width=300, height=44,
            font=ctk.CTkFont("Arial", 15, "bold"),
            fg_color="#89b4fa", hover_color="#74c7ec",
            text_color="#1e1e2e",
            command=self._submit,
        ).pack(pady=(0, 32), padx=40)
        pywinstyles.set_opacity(self, color="#4b3621")

    def _submit(self):
        name = self.entry.get().strip()
        if not name:
            self.entry.configure(border_color="red")
            return
        self.destroy()
        self.on_login(name)

# ---------------------------------------------------------------------------
# DASTUR ISHGA TUSHIRISH
# ---------------------------------------------------------------------------

def launch_program(program: ProgramEntry):
    if not program.allowed or not os.path.exists(program.path):
        return
    try:
        subprocess.Popen([program.path])
        root.lower()
    except Exception as e:
        print(f"Dasturni ishga tushirishda xatolik: {e}")

# ---------------------------------------------------------------------------
# CHIQISH
# ---------------------------------------------------------------------------

def _do_exit():
    try:
        stop_mouse_lock()
    except Exception:
        pass
    try:
        if agent:
            agent.stop()
    except Exception:
        pass
    try:
        if _voice_radio:
            _voice_radio.stop()
    except Exception:
        pass
    try:
        keyboard.unhook_all()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass
    os._exit(0)

ALWAYS_ON_KEYS = {
    "alt+f5":               lambda: root.after(0, lambda: wp.configure(
                                image=get_wallpaper(keyingi_rasm(), olcham))),
    "ctrl+alt+shift+break": lambda: root.after(0, _do_exit),
    "alt+shift": lambda: keyboard.press_and_release("alt+shift"),
}

def _register_voice_radio_hotkeys():
    """F9 push-to-talk har doim qayta ulanib turishi uchun.

    apply_key_restrictions() ichida keyboard.unhook_all() ishlatilgani sababli
    F9 hooklarini ham shu joydan qayta qo'shamiz.
    """
    if _voice_radio is None:
        return
    try:
        keyboard.on_press_key("f9", lambda e: _voice_radio.start_talk(), suppress=False)
        keyboard.on_release_key("f9", lambda e: _voice_radio.stop_talk(), suppress=False)
    except Exception as e:
        print(f"[Ratsiya] F9 hotkey ulanmadi: {e}")


def apply_key_restrictions(cfg: dict):
    keyboard.unhook_all()

    # 1) Doim ishlaydigan tugmalar — suppress=True YO'Q (boshqa tugmalarga
    #    xalaqit bermasligi uchun)
    for combo, handler in ALWAYS_ON_KEYS.items():
        keyboard.add_hotkey(combo, handler)

    _register_voice_radio_hotkeys()

    if not cfg.get("block", False):
        # Kiosk rejimi o'chirilgan — hech narsa bloklanmaydi
        return

    # 2) Win tugmasi — block_key() eng past darajali, xalaqit bermaydigan usul.
    #    suppress=True ishlatilmaydi, shu sababli kirill/maxsus tugmalarga
    #    ta'sir qilmaydi.
    if not cfg.get("win", False):
        try:
            keyboard.block_key("left windows")
            keyboard.block_key("right windows")
        except Exception:
            keyboard.add_hotkey("windows", lambda: None, suppress=True)

    # 3) Alt+Tab — faqat shu kombinatsiya suppress bilan
    if not cfg.get("alt_tab", False):
        keyboard.add_hotkey("tab", lambda: None, suppress=True)

    # 4) Qolgan bloqlanishi kerak bo'lgan kombinatsiyalar
    for combo in ("ctrl+esc", "ctrl+shift+esc"):
        keyboard.add_hotkey(combo, lambda: None, suppress=True)

# ---------------------------------------------------------------------------
# DASTURLAR PANELI
# ---------------------------------------------------------------------------

_programs_frame = None

def _setup_program_grid():
    global _programs_frame

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if raw.get("block"):
        root.deiconify()
    else:
        root.withdraw()

    apply_key_restrictions(raw)
    if raw.get("input_lock_mouse", False):
        start_mouse_lock()
    else:
        stop_mouse_lock()

    if _programs_frame is not None:
        _programs_frame.destroy()

    _programs_frame = ctk.CTkFrame(root, fg_color="#4b3621", bg_color="#4b3621")
    _programs_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

    dasturlar = [ProgramEntry(**item) for item in raw.get("programs", [])]
    allowed = [p for p in dasturlar if p.allowed]

    if not allowed:
        ctk.CTkLabel(
            _programs_frame,
            text="Ruxsat etilgan dasturlar topilmadi.",
            font=("Arial", 22), text_color="white", bg_color="#4b3621",fg_color="#4b3621",
        ).pack(pady=30)

    else:
        columns = 4
        for idx, program in enumerate(allowed):
            col, row = divmod(idx, columns)
            btn = ctk.CTkButton(
                _programs_frame,
                text=program.name,
                image=get_program_icon(program),
                compound="top",
                width=50, height=50,
                font=("Arial", 14),
                fg_color="#4b3621", bg_color="#4b3621",
                hover_color="#3b3b3b",
                command=lambda p=program: launch_program(p),
            )
            btn.grid(row=row, column=col, padx=10, pady=10, sticky="nw")

    pywinstyles.set_opacity(_programs_frame, color="#4b3621")


def yangilash():
    global _name_label
    _setup_program_grid()
    if _name_label is not None:
        _name_label.lift()

import winsound

_audio_temp = None
_screen_viewer = None


def _handle_screen_share(action: str, host: str, port: int):
    """Ustozdan kelgan screen_share start/stop xabarini bajaradi."""
    global _screen_viewer
    try:
        if _screen_viewer is None:
            _screen_viewer = StudentScreenShareViewer(root)

        if action == "stop":
            _screen_viewer.stop()
        else:
            _screen_viewer.start(host, port)
    except Exception as e:
        print(f"[ScreenShare] Xatolik: {e}")


def _play_audio(audio_bytes: bytes, speed: float, fmt: str, delay_sec: float = 0):
    global _audio_temp
    try:
        import tempfile

        if fmt.lower() == "wav" and speed == 1.0:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(audio_bytes)
            tmp.close()
        else:
            import io
            from pydub import AudioSegment

            sound = AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)

            if speed != 1.0:
                sound = sound._spawn(sound.raw_data, overrides={
                    "frame_rate": int(sound.frame_rate * speed)
                })

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            sound.export(tmp.name, format="wav")
            tmp.close()

        if _audio_temp and os.path.exists(_audio_temp):
            try:
                os.remove(_audio_temp)
            except Exception:
                pass
        _audio_temp = tmp.name

        def _start_playback():
            try:
                winsound.PlaySound(_audio_temp, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:
                print(f"[Audio] Ijroda xatolik: {e}")

        # Fayl allaqachon tayyor (yuqorida konvertatsiya qilindi) -
        # endi faqat delay_sec kutib, ijroni boshlaymiz
        root.after(max(0, int(delay_sec * 1000)), _start_playback)
    except Exception as e:
        print(f"[Audio] Tayyorlashda xatolik: {e}")


def _control_audio(action: str, delay_sec: float = 0):
    """delay_sec - buyruq qabul qilingandan necha soniya keyin bajarilishi
    kerak (sinxron to'xtatish uchun, audio_data bilan bir xil mantiq)."""
    def _do_stop():
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    if action in ("pause", "stop"):
        root.after(max(0, int(delay_sec * 1000)), _do_stop)
    elif action == "play":
        if _audio_temp and os.path.exists(_audio_temp):
            try:
                winsound.PlaySound(_audio_temp, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass

# ---------------------------------------------------------------------------
# RATSİYA
# ---------------------------------------------------------------------------
_voice_radio = StudentVoiceRadioClient(
    root,
    host=SERVER_HOST,
    port=3490,
    name=platform.node() or "Noma'lum",
)
_voice_radio.start()

# ---------------------------------------------------------------------------
# UPDATER
# ---------------------------------------------------------------------------
_setup_program_grid()

agent = ClientAgent(
    reload           = lambda: root.after(0, yangilash),
    name             = platform.node() or "Noma'lum",
    on_lower         = lambda: root.after(0, root.lower),
    on_update        = lambda: Thread(target=_do_update, daemon=True).start(),
    on_audio         = lambda b, s, f, d=0: root.after(0, _play_audio, b, s, f, d),
    on_audio_control = lambda a, d=0: root.after(0, _control_audio, a, d),
    on_screen_share  = lambda a, h, p: root.after(0, _handle_screen_share, a, h, p),
)
Thread(target=agent.run, daemon=True).start()


def on_login(name: str):
    agent.rename(name)
    if _voice_radio:
        _voice_radio.rename(name)
    _show_name_label(name)


def _show_name_label(name: str):

    global _name_label
    if _name_label is not None:
        _name_label.destroy()
    _name_label = NameLabel(
        root, initial_name=name,
        on_rename=lambda new_name: (agent.rename(new_name) if agent else None, _voice_radio.rename(new_name) if _voice_radio else None),
    )
    _name_label.place(relx=1.0, y=10, x=-10, anchor="ne")


_name_label = None

root.after(10, lambda: LoginFrame(root, on_login=on_login))
root.bind("<F11>", lambda e: root.lower())
root.mainloop()
