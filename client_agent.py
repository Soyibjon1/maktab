import socket
import subprocess
import json
import threading
import time
import os
import sys
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# ── Standart Sozlamalar ──────────────────────────────────────

DEFAULT_HOSTS = ["192.168.100.250", "192.168.1.100", "127.0.0.1"]
SERVER_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 3475

# Client nomi: muhit o'zgaruvchisi > kompyuter nomi
CLIENT_NAME = os.environ.get("CLIENT_NAME") or platform.node() or "Unknown-PC"

RECONNECT_DELAY = 3   # uzilganda qayta urinish oralig'i (soniya)
CONNECT_TIMEOUT = 2.5 # har bir IP ga ulanish kutish vaqti (soniya)
CMD_TIMEOUT     = 30  # buyruq bajarish maksimal vaqti (soniya)


def load_server_hosts() -> list[str]:
    """config.json yoki argumentlardan server IP-manzillar ro'yxatini yuklaydi."""
    hosts = []
    if len(sys.argv) > 1 and sys.argv[1].strip():
        hosts.append(sys.argv[1].strip())

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                loaded = cfg.get("server_hosts", [])
                if isinstance(loaded, list):
                    for h in loaded:
                        h_str = str(h).strip()
                        if h_str and h_str not in hosts:
                            hosts.append(h_str)
        except Exception as e:
            print(f"[Config] server_hosts o'qishda xato: {e}")

    for def_h in DEFAULT_HOSTS:
        if def_h not in hosts:
            hosts.append(def_h)

    return hosts


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
    if platform.system() != "Windows":
        return "utf-8"
    try:
        out = subprocess.check_output("chcp", shell=True, stderr=subprocess.DEVNULL)
        page = out.decode("ascii", errors="ignore").strip().split()[-1].rstrip(".")
        return f"cp{page}"
    except Exception:
        return "cp866"


_CMD_ENCODING = _detect_encoding()


def run_command(cmd: str) -> tuple[str, str]:
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
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
                 on_update=None, on_audio=None, on_audio_control=None,
                 on_screen_share=None, on_audio_isolate=None,
                 on_host_change=None):
        self._sock = None
        self._sock_lock = threading.Lock()
        self.reload = reload
        self.on_lower = on_lower
        self.on_update = on_update
        self.on_audio = on_audio                   # (bytes, speed, fmt, start_at) -> None
        self.on_audio_control = on_audio_control    # (action: str) -> None
        self.on_screen_share = on_screen_share      # (action, host, port) -> None
        self.on_audio_isolate = on_audio_isolate    # (state: bool) -> None
        self.on_host_change = on_host_change        # (new_host: str) -> None
        self._running = True
        self.name = name or CLIENT_NAME
        self.server_hosts = load_server_hosts()
        self.active_host = self.server_hosts[0] if self.server_hosts else "127.0.0.1"

    def rename(self, new_name: str):
        self.name = new_name or self.name
        with self._sock_lock:
            sock = self._sock
        if sock:
            try:
                send_msg(sock, json.dumps({"type": "hello", "name": self.name}))
            except Exception as e:
                print(f"[!] Nomni yangilashda xatolik: {e}")

    def update_server_hosts_list(self, new_hosts: list[str]):
        """Ustozdan yangi IP manzillar ro'yxati kelganda saqlash."""
        if not new_hosts or not isinstance(new_hosts, list):
            return
        cleaned = [str(h).strip() for h in new_hosts if str(h).strip()]
        if not cleaned:
            return
        self.server_hosts = cleaned
        current_cfg = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    current_cfg = json.load(f)
            except Exception:
                current_cfg = {}
        current_cfg["server_hosts"] = cleaned
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(current_cfg, f, ensure_ascii=False, indent=2)
            print(f"[Agent] Yangi server_hosts saqlandi: {cleaned}")
        except Exception as e:
            print(f"[Agent] server_hosts saqlashda xato: {e}")

    def run(self):
        print(f"[{self.name}] Agent ishga tushdi.")
        print(f"Ulanish uchun IP ro'yxati: {self.server_hosts}")

        while self._running:
            sock = None
            connected_host = None

            # Ro'yxatdagi har bir IP manzilga navbatma-navbat ulanishga harakat qilish
            for host in list(self.server_hosts):
                if not self._running:
                    break
                print(f"[~] {host}:{SERVER_PORT} ga ulanishga harakat qilinmoqda...")
                try:
                    s = socket.create_connection((host, SERVER_PORT), timeout=CONNECT_TIMEOUT)
                    sock = s
                    connected_host = host
                    break
                except Exception:
                    continue

            if sock and connected_host:
                self.active_host = connected_host
                if self.on_host_change:
                    try:
                        self.on_host_change(connected_host)
                    except Exception:
                        pass
                try:
                    self._listen(sock, connected_host)
                except Exception as e:
                    print(f"[!] Aloqa uzildi: {e}")
            else:
                print(f"[!] Serverlar ro'yxatidagi hech qaysi IP ga ulanib bo'lmadi.")

            if self._running:
                # Yangilangan server_hosts ni qayta o'qish (agar faylda o'zgargan bo'lsa)
                self.server_hosts = load_server_hosts()
                print(f"[~] {RECONNECT_DELAY}s dan keyin qayta urinadi…")
                time.sleep(RECONNECT_DELAY)

    def _listen(self, sock: socket.socket, host: str):
        with self._sock_lock:
            self._sock = sock
        print(f"[✓] Serverga muvaffaqiyatli ulandi: {host}:{SERVER_PORT}")

        # O'zini tanishtirish
        hello = json.dumps({"type": "hello", "name": self.name})
        send_msg(sock, hello)

        # Buyruqlarni tinglash
        while self._running:
            raw = recv_msg(sock)
            if raw is None:
                print("[!] Serverdan aloqa to'xtadi.")
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            xabar_turi = msg.get("type")

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
                cfg_data = msg.get("config", {})
                current_cfg = {}
                if os.path.exists(CONFIG_PATH):
                    try:
                        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                            current_cfg = json.load(f)
                    except Exception:
                        current_cfg = {}
                if isinstance(cfg_data, dict):
                    current_cfg.update(cfg_data)
                elif isinstance(cfg_data, str):
                    try:
                        parsed = json.loads(cfg_data)
                        if isinstance(parsed, dict):
                            current_cfg.update(parsed)
                    except Exception:
                        pass
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(current_cfg, f, ensure_ascii=False, indent=2)

                if "server_hosts" in current_cfg and isinstance(current_cfg["server_hosts"], list):
                    self.server_hosts = current_cfg["server_hosts"]

                if self.reload:
                    self.reload()
                if self.on_audio_isolate and "isolate_audio" in current_cfg:
                    self.on_audio_isolate(bool(current_cfg["isolate_audio"]))

            elif xabar_turi == "update_server_hosts":
                hosts = msg.get("hosts", [])
                self.update_server_hosts_list(hosts)

            elif xabar_turi == "input_lock":
                target = msg.get("target", "")
                state = bool(msg.get("state", True))
                current_cfg = {}
                if os.path.exists(CONFIG_PATH):
                    try:
                        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                            current_cfg = json.load(f)
                    except Exception:
                        current_cfg = {}
                if target in ("keyboard", "all"):
                    current_cfg["input_lock_keyboard"] = state
                if target in ("mouse", "all"):
                    current_cfg["input_lock_mouse"] = state
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(current_cfg, f, ensure_ascii=False, indent=2)
                if self.reload:
                    self.reload()

            elif xabar_turi == "close_blocked_programs":
                # CS 1.6 turlari, Roblox, Arduino kabi taqiqlangan dasturlarni darhol yopish
                targets = msg.get("targets", None)
                try:
                    from process_guardian import kill_all_blocked
                    killed = kill_all_blocked(targets)
                    reply_text = f"Yopilgan dasturlar: {', '.join(killed)}" if killed else "Hech qanday taqiqlangan dastur topilmadi."
                    send_msg(sock, json.dumps({
                        "type": "output",
                        "output": f"[{self.name}] {reply_text}\n",
                        "error": "",
                    }))
                except Exception as e:
                    print(f"[Guardian] Yopishda xatolik: {e}")

            elif xabar_turi == "isolate_audio":
                state = bool(msg.get("state", True))
                current_cfg = {}
                if os.path.exists(CONFIG_PATH):
                    try:
                        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                            current_cfg = json.load(f)
                    except Exception:
                        current_cfg = {}
                current_cfg["isolate_audio"] = state
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(current_cfg, f, ensure_ascii=False, indent=2)
                if self.on_audio_isolate:
                    self.on_audio_isolate(state)

            elif xabar_turi == "lower":
                if self.on_lower:
                    self.on_lower()

            elif xabar_turi == "update":
                if self.on_update:
                    self.on_update()

            elif xabar_turi == "audio_data":
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
                if self.on_audio_control:
                    action = msg.get("action", "stop")
                    delay_sec = float(msg.get("delay_sec", 0))
                    self.on_audio_control(action, delay_sec)

            elif xabar_turi == "screen_share":
                if self.on_screen_share:
                    action = msg.get("action", "start")
                    target_host = msg.get("host") or self.active_host
                    try:
                        port = int(msg.get("port", 3480))
                    except Exception:
                        port = 3480
                    self.on_screen_share(action, target_host, port)

        try:
            sock.close()
        except Exception:
            pass
        with self._sock_lock:
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
        with self._sock_lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None


if __name__ == "__main__":
    agent = ClientAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n[Agent to'xtatildi]")
        agent.stop()
