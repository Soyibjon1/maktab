import os
import requests

REPO    = "Soyibjon1/maktab"
BRANCH  = "main"
FILES   = ["Talaba.py", "client_agent.py", "updater.py", "requirements.txt"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def check_and_update() -> bool:
    try:
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
        print(f"[Updater] Xato: {e}")
        return False

def log(a):
    print(a)