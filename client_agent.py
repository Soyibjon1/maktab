import socket
import subprocess
import json
import threading
import time
import os
import sys
import platform

# Fayl joylashgan papka — config.json shu yerda bo'ladi.
# Avtozagruzka ishga tushirganda CWD boshqa joy bo'lishi mumkin,
# shu sababli absolut yo'l ishlatamiz.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# ── Sozlamalar ──────────────────────────────────────────────

SERVER_HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.100.250"
SERVER_PORT  = int(sys.argv[2]) if len(sys.argv) > 2 else 3475

# Client nomi: muhit o'zgaruvchisi > kompyuter nomi
CLIENT_NAME = os.environ.get("CLIENT_NAME") or platform.node() or "Unknown-PC"

RECONNECT_DELAY = 5   # uzilganda qayta urinish oralig'i (soniya)
CMD_TIMEOUT     = 30  # buyruq bajarish maksimal vaqti (soniya)


# ── Tarmoq yordamchilari ─────────────────────────────────────

def send_msg(sock, text: str):
    data = text.encode("utf-8")
    sock.sendall(len(data).to_bytes(4, "big") + data)


def recv_msg(sock) -> str | None:
    raw_len = _recvn(sock, 4)
    if not raw_len:
        return None
    n = int.from_bytes(raw_len, "big")
    raw = _recvn(sock, n)
    return raw.decode("utf-8") if raw else None


def _recvn(sock, n) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


# ── Buyruq bajarish ──────────────────────────────────────────

def _detect_encoding() -> str:
    """
    Windows CMD ning joriy kod sahifasini aniqlaydi.
    Linux/Mac da har doim utf-8 qaytaradi.
    """
    if platform.system() != "Windows":
        return "utf-8"
    try:
        # `chcp` buyrug'i joriy kod sahifasini chiqaradi: "Active code page: 866"
        out = subprocess.check_output("chcp", shell=True, stderr=subprocess.DEVNULL)
        # oxirgi raqamlarni olamiz
        page = out.decode("ascii", errors="ignore").strip().split()[-1].rstrip(".")
        return f"cp{page}"
    except Exception:
        return "cp866"   # Rus Windows uchun standart


# Bir marta aniqlab, modul darajasida saqlaymiz
_CMD_ENCODING = _detect_encoding()


def run_command(cmd: str) -> tuple[str, str]:
    """
    Buyruqni shell orqali bajaradi.
    Windows CMD encoding ni avtomatik aniqlab UTF-8 ga o'giradi.
    (stdout, stderr) juftligini qaytaradi.
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,   # text=False — xom bytes olamiz
            timeout=CMD_TIMEOUT,
        )
        stdout = result.stdout.decode(_CMD_ENCODING, errors="replace")
        stderr = result.stderr.decode(_CMD_ENCODING, errors="replace")
        return stdout, stderr
    except subprocess.TimeoutExpired:
        return "", f"[Xato] Buyruq {CMD_TIMEOUT}s dan oshdi, to'xtatildi."
    except Exception as e:
        return "", f"[Xato] {e}"


# ── Asosiy agent ─────────────────────────────────────────────

class ClientAgent:
    def __init__(self, reload=None, name: str = None, on_lower=None,
                 on_update=None, on_audio=None, on_audio_control=None):
        self._sock = None
        self._sock_lock = threading.Lock()
        self.reload = reload
        self.on_lower = on_lower
        self.on_update = on_update
        self.on_audio = on_audio                   # (bytes, speed, fmt, start_at) -> None
        self.on_audio_control = on_audio_control    # (action: str) -> None
        self._running = True
        self.name = name or CLIENT_NAME

    def rename(self, new_name: str):
        """
        Talaba LoginFrame orqali ismini kiritganda chaqiriladi.
        Serverga qayta "hello" xabarini yuborib, ko'rinadigan nomni
        yangilaydi (server buni eski manzil bo'yicha yangilaydi).
        """
        self.name = new_name or self.name
        with self._sock_lock:
            sock = self._sock
        if sock:
            try:
                send_msg(sock, json.dumps({"type": "hello", "name": self.name}))
            except Exception as e:
                print(f"[!] Nomni yangilashda xatolik: {e}")

    def run(self):
        print(f"[{self.name}] Agent ishga tushdi.")
        print(f"Server: {SERVER_HOST}:{SERVER_PORT}")
        while self._running:
            try:
                self._connect_and_listen()
            except Exception as e:
                print(f"[!] Xato: {e}")
            if self._running:
                print(f"[~] {RECONNECT_DELAY}s dan keyin qayta urinadi…")
                time.sleep(RECONNECT_DELAY)

    def _connect_and_listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SERVER_HOST, SERVER_PORT))
        with self._sock_lock:
            self._sock = sock
        print(f"[✓] Serverga ulandi: {SERVER_HOST}:{SERVER_PORT}")

        # O'zini tanishtirish
        hello = json.dumps({"type": "hello", "name": self.name})
        send_msg(sock, hello)

        # Buyruqlarni tinglash
        while True:
            raw = recv_msg(sock)
            if raw is None:
                print("[!] Server uzildi.")
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            xabar_turi=msg.get("type")
            if xabar_turi == "command":
                cmd = msg.get("cmd", "").strip()
                if not cmd:
                    continue
                print(f"[→] Buyruq: {cmd}")
                threading.Thread(
                    target=self._execute_and_reply,
                    args=(sock, cmd),
                    daemon=True,
                ).start()

            elif xabar_turi == "config":
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    f.write(json.dumps(msg.get("config", {})))
                if self.reload:
                    self.reload()

            elif xabar_turi == "lower":
                if self.on_lower:
                    self.on_lower()

            elif xabar_turi == "update":
                if self.on_update:
                    self.on_update()

            elif xabar_turi == "audio_data":
                # Audio faylni base64 formatida qabul qilish.
                # delay_sec - "xabar qabul qilingandan necha soniya keyin
                # boshlash kerak". Bu server/client soat farqidan MUSTAQIL
                # ishlaydi (Unix timestamp solishtirish o'rniga nisbiy
                # kechikish ishlatiladi) - barcha talabalar deyarli bir
                # vaqtda xabarni oladi, shuning uchun bir xil kechikish
                # bilan boshlash amalda sinxron eshitilishini ta'minlaydi.
                if self.on_audio:
                    import base64
                    try:
                        audio_bytes = base64.b64decode(msg.get("data", ""))
                        speed = float(msg.get("speed", 1.0))
                        fmt = msg.get("format", "mp3")
                        delay_sec = float(msg.get("delay_sec", 0))
                        self.on_audio(audio_bytes, speed, fmt, delay_sec)
                    except Exception as e:
                        print(f"[Audio] Qabul qilishda xatolik: {e}")

            elif xabar_turi == "audio_control":
                # action: "stop"/"pause"/"play". delay_sec - xuddi
                # audio_data'dagi kabi, sinxron to'xtatish uchun.
                if self.on_audio_control:
                    action = msg.get("action", "stop")
                    delay_sec = float(msg.get("delay_sec", 0))
                    self.on_audio_control(action, delay_sec)



        sock.close()
        self._sock = None

    def _execute_and_reply(self, sock, cmd):
        stdout, stderr = run_command(cmd)
        print(f"[←] Natija: {stdout[:80]!r}" + (" …" if len(stdout) > 80 else ""))
        try:
            payload = json.dumps({
                "type":   "output",
                "output": stdout,
                "error":  stderr,
            })
            send_msg(sock, payload)
        except Exception as e:
            print(f"[!] Natijani yuborishda xato: {e}")

    def stop(self):
        self._running = False
        if self._sock:
            self._sock.close()


# ── Ishga tushirish ──────────────────────────────────────────

if __name__ == "__main__":
    agent = ClientAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n[Agent to'xtatildi]")
        agent.stop()