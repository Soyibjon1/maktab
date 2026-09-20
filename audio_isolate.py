"""
audio_isolate.py — Talaba kompyuterida faqat Talaba (Python) dasturi ovozini qoldirish,
qolgan barcha ilovalar (brauzer, youtube, o'yinlar, tizim tovushlari) ovozini o'chirish (mute).
"""

import os
import threading
import time

try:
    import comtypes
    from pycaw.pycaw import AudioUtilities
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False
    comtypes = None
    AudioUtilities = None


class AudioIsolator:
    def __init__(self):
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._current_pid = os.getpid()

    def start(self) -> bool:
        """Boshqa barcha ilovalar ovozini o'chiradi va doimiy nazorat qiladi."""
        if not PYCAW_AVAILABLE:
            print("[AudioIsolate] pycaw yoki comtypes kutubxonasi topilmadi!")
            return False

        with self._lock:
            if self._running:
                return True
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
        print("[AudioIsolate] Boshqa barcha audio o'chirildi (faqat Ustoz ovozi qoldi).")
        return True

    def stop(self):
        """Barcha ilovalarning ovozini qayta yoqadi (unmute)."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if PYCAW_AVAILABLE:
            threading.Thread(target=self._unmute_all, daemon=True).start()
        print("[AudioIsolate] Barcha ilovalar ovozi qayta tiklandi.")

    def is_active(self) -> bool:
        return self._running

    def _unmute_all(self):
        try:
            comtypes.CoInitialize()
            try:
                sessions = AudioUtilities.GetAllSessions()
                for session in sessions:
                    try:
                        volume = session.SimpleAudioVolume
                        if volume and volume.GetMute():
                            volume.SetMute(0, None)
                    except Exception:
                        pass
            finally:
                comtypes.CoUninitialize()
        except Exception as e:
            print(f"[AudioIsolate] Unmute xatosi: {e}")

    def _isolate_sessions_once(self):
        try:
            # 1. Master volumeni unmute qilamiz (agar talaba kompyuter umumiy ovozini o'chirgan bo'lsa)
            try:
                device = AudioUtilities.GetSpeakers()
                if device and hasattr(device, "EndpointVolume") and device.EndpointVolume:
                    if device.EndpointVolume.GetMute():
                        device.EndpointVolume.SetMute(0, None)
            except Exception:
                pass

            # 2. Barcha audio sessiyalarni aylanib chiqamiz
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    volume = session.SimpleAudioVolume
                    if not volume:
                        continue
                    proc = session.Process
                    session_pid = proc.pid if proc else None

                    # Agar joriy Python jarayoni (Talaba) bo'lsa — ovozini yoqamiz
                    if session_pid == self._current_pid:
                        if volume.GetMute():
                            volume.SetMute(0, None)
                    else:
                        # Boshqa barcha ilovalarning (Chrome, o'yinlar, brauzer) ovozini o'chiramiz
                        if not volume.GetMute():
                            volume.SetMute(1, None)
                except Exception:
                    pass
        except Exception as e:
            print(f"[AudioIsolate] Xatolik: {e}")

    def _monitor_loop(self):
        try:
            comtypes.CoInitialize()
            while self._running:
                self._isolate_sessions_once()
                time.sleep(1.0)
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


_isolator = AudioIsolator()


def start_audio_isolation() -> bool:
    return _isolator.start()


def stop_audio_isolation():
    _isolator.stop()


def is_audio_isolation_active() -> bool:
    return _isolator.is_active()


def set_audio_isolation(state: bool):
    if state:
        start_audio_isolation()
    else:
        stop_audio_isolation()


if __name__ == "__main__":
    print("Testing audio isolation for 5 seconds...")
    start_audio_isolation()
    time.sleep(5)
    stop_audio_isolation()
    print("Done.")
