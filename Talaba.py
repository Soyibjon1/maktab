import os
import sys
import json
import ctypes
import platform
import subprocess
from dataclasses import dataclass
from itertools import cycle
from threading import Thread

import customtkinter as ctk
import keyboard
import pywinstyles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

from client_agent import ClientAgent
from rasm_tahrir import get_program_icon, get_wallpaper

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
agent = None

# ---------------------------------------------------------------------------
# KONSOL YASHIRISH
# ---------------------------------------------------------------------------
# if platform.system() == "Windows":
#     try:
#         _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
#         if _hwnd:
#             ctypes.windll.user32.ShowWindow(_hwnd, 0)
#     except Exception:
#         pass

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

class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, on_login):
        super().__init__(master, fg_color="#000000", corner_radius=0)
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()
        self.on_login = on_login

        kard = ctk.CTkFrame(self, fg_color="#1e1e2e", corner_radius=20, width=420)
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
        if agent:
            agent.stop()
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
}

def apply_key_restrictions(cfg: dict):
    keyboard.unhook_all()

    # 1) Doim ishlaydigan tugmalar — suppress=True YO'Q (boshqa tugmalarga
    #    xalaqit bermasligi uchun)
    for combo, handler in ALWAYS_ON_KEYS.items():
        keyboard.add_hotkey(combo, handler)

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
        keyboard.add_hotkey("alt+tab", lambda: None, suppress=True)

    # 4) Qolgan bloqlanishi kerak bo'lgan kombinatsiyalar
    for combo in ("alt+f4", "ctrl+esc", "ctrl+shift+esc"):
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
    _setup_program_grid()

import winsound

_audio_temp = None


def _play_audio(audio_bytes: bytes, speed: float, fmt: str, delay_sec: float = 0):
    """
    delay_sec - xabar qabul qilingandan necha soniya keyin ijro
    boshlanishi kerak. Audio fayl OLDINDAN (kechikish paytida) tayyor
    holga keltiriladi, shunda ijroning o'zi aniq delay_sec vaqtida
    boshlanadi - fayl konvertatsiya vaqti sinxronlikni buzmaydi.
    """
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
# UPDATER
# ---------------------------------------------------------------------------

def _do_update():
    from updater import check_and_update
    updated = check_and_update()
    if updated:
        print("[Updater] Yangilandi, qayta ishga tushirilmoqda...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        print("[Updater] Yangilanish yo'q yoki xato.")

# ---------------------------------------------------------------------------
# ISHGA TUSHIRISH
# ---------------------------------------------------------------------------
# TARTIB (muhim!):
#   1) BIRINCHI NAVBATDA serverga ulanamiz (fon threadida). Bu config.json
#      dagi "block" qiymatidan QAT'IY NAZAR bajariladi - aks holda
#      block=false bo'lganda LoginFrame umuman chiqmay, ustozga ulanish
#      ham amalga oshmay qolardi.
#   2) Server bilan aloqa fon threadida boshlangandan keyin, LoginFrame
#      har doim ko'rsatiladi (talaba ismini kiritishi shart).
#   3) Ism kiritilgach, agentga (allaqachon ishga tushgan) nomni beramiz
#      va dasturlar panelini config.json ga mos holda quramiz (shu yerda
#      "block" qiymatiga qarab oyna ko'rsatiladi yoki yashiriladi).

_setup_program_grid()

# Talaba kiritgan ism kelguncha vaqtinchalik nom bilan ulanamiz -
# LoginFrame orqali ism kiritilgach, agent.name yangilanadi va
# serverga xabar beriladi (rename orqali).
agent = ClientAgent(
    reload           = lambda: root.after(0, yangilash),
    name             = platform.node() or "Noma'lum",
    on_lower         = lambda: root.after(0, root.lower),
    on_update        = lambda: Thread(target=_do_update, daemon=True).start(),
    on_audio         = lambda b, s, f, d=0: root.after(0, _play_audio, b, s, f, d),
    on_audio_control = lambda a, d=0: root.after(0, _control_audio, a, d),
)
Thread(target=agent.run, daemon=True).start()


def on_login(name: str):
    agent.rename(name)


root.after(10, lambda: LoginFrame(root, on_login=on_login))
root.bind("<F11>", lambda e: root.lower())
root.mainloop()
