"""
process_guardian.py — O'quvchi kompyuterida taqiqlangan dasturlarni (CS 1.6, Roblox, Arduino va b.)
darhol yopish va fon rejimida ularni bloklab turish moduli.
"""

import os
import platform
import subprocess
import threading
import time
from typing import Iterable, Set

# Standart taqiqlangan dasturlar bazasi (CS 1.6 ning barcha turlari, Roblox, Arduino va boshqalar)
DEFAULT_BLOCKED_PROCESSES = {
    # Counter-Strike 1.6 va uning yig'malari
    "hl.exe",
    "cstrike.exe",
    "cs.exe",
    "cs16.exe",
    "counter-strike.exe",
    "counterstrike.exe",
    "cs_classic.exe",
    "strike.exe",
    "czero.exe",

    # Roblox
    "robloxplayerbeta.exe",
    "robloxplayerlauncher.exe",
    "robloxstudiobeta.exe",
    "robloxcrashhandler.exe",

    # Arduino IDE (o'qituvchi yopishni buyurganda)
    "arduino.exe",
    "arduino ide.exe",
    "arduino-ide.exe",
    "arduino-cli.exe",

    # Chalg'ituvchi boshqa dasturlar
    "telegram.exe",
    "discord.exe",
}

_monitor_running = False
_monitor_thread = None
_active_blocked_set: Set[str] = set(DEFAULT_BLOCKED_PROCESSES)
_lock = threading.Lock()


def set_blocked_list(names: Iterable[str]):
    """Taqiqlangan jarayonlar ro'yxatini yangilaydi."""
    global _active_blocked_set
    with _lock:
        _active_blocked_set = {n.strip().lower() for n in names if n.strip()}


def add_to_blocked(names: Iterable[str]):
    global _active_blocked_set
    with _lock:
        for n in names:
            if n.strip():
                _active_blocked_set.add(n.strip().lower())


def kill_process_by_name(proc_name: str) -> bool:
    """Bitta jarayon nomini taskkill orqali majburiy yopadi."""
    if platform.system() != "Windows":
        return False
    try:
        # /F — majburiy, /T — bolalar jarayonlari bilan, /IM — tasvir nomi
        cmd = f'taskkill /F /T /IM "{proc_name}"'
        res = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False


def kill_all_blocked(targets: Iterable[str] | None = None) -> list[str]:
    """
    Belgilangan (yoki barcha) taqiqlangan dasturlarni darhol yopadi.
    Yopishga urinilgan dasturlar ro'yxatini qaytaradi.
    """
    to_kill = set(targets) if targets else _active_blocked_set
    killed = []

    # psutil mavjud bo'lsa, avval ro'yxatda bor-yo'qligini tekshirib yopish tezroq bo'ladi
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info["name"] or "").lower()
                if name in to_kill:
                    proc.kill()
                    killed.append(name)
            except Exception:
                pass
    except Exception:
        # psutil bo'lmasa to'g'ridan-to'g'ri taskkill chaqiramiz
        for proc_name in to_kill:
            if kill_process_by_name(proc_name):
                killed.append(proc_name)

    return killed


def _monitor_loop(interval: float):
    global _monitor_running
    while _monitor_running:
        try:
            with _lock:
                targets = set(_active_blocked_set)
            kill_all_blocked(targets)
        except Exception:
            pass
        time.sleep(interval)


def start_auto_guard(interval: float = 2.0):
    """Fonda taqiqlangan dasturlarni avtomatik o'chirib turishni yoqadi."""
    global _monitor_running, _monitor_thread
    with _lock:
        if _monitor_running:
            return
        _monitor_running = True
        _monitor_thread = threading.Thread(
            target=_monitor_loop, args=(interval,), daemon=True
        )
        _monitor_thread.start()
    print("[ProcessGuardian] Taqiqlangan dasturlarni avto-yopish faollashdi.")


def stop_auto_guard():
    """Fon rejimini to'xtatadi."""
    global _monitor_running
    with _lock:
        _monitor_running = False
    print("[ProcessGuardian] Avto-yopish to'xtatildi.")
