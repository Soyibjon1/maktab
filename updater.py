import os
import requests

CURRENT = "1.0.0"
REPO    = "Soyibjon1/maktab"
BRANCH  = "main"
FILES   = ["Talaba.py", "client_agent.py", "updater.py"]

# Fayllar Talaba.py bilan bir papkada bo'ladi.
# CWD (avtozagruzka) boshqa papkada bo'lishi mumkin,
# shu sababli absolut yo'l ishlatamiz.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
        print(f"[Updater] Xato: {e}")
        return False
