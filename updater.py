import os
import shutil
import tempfile
import requests


REPO    = "Soyibjon1/maktab"
BRANCH  = "main"
FILES   = [
    "Talaba.py", "client_agent.py", "updater.py", "rasm_tahrir.py",
    "mouse_lock.py", "screen_share.py", "audio_isolate.py",
    "process_guardian.py", "requirements.txt", "version.txt",
    "voice_radio.py", "fon/light.png", "fon/dark.png"
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_current_version() -> str:
    try:
        current_path = os.path.join(BASE_DIR, "version.txt")
        if os.path.exists(current_path):
            with open(current_path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception as e:
        print(f"[Updater] Versiyani o'qishda xato: {e}")
    return "1.0.0"


def update() -> bool:
    """Fayllarni avval vaqtinchalik papkaga xavfsiz yuklab oladi.
    Barcha fayllar to'liq yuklangandagina asosiy papkaga ko'chiradi (atomik yangilanish).
    """
    temp_dir = tempfile.mkdtemp(prefix="talaba_upd_")
    try:
        binary_ext = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".exe"}
        for filename in FILES:
            url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{filename}"
            r = requests.get(url, timeout=12)
            r.raise_for_status()

            temp_path = os.path.join(temp_dir, filename)
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)

            ext = os.path.splitext(filename)[1].lower()
            if ext in binary_ext:
                with open(temp_path, "wb") as f:
                    f.write(r.content)
            else:
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(r.text)

        # Barcha fayllar muvaffaqiyatli yuklandi — asosiy papkaga xavfsiz ko'chiramiz
        for filename in FILES:
            src = os.path.join(temp_dir, filename)
            dst = os.path.join(BASE_DIR, filename)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                try:
                    os.remove(dst)
                except Exception:
                    pass
            shutil.copy2(src, dst)

        return True
    except Exception as e:
        print(f"[Updater] Yuklab olishda xato (bekor qilindi): {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def check_and_update() -> bool:
    try:
        current_ver = get_current_version()
        r = requests.get(
            f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/version.txt",
            timeout=5,
        )
        r.raise_for_status()
        remote_ver = r.text.strip()
        if remote_ver == current_ver:
            print(f"[Updater] Yangilanish mavjud emas ({remote_ver} == {current_ver})")
            return False

        print(f"[Updater] Yangi versiya topildi: {remote_ver} (joriy: {current_ver}). Yuklanmoqda...")
        return update()
    except Exception as e:
        print(f"[Updater] Versiyani tekshirishda xato: {e}")
        return False


if __name__ == "__main__":
    if check_and_update():
        print("[Updater] Yangilanish muvaffaqiyatli yakunlandi.")
    else:
        print("[Updater] Yangilanish bajarilmadi.")
