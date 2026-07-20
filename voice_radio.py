"""
voice_radio.py — Talaba tomoni uchun F9 push-to-talk ratsiya clienti.

F9 bosib turilganda mikrofon ovozi ustoz kompyuteridagi 3490-portga yuboriladi.
Ustoz gapirganda yoki switch yoqilgan bo'lsa boshqa talabalar gapirganda, shu client
kelgan ovozni eshittiradi.
"""

from __future__ import annotations

import base64
import json
import platform
import queue
import socket
import threading
import time
import tkinter as tk
from typing import Callable

try:
    import numpy as np
    import sounddevice as sd
    AUDIO_AVAILABLE = True
    AUDIO_IMPORT_ERROR = ""
except Exception as exc:
    np = None
    sd = None
    AUDIO_AVAILABLE = False
    AUDIO_IMPORT_ERROR = str(exc)

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK_MS = 40
BLOCKSIZE = int(SAMPLE_RATE * CHUNK_MS / 1000)
MAX_QUEUE = 80


def _recvn(sock: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def _send_json(sock: socket.socket, payload: dict, lock: threading.Lock | None = None):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    packet = len(data).to_bytes(4, "big") + data
    if lock:
        with lock:
            sock.sendall(packet)
    else:
        sock.sendall(packet)


def _recv_json(sock: socket.socket) -> dict | None:
    raw_len = _recvn(sock, 4)
    if not raw_len:
        return None
    n = int.from_bytes(raw_len, "big")
    raw = _recvn(sock, n)
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


class _AudioPlayer:
    def __init__(self, log: Callable[[str], None] | None = None):
        self.log = log or print
        self._queue: queue.Queue[bytes] = queue.Queue(MAX_QUEUE)
        self._running = False
        self._thread: threading.Thread | None = None
        self._stream = None

    def start(self) -> bool:
        if not AUDIO_AVAILABLE:
            self.log(f"[Ratsiya] Audio kutubxona topilmadi: {AUDIO_IMPORT_ERROR}")
            return False
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        try:
            self._queue.put_nowait(b"")
        except Exception:
            pass
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None

    def play(self, pcm: bytes):
        if not pcm:
            return
        if not self._running:
            self.start()
        try:
            self._queue.put_nowait(pcm)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(pcm)
            except Exception:
                pass

    def _loop(self):
        try:
            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=BLOCKSIZE,
            )
            self._stream.start()
            while self._running:
                pcm = self._queue.get()
                if not pcm:
                    continue
                arr = np.frombuffer(pcm, dtype=np.int16)
                if arr.size:
                    self._stream.write(arr.reshape(-1, 1))
        except Exception as exc:
            self.log(f"[Ratsiya] Audio chiqarishda xato: {exc}")
        finally:
            try:
                if self._stream:
                    self._stream.stop()
                    self._stream.close()
            except Exception:
                pass
            self._stream = None


class StudentVoiceRadioClient:
    def __init__(self, root: tk.Tk | None, host: str, port: int = 3490, name: str | None = None):
        self.root = root
        self.host = str(host or "").strip()
        self.port = int(port)
        self.name = name or platform.node() or "Talaba"
        self._sock: socket.socket | None = None
        self._send_lock = threading.Lock()
        self._running = False
        self._connected = False
        self._connect_thread: threading.Thread | None = None
        self._player = _AudioPlayer(print)

        self._talking = False
        self._mic_stream = None
        self._mic_queue: queue.Queue[bytes] = queue.Queue(MAX_QUEUE)
        self._mic_sender_thread: threading.Thread | None = None
        self._indicator: tk.Toplevel | None = None

    def rename(self, name: str):
        self.name = name or self.name
        self._send_safe({"type": "hello", "name": self.name})

    def start(self):
        if not AUDIO_AVAILABLE:
            print(f"[Ratsiya] sounddevice/numpy kerak: {AUDIO_IMPORT_ERROR}")
            return
        if self._running:
            return
        self._running = True
        self._player.start()
        self._connect_thread = threading.Thread(target=self._connect_loop, daemon=True)
        self._connect_thread.start()

    def stop(self):
        self._running = False
        self.stop_talk()
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        self._player.stop()
        self._hide_indicator()

    def start_talk(self):
        if not AUDIO_AVAILABLE or not self._running or self._talking:
            return
        if not self._connected:
            return
        self._talking = True
        self._mic_queue = queue.Queue(MAX_QUEUE)
        self._mic_sender_thread = threading.Thread(target=self._mic_sender_loop, daemon=True)
        self._mic_sender_thread.start()
        try:
            self._mic_stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=BLOCKSIZE,
                callback=self._mic_callback,
            )
            self._mic_stream.start()
            self._show_indicator()
        except Exception as exc:
            self._talking = False
            print(f"[Ratsiya] Mikrofon ochilmadi: {exc}")
            self._hide_indicator()

    def stop_talk(self):
        if not self._talking:
            return
        self._talking = False
        try:
            self._mic_queue.put_nowait(b"")
        except Exception:
            pass
        try:
            if self._mic_stream:
                self._mic_stream.stop()
                self._mic_stream.close()
        except Exception:
            pass
        self._mic_stream = None
        self._hide_indicator()

    def _connect_loop(self):
        while self._running:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((self.host, self.port))
                sock.settimeout(None)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._sock = sock
                self._connected = True
                _send_json(sock, {"type": "hello", "name": self.name}, self._send_lock)
                self._recv_loop(sock)
            except Exception as exc:
                if self._running:
                    print(f"[Ratsiya] Ulanmadi/qayta ulanadi: {exc}")
                    time.sleep(3)
            finally:
                self._connected = False
                try:
                    if self._sock:
                        self._sock.close()
                except Exception:
                    pass
                self._sock = None

    def _recv_loop(self, sock: socket.socket):
        while self._running:
            msg = _recv_json(sock)
            if not msg:
                break
            if msg.get("type") == "audio":
                try:
                    pcm = base64.b64decode(msg.get("data", ""))
                    self._player.play(pcm)
                except Exception:
                    pass

    def _mic_callback(self, indata, frames, time_info, status):
        if not self._talking:
            return
        try:
            self._mic_queue.put_nowait(bytes(indata))
        except queue.Full:
            pass

    def _mic_sender_loop(self):
        while self._talking and self._running:
            try:
                pcm = self._mic_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if not pcm:
                continue
            data = base64.b64encode(pcm).decode("ascii")
            if not self._send_safe({"type": "audio", "data": data}):
                break

    def _send_safe(self, payload: dict) -> bool:
        sock = self._sock
        if not sock:
            return False
        try:
            _send_json(sock, payload, self._send_lock)
            return True
        except Exception:
            return False

    # ───────── Vizual indikator: o'quvchi qachon ovoz ketayotganini ko'rsin ─────────

    def _show_indicator(self):
        if not self.root:
            return
        def inner():
            if self._indicator and self._indicator.winfo_exists():
                self._indicator.lift()
                return
            win = tk.Toplevel(self.root)
            self._indicator = win
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg="#7f1d1d")
            label = tk.Label(
                win,
                text="  F9 bosilgan — ovoz ustozga ketmoqda  ",
                bg="#7f1d1d",
                fg="white",
                font=("Segoe UI", 11, "bold"),
                padx=12,
                pady=7,
            )
            label.pack()
            sw = self.root.winfo_screenwidth()
            win.update_idletasks()
            x = max(0, (sw - win.winfo_width()) // 2)
            win.geometry(f"+{x}+12")
        try:
            self.root.after(0, inner)
        except Exception:
            pass

    def _hide_indicator(self):
        if not self.root:
            return
        def inner():
            try:
                if self._indicator and self._indicator.winfo_exists():
                    self._indicator.destroy()
            except Exception:
                pass
            self._indicator = None
        try:
            self.root.after(0, inner)
        except Exception:
            pass
