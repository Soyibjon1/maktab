import os
import requests


REPO    = "Soyibjon1/maktab"
BRANCH  = "main"
FILES   = ["Talaba.py", "client_agent.py", "updater.py", "rasm_tahrir.py", "requirements.txt", 'version.txt']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    CURRENT_PATH = os.path.join(BASE_DIR, "version.txt")
    with open(CURRENT_PATH, "r", encoding="utf-8") as f:
        CURRENT = f.read().strip()
except Exception as e:
    print(f"[Updater] Xato-1: {e}")
    CURRENT = "1.0.0"

def check_and_update() -> bool:
    try:
        r = requests.get(
            f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/version.txt",
            timeout=5,
        )
        r.raise_for_status()
        if r.text.strip() == CURRENT:
            return False

        for filename in FILES:
            r = requests.get(
                f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{filename}",
                timeout=10,
            )
            r.raise_for_status()
            path = os.path.join(BASE_DIR, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(r.text)

        return True
    except Exception as e:
        print(f"[Updater] Xato-2: {e}")
        return False

def log(a):
    print(a)