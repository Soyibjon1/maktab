"""
audio_isolate.py — Talaba kompyuterida ovozlarni boshqarish moduli:
  1) Barcha boshqa dasturlar (Chrome, YouTube, o'yinlar) ovozini to'liq o'chirish (mute).
  2) Ustoz gapirayotganda boshqa dasturlar ovozini pasaytirish (audio ducking ~15%)
     va ustoz gapirib bo'lgach avvalgi balandligiga qaytarish.
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


class AudioManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._current_pid = os.getpid()

        # Rejimlar
        self._mute_all_active = False
        self._duck_active = False
        self._duck_level = 0.15          # 15% balandlikka tushirish

        # Har bir sessiyaning ducking dan oldingi original ovozi: {pid: float}
        self._saved_volumes = {}

        # Fon monitoringi
        self._monitor_running = False
        self._monitor_thread = None

    # ──────────────────────── MUTE ALL (TO'LIQ O'CHIRISH) ────────────────────────

    def set_mute_all(self, state: bool):
        """Barcha boshqa dasturlar ovozini to'liq o'chiradi (mute) yoki tiklaydi."""
        with self._lock:
            self._mute_all_active = bool(state)
            if self._mute_all_active:
                self._ensure_monitor()

        if not PYCAW_AVAILABLE:
            return

        threading.Thread(target=self._apply_mute_all_async, args=(state,), daemon=True).start()

    def _apply_mute_all_async(self, state: bool):
        try:
            if comtypes:
                comtypes.CoInitialize()
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    vol = session.SimpleAudioVolume
                    if not vol:
                        continue
                    proc = session.Process
                    pid = proc.pid if proc else None
                    if pid == self._current_pid:
                        # Talaba / Ustoz ovozi doim yoqilgan qoladi
                        if vol.GetMute():
                            vol.SetMute(0, None)
                    else:
                        vol.SetMute(1 if state else 0, None)
                except Exception:
                    pass
        except Exception as e:
            print(f"[AudioManager] Mute all xatosi: {e}")
        finally:
            if comtypes:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

    # ──────────────────────── DUCKING (OVOZNI PASAYTIRISH) ────────────────────────

    def set_ducking(self, active: bool, level: float = 0.15):
        """Ustoz gapirayotganda boshqa dasturlar ovozini pasaytiradi (active=True)
        yoki avvalgi holatiga qaytaradi (active=False).
        """
        with self._lock:
            # Agar umumiy mute yoqilgan bo'lsa, ducking shart emas (allaqachon ovoz o'chirilgan)
            if self._mute_all_active and active:
                return
            if self._duck_active == bool(active):
                return
            self._duck_active = bool(active)
            self._duck_level = float(level)
            if self._duck_active:
                self._ensure_monitor()

        if not PYCAW_AVAILABLE:
            return

        threading.Thread(target=self._apply_ducking_async, args=(active, level), daemon=True).start()

    def _apply_ducking_async(self, active: bool, level: float):
        try:
            if comtypes:
                comtypes.CoInitialize()
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    vol = session.SimpleAudioVolume
                    if not vol:
                        continue
                    proc = session.Process
                    pid = proc.pid if proc else None
                    if pid == self._current_pid:
                        # Ustoz ovozi doim to'liq eshitiladi
                        if vol.GetMute():
                            vol.SetMute(0, None)
                        continue

                    if active:
                        # Avvalgi balandlikni eslab qolamiz
                        cur_vol = vol.GetMasterVolume()
                        if pid not in self._saved_volumes:
                            self._saved_volumes[pid] = cur_vol
                        # Ovozni belgilangan darajagacha pasaytiramiz
                        vol.SetMasterVolume(min(cur_vol, level), None)
                    else:
                        # Avvalgi balandlikni qayta tiklaymiz
                        saved = self._saved_volumes.pop(pid, 1.0)
                        vol.SetMasterVolume(saved, None)
                except Exception:
                    pass

            if not active:
                self._saved_volumes.clear()
        except Exception as e:
            print(f"[AudioManager] Ducking xatosi: {e}")
        finally:
            if comtypes:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

    # ──────────────────────── FON MONITORINGI ────────────────────────

    def _ensure_monitor(self):
        if self._monitor_running:
            return
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _monitor_loop(self):
        if not PYCAW_AVAILABLE or not comtypes:
            return
        try:
            comtypes.CoInitialize()
            while self._monitor_running and (self._mute_all_active or self._duck_active):
                try:
                    # Agar o'quvchi umumiy kompyuter ovozini o'chirgan bo'lsa, uni yoqamiz
                    try:
                        device = AudioUtilities.GetSpeakers()
                        if device and hasattr(device, "EndpointVolume") and device.EndpointVolume:
                            if device.EndpointVolume.GetMute():
                                device.EndpointVolume.SetMute(0, None)
                    except Exception:
                        pass

                    sessions = AudioUtilities.GetAllSessions()
                    for session in sessions:
                        try:
                            vol = session.SimpleAudioVolume
                            if not vol:
                                continue
                            proc = session.Process
                            pid = proc.pid if proc else None
                            if pid == self._current_pid:
                                if vol.GetMute():
                                    vol.SetMute(0, None)
                                continue

                            if self._mute_all_active:
                                if not vol.GetMute():
                                    vol.SetMute(1, None)
                            elif self._duck_active:
                                cur = vol.GetMasterVolume()
                                if cur > self._duck_level:
                                    if pid not in self._saved_volumes:
                                        self._saved_volumes[pid] = cur
                                    vol.SetMasterVolume(self._duck_level, None)
                        except Exception:
                            pass
                except Exception:
                    pass
                time.sleep(1.2)
        finally:
            self._monitor_running = False
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    def stop_all(self):
        self._monitor_running = False
        self.set_mute_all(False)
        self.set_ducking(False)


_audio_mgr = AudioManager()


def set_mute_all(state: bool):
    """Barcha boshqa dasturlar ovozini to'liq o'chirish (True) yoki yoqish (False)."""
    _audio_mgr.set_mute_all(state)


def set_ducking(active: bool, level: float = 0.15):
    """Boshqa dasturlar ovozini pasaytirish (True) yoki avvalgi holatga qaytarish (False)."""
    _audio_mgr.set_ducking(active, level)


# Eski funksiyalar bilan moslik uchun
def start_audio_isolation() -> bool:
    _audio_mgr.set_mute_all(True)
    return True


def stop_audio_isolation():
    _audio_mgr.stop_all()


def is_audio_isolation_active() -> bool:
    return _audio_mgr._mute_all_active


def set_audio_isolation(state: bool):
    _audio_mgr.set_mute_all(state)
