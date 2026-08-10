import os
import requests


REPO    = "Soyibjon1/maktab"
BRANCH  = "main"
FILES   = ["Talaba.py", "client_agent.py", "updater.py", "rasm_tahrir.py", "mouse_lock.py", "requirements.txt", 'version.txt', "voice_radio.py", "fon/light.png", "fon/dark.png"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    CURRENT_PATH = os.path.join(BASE_DIR, "version.txt")
    with open(CURRENT_PATH, "r", encoding="utf-8") as f:
        CURRENT = f.read().strip()
except Exception as e:
    print(f"[Updater] Xato-1: {e}")
    CURRENT = "1.0.0"

def update():
    for filename in FILES:
        r = requests.get(
            f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{filename}",
            timeout=10,
        )
        r.raise_for_status()

        path = os.path.join(BASE_DIR, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)  # fon/ papkasi yo'q bo'lsa yaratadi

        # rasm va binary fayllar uchun wb, qolganlar uchun w
        binary_ext = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".exe"}
        ext = os.path.splitext(filename)[1].lower()

        if ext in binary_ext:
            with open(path, "wb") as f:
                f.write(r.content)   # content — bytes
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(r.text)      # text — str

def check_and_update() -> bool:
    try:
        r = requests.get(
            f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/version.txt",
            timeout=5,
        )
        r.raise_for_status()
        if r.text.strip() == CURRENT:
            print(f"Yagilanihs mavjud emas {r.text.strip()}:{CURRENT}")
            return False

        update()

        return True
    except Exception as e:
        print(f"[Updater] Xato-2: {e}")
        return False

if __name__ == "__main__":
    update()