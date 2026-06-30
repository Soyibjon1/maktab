import os
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

from client_agent import ClientAgent
from rasm_tahrir import get_program_icon, get_wallpaper

CONFIG_PATH = "config.json"


# ---------------------------------------------------------------------------
# KONSOL OYNASINI YASHIRISH
# ---------------------------------------------------------------------------
# Talaba kompyuterida qora konsol oynasi ko'rinib turmasligi uchun.
# DIQQAT: bu faqat OYNANI yashiradi, print() funksiyasi baribir
# ishlayveradi (faqat ko'rinmas konsolga yoziladi) - shu sababli
# log faylga alohida yo'naltirish shart emas, debugging uchun kerak
# bo'lsa, konsolni vaqtincha qaytadan ko'rsatish (ShowWindow(hwnd, 1))
# orqali tekshirish mumkin.
if platform.system() == "Windows":
    try:
        _console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if _console_hwnd:
            ctypes.windll.user32.ShowWindow(_console_hwnd, 0)  # SW_HIDE
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
# ASOSIY OYNA VA TALABA ISMINI SO'RASH
# ---------------------------------------------------------------------------

root = ctk.CTk()

_ism_oynasi = ctk.CTkInputDialog(text="Ismingizni kiriting:", title="Talaba")
TALABA_ISMI = (_ism_oynasi.get_input() or "").strip() or platform.node() or "Noma'lum"

root.deiconify()
root.attributes("-fullscreen", True)
root.attributes("-topmost", True)

olcham = root.winfo_screenwidth(), root.winfo_screenheight()

folder = "fon"
raslar = [
    os.path.join(folder, f) for f in os.listdir(folder)
    if os.path.splitext(f)[1].lower() in {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
]
_rasm_aylanma = cycle(raslar) if raslar else cycle(["fon/dark.png"])

wp = ctk.CTkLabel(root, text="", image=get_wallpaper("fon/dark.png", olcham))
wp.place(x=0, y=0)


def keyingi_rasm():
    return next(_rasm_aylanma)


# ---------------------------------------------------------------------------
# DASTUR ISHGA TUSHIRISH
# ---------------------------------------------------------------------------

def launch_program(program: ProgramEntry):
    if not program.allowed:
        return
    if not os.path.exists(program.path):
        print(f"Dastur topilmadi: {program.path}")
        return
    try:
        subprocess.Popen([program.path])
        root.lower()  # dastur ochilganda launcher doim orqaga o'tadi (ruxsat shart emas)
    except Exception as e:
        print(f"Dasturni ishga tushirishda xatolik: {e}")


# ---------------------------------------------------------------------------
# TUGMALARNI BLOKLASH / OGOHLANTIRISH
# ---------------------------------------------------------------------------

def _do_exit():
    try:
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


def block_and_warn(combo):
    if combo == "alt+f5":
        wp.configure(image=get_wallpaper(keyingi_rasm(), olcham))
        return
    if combo in ("chiqish", "ctrl+alt+shift+break"):
        root.after(0, _do_exit)
        return
    print(f"'{combo}' bloklangan - bu amal taqiqlangan!")


root.protocol("WM_DELETE_WINDOW", lambda: block_and_warn("chiqish"))

# Doim ishlaydigan, hech qachon bloklanmaydigan tugmalar:
#   alt+f5               - fon rasmini almashtirish
#   ctrl+alt+shift+break - admin uchun chiqish (kiosk rejimidan qat'iy nazar)
ALWAYS_ON_KEYS = ("alt+f5", "ctrl+alt+shift+break")

# SECURITY_KEYS - Win, Alt+Tab kabi xavfsizlik tugmalari (o'zgarishsiz qoladi)
SECURITY_KEYS = ("windows", "alt+f4", "alt+tab", "ctrl+esc",
                  "ctrl+alt+delete", "ctrl+shift+esc")


def apply_key_restrictions(cfg: dict):
    keyboard.unhook_all()

    # 1) Doim ishlaydigan tugmalar - kiosk holatidan qat'iy nazar
    for combo in ALWAYS_ON_KEYS:
        keyboard.add_hotkey(combo, lambda c=combo: block_and_warn(c), suppress=True)

    block_mode = cfg.get("block", False)

    if not block_mode:
        # Kiosk rejimi O'CHIRILGAN - xavfsizlik tugmalarining HECH BIRI
        # bloklanmaydi, alohida sozlamalardan (win, alt_tab) qat'iy nazar
        return

    allow_win = cfg.get("win", False)
    allow_alt_tab = cfg.get("alt_tab", False)

    for combo in SECURITY_KEYS:
        if combo == "windows" and allow_win:
            continue  # ruxsat berilgan - bloklamaymiz
        if combo == "alt+tab" and allow_alt_tab:
            continue  # ruxsat berilgan - bloklamaymiz
        keyboard.add_hotkey(combo, lambda c=combo: block_and_warn(c), suppress=True)

_programs_frame = None


def _setup_program_grid():
    global _programs_frame

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Oyna ko'rinishini boshqarish (kiosk rejimi yoqilgan/o'chirilganiga qarab)
    if raw.get("block"):
        root.deiconify()
    else:
        root.withdraw()

    # Klaviatura cheklovlarini joriy konfiguratsiyaga mos ravishda
    # to'liq qaytadan quramiz (bug-fix - yuqoridagi izohga qarang)
    apply_key_restrictions(raw)

    # Eski panelni BUTUNLAY, BIR YO'LA o'chiramiz (agar mavjud bo'lsa)
    if _programs_frame is not None:
        _programs_frame.destroy()

    _programs_frame = ctk.CTkFrame(root, fg_color="#4b3621", bg_color="#4b3621")
    _programs_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

    dasturlar = [ProgramEntry(**item) for item in raw.get("programs", [])]
    allowed_programs = [i for i in dasturlar if i.allowed]

    if not allowed_programs:
        t = ctk.CTkLabel(
            _programs_frame,
            text="Ruxsat etilgan dasturlar topilmadi.",
            font=("Arial", 22), text_color="white",
            bg_color="#4b3621",
        )
        t.pack(pady=30)
        return

    columns = 4
    for idx, program in enumerate(allowed_programs):
        col, row = divmod(idx, columns)  # chap→o'ng, keyin pastga
        icon = get_program_icon(program)

        btn = ctk.CTkButton(
            _programs_frame,
            text=program.name,
            image=icon,
            compound="top",
            width=50, height=50,
            font=("Arial", 14),
            fg_color="#4b3621",
            bg_color="#4b3621",
            hover_color="#3b3b3b",
            command=lambda p=program: launch_program(p),
        )
        btn.grid(row=row, column=col, padx=10, pady=10, sticky="nw")
    pywinstyles.set_opacity(_programs_frame, color="#4b3621")


def yangilash():
    """Serverdan yangi konfiguratsiya kelganda chaqiriladi."""
    _setup_program_grid()


_setup_program_grid()


# ---------------------------------------------------------------------------
# SERVERGA ULANISH (talaba kiritgan ism bilan)
# ---------------------------------------------------------------------------

agent = ClientAgent(
    reload=lambda: root.after(0, yangilash),  # tarmoq threadidan emas, asosiy threadda bajariladi
    name=TALABA_ISMI,
    on_lower=lambda: root.after(0, root.lower),
)
Thread(target=agent.run, daemon=True).start()


# ---------------------------------------------------------------------------
# F11 - DASTURNI ORQAGA TUSHIRISH (cheklovsiz, doim ishlaydi)
# ---------------------------------------------------------------------------

root.bind("<F11>", lambda e: root.lower())

root.mainloop()
