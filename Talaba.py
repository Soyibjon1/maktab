from threading import Thread

import customtkinter as ctk
import keyboard, json, os, subprocess, pywinstyles, sys

from client_agent import ClientAgent
from rasm_tahrir import get_program_icon, get_wallpaper
from dataclasses import dataclass
from itertools import cycle

root = ctk.CTk()
root.attributes("-fullscreen", True)
root.attributes("-topmost", True)
olcham=root.winfo_screenwidth(), root.winfo_screenheight()
folder='fon'
raslar=[os.path.join(folder, f) for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}]
c = cycle(raslar)

wp=ctk.CTkLabel(root, text='', image=get_wallpaper('fon/dark.png', olcham))
wp.place(x=0, y=0)

def launch_program(program: ProgramEntry):
    if not program.allowed:
        return
    if not os.path.exists(program.path):
        print(f"Dastur topilmadi: {program.path}")
        return

    try:
        subprocess.Popen([program.path])
        root.lower()
    except Exception as e:
        print(f"Dasturni ishga tushirishda xatolik: {e}")
        return

def keyingi(rasm_manzil=None):
    if rasm_manzil:
        return next(c)
    else:
        return rasm_manzil
def block_and_warn(combo):
    if combo == "alt+f5":
        wp.configure(image=get_wallpaper(keyingi(), olcham))
    elif combo == "chiqish" or combo == "ctrl+alt+shift+break":
        agent.stop()
        sys.exit(0)
    print(f"'{combo}' bloklangan - bu amal taqiqlangan!")

root.protocol("WM_DELETE_WINDOW", lambda: block_and_warn("chiqish"))
taqiq = ("windows", "alt+f4", "alt+f5", "alt+tab", "ctrl+esc", "ctrl+alt+delete", "ctrl+shift+esc", "ctrl+c+h", "ctrl+alt+shift+break")

for combo in taqiq:
    keyboard.add_hotkey(combo, lambda c=combo: block_and_warn(c), suppress=True)


# ctk.CTkLabel(root, text="Kiosk rejimi ishlamoqda", font=("Arial", 30)).pack(expand=True)

@dataclass
class ProgramEntry:
    name: str
    path: str
    allowed: bool = False
    icon: str = ""
tugmalar = {}
def _setup_program_grid():
    # place o'rniga pack/grid ishlatamiz, chap-yuqoridan boshlansin
    # grid_frame = ctk.CTkScrollableFrame(root, fg_color="transparent")
    # grid_frame.pack(fill="both", expand=True, padx=20, pady=20)

    with open("config.json", "r", encoding="utf-8") as f:
        raw = json.load(f)
    if raw.get('block'):
        root.deiconify()
    else:
        root.withdraw()

    if raw.get('win'):
        keyboard.remove_hotkey("windows")

    dasturlar = [ProgramEntry(**item) for item in raw.get("programs", [])]
    allowed_programs = [i for i in dasturlar if i.allowed]

    if not allowed_programs:
        t=ctk.CTkLabel(
            root,
            text="Ruxsat etilgan dasturlar topilmadi.",
            font=("Arial", 22), text_color="white",
            bg_color="#4b3621"
        )
        t.pack(pady=30)
        tugmalar["0:0"] = t
        pywinstyles.set_opacity(t, color="#4b3621")
        return

    columns = 4
    for idx, program in enumerate(allowed_programs):
        col, row = divmod(idx, columns)  # chap→o'ng, keyin pastga
        icon = get_program_icon(program)

        btn = ctk.CTkButton(
            root,
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
        btn.grid(row=row, column=col, padx=10, pady=10, sticky="nw")  # nw = chap-yuqori
        tugmalar[f"{col}:{row}"] = btn

        pywinstyles.set_opacity(btn, color="#4b3621")

_setup_program_grid()

def yangilash():
    for i in tugmalar.keys():
        tugmalar[i].destroy()
    _setup_program_grid()

agent = ClientAgent(reload=yangilash)
Thread(target=agent.run).start()


root.bind("<F11>", lambda e: root.lower())

root.mainloop()