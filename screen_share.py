from __future__ import annotations
import io
import socket
import threading
import time
import tkinter as tk
from PIL import Image, ImageTk


class StudentScreenShareViewer:
    MIN_WIDTH = 320
    MIN_HEIGHT = 190

    def __init__(self, root: tk.Tk):
        self.root = root
        self.window: tk.Toplevel | None = None
        self.title_bar: tk.Frame | None = None
        self.label: tk.Label | None = None
        self.resize_grip: tk.Label | None = None
        self._sock: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._photo = None
        self._last_image: Image.Image | None = None
        self._large = False
        self._normal_geometry: str | None = None
        self._host = ""
        self._port = 3480

        # Sudrash/resize uchun vaqtinchalik qiymatlar
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_win_x = 0
        self._drag_win_y = 0
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_start_w = 0
        self._resize_start_h = 0

        # UI qotib qolmasligi uchun: har frame uchun alohida root.after yig'ilib ketmaydi
        self._render_pending = False
        self._resize_after_id: str | None = None
        self._image_lock = threading.Lock()

    def start(self, host: str, port: int = 3480):
        host = str(host or "").strip()
        if not host:
            return
        port = int(port or 3480)

        # Eski ulanish bo'lsa tozalab, yangi streamga ulanadi.
        self.stop(destroy_window=False)
        self._host = host
        self._port = port
        self._running = True
        self._ensure_window()
        self._set_status(f"Ustoz ekraniga ulanmoqda: {host}:{port}")
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def stop(self, destroy_window: bool = True):
        self._running = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        if destroy_window:
            self.root.after(0, self._destroy_window)

    # ───────── UI ─────────

    def _ensure_window(self):
        if self.window and self.window.winfo_exists():
            self.window.lift()
            self.window.attributes("-topmost", True)
            return

        win = tk.Toplevel(self.root)
        self.window = win
        win.overrideredirect(True)          # O'zimiz custom titlebar chizamiz
        win.attributes("-topmost", True)
        win.configure(bg="#080808")
        win.protocol("WM_DELETE_WINDOW", self._fake_close)

        outer = tk.Frame(win, bg="#111111", bd=1, relief="solid")
        outer.pack(fill="both", expand=True)

        self.title_bar = tk.Frame(outer, bg="#202020", height=34, cursor="fleur")
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        title = tk.Label(
            self.title_bar,
            text="  Ustoz ekrani  •  tepa qismidan sudrab joyini almashtiring",
            bg="#202020",
            fg="white",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        )
        title.pack(side="left", fill="both", expand=True)

        button_box = tk.Frame(self.title_bar, bg="#202020")
        button_box.pack(side="right", fill="y")

        # _ tugmasi: haqiqiy minimizatsiya emas, kichik oynaga qaytaradi.
        # btn_small = tk.Button(
        #     button_box,
        #     text="—",
        #     width=4,
        #     bd=0,
        #     bg="#2b2b2b",
        #     fg="white",
        #     activebackground="#3a3a3a",
        #     activeforeground="white",
        #     command=self._set_small_geometry,
        # )
        # btn_small.pack(side="left", fill="y")

        btn_toggle = tk.Button(
            button_box,
            text="□",
            width=4,
            bd=0,
            bg="#2b2b2b",
            fg="white",
            activebackground="#3a3a3a",
            activeforeground="white",
            command=self._toggle_size,
        )
        btn_toggle.pack(side="left", fill="y")

        # # X ko'rinadi, lekin oyna yopilmaydi.
        # btn_close = tk.Button(
        #     button_box,
        #     text="×",
        #     width=4,
        #     bd=0,
        #     bg="#3a1f1f",
        #     fg="white",
        #     activebackground="#5a2a2a",
        #     activeforeground="white",
        #     command=self._fake_close,
        # )
        # btn_close.pack(side="left", fill="y")

        body = tk.Frame(outer, bg="black")
        body.pack(fill="both", expand=True)

        self.label = tk.Label(body, bg="black", fg="white", text="Ustoz ekrani yuklanmoqda…")
        self.label.pack(fill="both", expand=True)

        self.resize_grip = tk.Label(
            body,
            text="◢",
            bg="black",
            fg="#d0d0d0",
            cursor="size_nw_se",
            font=("Segoe UI", 13, "bold"),
        )
        self.resize_grip.place(relx=1.0, rely=1.0, anchor="se")

        # Tepa paneldan sudrash
        for widget in (self.title_bar, title):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag_window)
            widget.bind("<Double-Button-1>", self._toggle_size)

        # Past-o'ng burchakdan resize
        self.resize_grip.bind("<ButtonPress-1>", self._start_resize)
        self.resize_grip.bind("<B1-Motion>", self._resize_window)

        # Rasmga ikki marta bosilsa katta/kichik bo'ladi. Oddiy click endi tasodifan sakratmaydi.
        self.label.bind("<Double-Button-1>", self._toggle_size)
        win.bind("<Escape>", lambda e: "break")
        win.bind("<Alt-F4>", lambda e: "break")
        win.bind("<Configure>", self._on_configure)

        self._set_small_geometry()
        win.lift()

    def _set_small_geometry(self):
        if not self.window:
            return
        sw = self.root.winfo_screenwidth()
        width = min(640, max(420, sw // 3))
        height = int(width * 9 / 16) + 34
        x = max(0, sw - width - 18)
        y = 18
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self._normal_geometry = self.window.geometry()
        self._large = False
        self._schedule_redraw()

    def _set_large_geometry(self):
        if not self.window:
            return
        if not self._large:
            self._normal_geometry = self.window.geometry()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.window.geometry(f"{sw}x{sh}+0+0")
        self._large = True
        self._schedule_redraw()

    def _toggle_size(self, event=None):
        if self._large:
            self._restore_normal_geometry()
        else:
            self._set_large_geometry()
        return "break"

    def _restore_normal_geometry(self):
        if not self.window:
            return
        if self._normal_geometry:
            self.window.geometry(self._normal_geometry)
        else:
            self._set_small_geometry()
            return
        self._large = False
        self._schedule_redraw()

    def _fake_close(self):
        # O'quvchi X bossayam oyna yopilmaydi.
        self._set_status("Bu oynani faqat ustoz to'xtata oladi")
        if self.window:
            self.window.after(1200, self._schedule_redraw)
        return "break"

    def _start_drag(self, event):
        if not self.window:
            return "break"
        if self._large:
            # Fullscreen holatda sudrash boshlansa, avval normal holatga qaytadi.
            self._restore_normal_geometry()
            self.window.update_idletasks()
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._drag_win_x = self.window.winfo_x()
        self._drag_win_y = self.window.winfo_y()
        return "break"

    def _drag_window(self, event):
        if not self.window:
            return "break"
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        x = self._drag_win_x + dx
        y = self._drag_win_y + dy

        # Oyna butunlay ekrandan chiqib ketmasin.
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = max(self.MIN_WIDTH, self.window.winfo_width())
        h = max(self.MIN_HEIGHT, self.window.winfo_height())
        x = min(max(x, -w + 80), sw - 80)
        y = min(max(y, 0), sh - 50)
        self.window.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
        self._normal_geometry = self.window.geometry()
        return "break"

    def _start_resize(self, event):
        if not self.window:
            return "break"
        if self._large:
            self._restore_normal_geometry()
            self.window.update_idletasks()
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_start_w = self.window.winfo_width()
        self._resize_start_h = self.window.winfo_height()
        return "break"

    def _resize_window(self, event):
        if not self.window:
            return "break"
        dx = event.x_root - self._resize_start_x
        dy = event.y_root - self._resize_start_y
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = self.window.winfo_x()
        y = self.window.winfo_y()

        new_w = max(self.MIN_WIDTH, min(self._resize_start_w + dx, sw - x))
        new_h = max(self.MIN_HEIGHT, min(self._resize_start_h + dy, sh - y))
        self.window.geometry(f"{int(new_w)}x{int(new_h)}+{x}+{y}")
        self._normal_geometry = self.window.geometry()
        self._large = False
        self._schedule_redraw(delay_ms=80)
        return "break"

    def _on_configure(self, event=None):
        if self.window and event is not None and event.widget is self.window:
            if not self._large:
                self._normal_geometry = self.window.geometry()
            self._schedule_redraw(delay_ms=120)

    def _destroy_window(self):
        try:
            if self.window and self.window.winfo_exists():
                self.window.destroy()
        except Exception:
            pass
        self.window = None
        self.title_bar = None
        self.label = None
        self.resize_grip = None
        self._photo = None
        with self._image_lock:
            self._last_image = None
            self._render_pending = False

    def _set_status(self, text: str):
        def inner():
            self._ensure_window()
            if self.label:
                self.label.configure(text=text, image="", compound="center")
        self.root.after(0, inner)

    def _schedule_redraw(self, delay_ms: int = 0):
        if not self.window or not self.window.winfo_exists():
            return
        try:
            if self._resize_after_id:
                self.window.after_cancel(self._resize_after_id)
        except Exception:
            pass
        self._resize_after_id = self.window.after(delay_ms, self._request_render)

    def _request_render(self):
        if self._render_pending:
            return
        with self._image_lock:
            has_image = self._last_image is not None
        if not has_image:
            return
        self._render_pending = True
        self.root.after(0, self._render_latest_image)

    # ───────── Tarmoq ─────────

    def _recv_loop(self):
        while self._running:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((self._host, self._port))
                sock.settimeout(None)
                self._sock = sock
                self._set_status("Ustoz ekrani qabul qilinmoqda…")

                while self._running:
                    raw_len = self._recvn(sock, 4)
                    if not raw_len:
                        raise ConnectionError("stream uzildi")
                    n = int.from_bytes(raw_len, "big")
                    data = self._recvn(sock, n)
                    if not data:
                        raise ConnectionError("frame qabul qilinmadi")

                    img = Image.open(io.BytesIO(data)).convert("RGB")
                    with self._image_lock:
                        self._last_image = img
                    self._request_render()
            except Exception:
                if self._running:
                    self._set_status("Ustoz ekraniga qayta ulanmoqda…")
                    time.sleep(1.0)
            finally:
                try:
                    if self._sock:
                        self._sock.close()
                except Exception:
                    pass
                self._sock = None

    @staticmethod
    def _recvn(sock: socket.socket, n: int) -> bytes | None:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def _render_latest_image(self):
        with self._image_lock:
            img = self._last_image
        if img is not None:
            self._show_image(img)
        self._render_pending = False

    def _show_image(self, img: Image.Image):
        if not self.window or not self.window.winfo_exists() or not self.label:
            return

        w = max(1, self.label.winfo_width())
        h = max(1, self.label.winfo_height())
        if w < 10 or h < 10:
            self.window.update_idletasks()
            w = max(1, self.label.winfo_width())
            h = max(1, self.label.winfo_height())

        view = img.copy()
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        view.thumbnail((w, h), resample)
        self._photo = ImageTk.PhotoImage(view)
        self.label.configure(image=self._photo, text="", compound="center")
        self.label.image = self._photo
        self.window.attributes("-topmost", True)
