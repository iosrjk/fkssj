# -*- coding: utf-8 -*-
"""
疯狂水世界 - 礼包码自动兑换 v1.0
Windows / WeChatAppEx.exe
"""

import sys
import os
import subprocess
import importlib.util
import time
import json
import random
import threading
import ctypes
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

# ===== 自动安装运行依赖 =====
REQUIRED = {
    "win32api": "pywin32",
    "win32gui": "pywin32",
    "win32con": "pywin32",
    "win32process": "pywin32",
    "psutil": "psutil",
    "pyperclip": "pyperclip",
}

missing_pkgs = []
for mod, pkg in REQUIRED.items():
    if importlib.util.find_spec(mod) is None and pkg not in missing_pkgs:
        missing_pkgs.append(pkg)

if missing_pkgs:
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install",
             "--disable-pip-version-check", *missing_pkgs]
        )
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "依赖安装失败",
            "自动安装依赖失败：\n\n"
            + str(e)
            + "\n\n请手动执行：\n"
            + f'"{sys.executable}" -m pip install pywin32 psutil pyperclip'
        )
        raise SystemExit(1)

import psutil
import pyperclip
import win32api
import win32con
import win32gui
import win32process


APP_TITLE = "礼包码自动兑换 v1.0"
def get_app_dir():
    """
    源码运行：返回 .py 所在目录
    PyInstaller EXE：返回 .exe 所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

APP_DIR = get_app_dir()
CONFIG_FILE = APP_DIR / "giftcode_config_v1.0.json"
TARGET_EXE = "WeChatAppEx.exe"

TARGET_W = 431
TARGET_H = 788

POINTS = [
    ("gift_button", "1. 礼包码按钮"),
    ("game_input", "2. 游戏礼包码输入框"),
    ("popup_input", "3. 输入文字白色输入框"),
    ("done_button", "4. 输入文字「完成」"),
    ("confirm_button", "5. 游戏礼包码「确定」"),
    ("reward_close", "6. 奖励页空白关闭"),
]


def hwnd_process_name(hwnd):
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name()
    except Exception:
        return ""


def list_wechat_windows():
    items = []

    def enum_cb(hwnd, _):
        try:
            if not win32gui.IsWindow(hwnd):
                return
            if hwnd_process_name(hwnd).lower() != TARGET_EXE.lower():
                return

            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]

            if w < 250 or h < 400:
                return

            title = win32gui.GetWindowText(hwnd) or "(无标题)"
            items.append((hwnd, title, w, h))
        except Exception:
            pass

    win32gui.EnumWindows(enum_cb, None)
    return items


def force_window_size(hwnd, width=TARGET_W, height=TARGET_H):
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False

    try:
        rect = win32gui.GetWindowRect(hwnd)
        x, y = rect[0], rect[1]
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            x, y, width, height,
            win32con.SWP_NOACTIVATE
        )
        time.sleep(0.12)
        return True
    except Exception:
        return False


def make_lparam(x, y):
    return win32api.MAKELONG(int(x), int(y))


def background_click(hwnd, x, y):
    lp = make_lparam(x, y)
    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lp)
    time.sleep(0.02)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
    time.sleep(0.035)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)


def post_ctrl_key(hwnd, vk):
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_CONTROL, 0)
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
    time.sleep(0.04)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_CONTROL, 0)


def force_foreground(hwnd):
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        fg = win32gui.GetForegroundWindow()
        fg_tid = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
        target_tid = win32process.GetWindowThreadProcessId(hwnd)[0]
        current_tid = win32api.GetCurrentThreadId()

        attached = []
        try:
            for tid in {fg_tid, target_tid}:
                if tid and tid != current_tid:
                    ctypes.windll.user32.AttachThreadInput(current_tid, tid, True)
                    attached.append(tid)

            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.SetActiveWindow(hwnd)
        finally:
            for tid in attached:
                try:
                    ctypes.windll.user32.AttachThreadInput(current_tid, tid, False)
                except Exception:
                    pass
    except Exception:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("930x680")
        self.root.minsize(860, 620)

        self.bound_hwnd = None
        self.window_map = {}

        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.running = False

        self.window_var = tk.StringVar()
        self.window_status_var = tk.StringVar(value="正在查找 WeChatAppEx.exe...")
        self.auto_resize_var = tk.BooleanVar(value=True)

        self.progress_var = tk.StringVar(value="0 / 0")
        self.status_var = tk.StringVar(value="等待操作")

        self.delay_var = tk.StringVar(value="0.8")
        self.popup_wait_var = tk.StringVar(value="0.8")
        self.reward_wait_var = tk.StringVar(value="2.0")

        self.jitter_mode = tk.StringVar(value="3")
        self.custom_jitter_var = tk.StringVar(value="5")
        self.foreground_paste_var = tk.BooleanVar(value=False)

        self.coord_vars = {
            key: (tk.StringVar(value=""), tk.StringVar(value=""))
            for key, _ in POINTS
        }

        self.build_ui()
        self.load_config()

        # 根据当前屏幕可用高度自动限制窗口高度，避免任务栏遮挡
        self.root.update_idletasks()
        screen_h = self.root.winfo_screenheight()
        safe_h = max(620, min(720, screen_h - 90))
        self.root.geometry(f"930x{safe_h}")

        self.root.after(250, self.startup_bind)

    def build_ui(self):
        # 主界面使用可滚动容器，避免低分辨率 / Windows缩放时底部被裁切
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)

        self.main_canvas = tk.Canvas(outer, highlightthickness=0)
        self.main_scrollbar = ttk.Scrollbar(
            outer, orient="vertical", command=self.main_canvas.yview
        )
        self.main_canvas.configure(yscrollcommand=self.main_scrollbar.set)

        self.main_scrollbar.pack(side="right", fill="y")
        self.main_canvas.pack(side="left", fill="both", expand=True)

        self.scroll_frame = ttk.Frame(self.main_canvas)
        self.canvas_window = self.main_canvas.create_window(
            (0, 0), window=self.scroll_frame, anchor="nw"
        )

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.main_canvas.configure(
                scrollregion=self.main_canvas.bbox("all")
            )
        )
        self.main_canvas.bind(
            "<Configure>",
            lambda e: self.main_canvas.itemconfigure(
                self.canvas_window, width=e.width
            )
        )

        # 鼠标滚轮支持
        self.main_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.main_canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"
            )
        )

        content = self.scroll_frame

        ttk.Label(
            content,
            text="疯狂水世界 · 礼包码自动兑换 v1.0",
            font=("Microsoft YaHei UI", 17, "bold")
        ).pack(pady=(10, 4))

        # ① 窗口绑定
        bind_frame = ttk.LabelFrame(content, text="① 绑定微信小程序窗口")
        bind_frame.pack(fill="x", padx=12, pady=5)

        ttk.Label(bind_frame, text="窗口：").grid(row=0, column=0, padx=8, pady=7)

        self.window_combo = ttk.Combobox(
            bind_frame,
            textvariable=self.window_var,
            state="readonly",
            width=62
        )
        self.window_combo.grid(row=0, column=1, padx=5, pady=7, sticky="ew")

        ttk.Button(bind_frame, text="刷新", command=self.refresh_windows).grid(
            row=0, column=2, padx=5
        )
        ttk.Button(bind_frame, text="绑定", command=self.bind_selected).grid(
            row=0, column=3, padx=5
        )

        ttk.Checkbutton(
            bind_frame,
            text="绑定时自动强制为 431×788",
            variable=self.auto_resize_var,
            command=self.save_config
        ).grid(row=1, column=0, columnspan=2, padx=8, pady=(0, 5), sticky="w")

        ttk.Button(
            bind_frame,
            text="立即强制 431×788",
            command=self.resize_bound_window
        ).grid(row=1, column=2, columnspan=2, padx=5, pady=(0, 5))

        ttk.Label(
            bind_frame,
            textvariable=self.window_status_var
        ).grid(
            row=2, column=0, columnspan=4,
            padx=8, pady=(0, 6), sticky="w"
        )
        bind_frame.columnconfigure(1, weight=1)

        # ② 坐标，两列排列
        pos_frame = ttk.LabelFrame(
            content,
            text="② 点击坐标（绑定窗口内部坐标，可直接修改）"
        )
        pos_frame.pack(fill="x", padx=12, pady=5)

        # 左右两组，每组占4列
        headers = [
            (0, "步骤"), (1, "X"), (2, "Y"), (3, "操作"),
            (4, "步骤"), (5, "X"), (6, "Y"), (7, "操作")
        ]
        for col, txt in headers:
            ttk.Label(pos_frame, text=txt).grid(
                row=0, column=col, padx=4, pady=4, sticky="w"
            )

        for i, (key, label) in enumerate(POINTS):
            row = i // 2 + 1
            base_col = 0 if i % 2 == 0 else 4
            xv, yv = self.coord_vars[key]

            ttk.Label(pos_frame, text=label, width=23).grid(
                row=row, column=base_col, padx=6, pady=5, sticky="w"
            )
            ttk.Entry(pos_frame, textvariable=xv, width=7).grid(
                row=row, column=base_col + 1, padx=3
            )
            ttk.Entry(pos_frame, textvariable=yv, width=7).grid(
                row=row, column=base_col + 2, padx=3
            )
            ttk.Button(
                pos_frame,
                text="抓取",
                width=7,
                command=lambda k=key: self.capture_coord(k)
            ).grid(
                row=row, column=base_col + 3, padx=4, pady=4
            )

        ttk.Label(
            pos_frame,
            text="抓取：点击按钮后 3 秒内将鼠标移到目标位置。窗口可移动，只要内部布局不变，坐标仍有效。",
            foreground="#555"
        ).grid(
            row=4, column=0, columnspan=8,
            padx=8, pady=(4, 7), sticky="w"
        )

        # ③ 礼包码
        codes_frame = ttk.LabelFrame(content, text="③ 礼包码（每行一个）")
        codes_frame.pack(fill="both", expand=True, padx=12, pady=5)

        self.codes_text = tk.Text(
            codes_frame,
            height=10,
            font=("Consolas", 11),
            undo=True
        )
        self.codes_text.pack(fill="both", expand=True, padx=8, pady=8)

        # ④ 参数
        param_frame = ttk.LabelFrame(content, text="④ 执行参数")
        param_frame.pack(fill="x", padx=12, pady=5)

        ttk.Label(param_frame, text="普通等待").grid(row=0, column=0, padx=7, pady=5)
        ttk.Entry(param_frame, textvariable=self.delay_var, width=7).grid(row=0, column=1)
        ttk.Label(param_frame, text="秒").grid(row=0, column=2)

        ttk.Label(param_frame, text="输入弹窗等待").grid(row=0, column=3, padx=7)
        ttk.Entry(param_frame, textvariable=self.popup_wait_var, width=7).grid(row=0, column=4)
        ttk.Label(param_frame, text="秒").grid(row=0, column=5)

        ttk.Label(param_frame, text="奖励页等待").grid(row=0, column=6, padx=7)
        ttk.Entry(param_frame, textvariable=self.reward_wait_var, width=7).grid(row=0, column=7)
        ttk.Label(param_frame, text="秒").grid(row=0, column=8)

        ttk.Label(param_frame, text="坐标随机偏移").grid(row=1, column=0, padx=7, pady=5)
        ttk.Combobox(
            param_frame,
            textvariable=self.jitter_mode,
            state="readonly",
            values=["0", "1", "2", "3", "自定义"],
            width=7
        ).grid(row=1, column=1)

        ttk.Label(param_frame, text="像素").grid(row=1, column=2)
        ttk.Label(param_frame, text="自定义 ±").grid(row=1, column=3, padx=7)
        ttk.Entry(param_frame, textvariable=self.custom_jitter_var, width=7).grid(
            row=1, column=4
        )
        ttk.Label(param_frame, text="像素").grid(row=1, column=5)

        ttk.Checkbutton(
            param_frame,
            text="粘贴礼包码时短暂激活小程序窗口（后台粘贴失败时开启）",
            variable=self.foreground_paste_var
        ).grid(
            row=2, column=0, columnspan=9,
            padx=7, pady=(2, 6), sticky="w"
        )

        # 控制区
        ctrl = ttk.Frame(content)
        ctrl.pack(fill="x", padx=12, pady=6)

        self.start_btn = ttk.Button(ctrl, text="开始兑换", command=self.start)
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.pause_btn = ttk.Button(
            ctrl, text="暂停", command=self.toggle_pause, state="disabled"
        )
        self.pause_btn.pack(side="left", expand=True, fill="x", padx=5)

        self.stop_btn = ttk.Button(
            ctrl, text="停止", command=self.stop, state="disabled"
        )
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(5, 0))

        status = ttk.Frame(content)
        status.pack(fill="x", padx=12, pady=(0, 9))

        ttk.Label(status, text="状态：").pack(side="left")
        ttk.Label(status, textvariable=self.status_var).pack(side="left")

        ttk.Label(status, textvariable=self.progress_var).pack(side="right")
        ttk.Label(status, text="进度：").pack(side="right", padx=(0, 5))

    def startup_bind(self):
        wins = self.refresh_windows(silent=True)

        if not wins:
            self.window_status_var.set(
                "未找到 WeChatAppEx.exe，请先打开微信小程序后点击“刷新”。"
            )
            return

        if len(wins) == 1:
            display = next(iter(self.window_map.keys()))
            self.window_var.set(display)
            self.bind_selected(silent=True)
        else:
            best = min(
                self.window_map.keys(),
                key=lambda v: self.window_score(self.window_map[v])
            )
            self.window_var.set(best)
            self.window_status_var.set(
                f"检测到 {len(wins)} 个窗口，已预选最接近 431×788 的窗口，请确认后点击“绑定”。"
            )

    def window_score(self, hwnd):
        try:
            r = win32gui.GetWindowRect(hwnd)
            w = r[2] - r[0]
            h = r[3] - r[1]
            return abs(w - TARGET_W) + abs(h - TARGET_H)
        except Exception:
            return 999999

    def refresh_windows(self, auto_bind=False, silent=False):
        wins = list_wechat_windows()
        self.window_map.clear()
        values = []

        for hwnd, title, w, h in wins:
            text = f"{title} | HWND={hwnd} | {w}x{h}"
            values.append(text)
            self.window_map[text] = hwnd

        self.window_combo["values"] = values

        if values:
            best = min(values, key=lambda v: self.window_score(self.window_map[v]))
            self.window_var.set(best)

            if auto_bind:
                self.bind_selected(silent=True)
            elif not silent:
                self.window_status_var.set(
                    f"找到 {len(values)} 个候选窗口，已预选最接近 431×788 的一个。"
                )
        else:
            self.window_var.set("")
            self.window_status_var.set("未找到 WeChatAppEx.exe 小程序窗口。")

        return wins

    def bind_selected(self, silent=False):
        value = self.window_var.get()
        hwnd = self.window_map.get(value)

        if not hwnd or not win32gui.IsWindow(hwnd):
            if not silent:
                messagebox.showwarning("提示", "请选择有效的 WeChatAppEx.exe 窗口。")
            return False

        self.bound_hwnd = hwnd

        if self.auto_resize_var.get():
            force_window_size(hwnd, TARGET_W, TARGET_H)

        self.update_window_status()
        self.save_config()
        return True

    def resize_bound_window(self):
        if not self.bound_hwnd or not win32gui.IsWindow(self.bound_hwnd):
            if not self.bind_selected(silent=True):
                messagebox.showwarning("提示", "请先绑定小程序窗口。")
                return

        ok = force_window_size(self.bound_hwnd, TARGET_W, TARGET_H)
        self.update_window_status()

        if not ok:
            messagebox.showwarning("提示", "窗口尺寸调整失败。")

    def update_window_status(self):
        if not self.bound_hwnd or not win32gui.IsWindow(self.bound_hwnd):
            self.window_status_var.set("未绑定")
            return

        rect = win32gui.GetWindowRect(self.bound_hwnd)
        client = win32gui.GetClientRect(self.bound_hwnd)
        title = win32gui.GetWindowText(self.bound_hwnd) or "(无标题)"

        w = rect[2] - rect[0]
        h = rect[3] - rect[1]

        self.window_status_var.set(
            f"已绑定：{title} | HWND={self.bound_hwnd} | "
            f"窗口={w}×{h} | 客户区={client[2]}×{client[3]}"
        )

    def ensure_window(self):
        if self.bound_hwnd and win32gui.IsWindow(self.bound_hwnd):
            return True

        wins = self.refresh_windows(silent=True)
        if len(wins) == 1:
            return self.bind_selected(silent=True)

        return False

    def capture_coord(self, key):
        if not self.ensure_window():
            messagebox.showwarning("提示", "请先绑定微信小程序窗口。")
            return

        def worker():
            for i in (3, 2, 1):
                self.set_status(f"{i} 秒后记录坐标…")
                time.sleep(1)

            p = win32api.GetCursorPos()
            try:
                cx, cy = win32gui.ScreenToClient(self.bound_hwnd, p)
            except Exception:
                self.set_status("坐标抓取失败")
                return

            self.root.after(0, lambda: self.coord_vars[key][0].set(str(cx)))
            self.root.after(0, lambda: self.coord_vars[key][1].set(str(cy)))
            self.set_status(f"已记录 {key}: X={cx}, Y={cy}")
            self.save_config()

        threading.Thread(target=worker, daemon=True).start()

    def get_jitter(self):
        mode = self.jitter_mode.get()
        if mode == "自定义":
            try:
                return max(0, int(self.custom_jitter_var.get()))
            except Exception:
                return 0
        try:
            return max(0, int(mode))
        except Exception:
            return 0

    def read_point(self, key):
        xv, yv = self.coord_vars[key]
        x = int(xv.get().strip())
        y = int(yv.get().strip())

        j = self.get_jitter()
        if j > 0:
            x += random.randint(-j, j)
            y += random.randint(-j, j)

        return x, y

    def click(self, key):
        x, y = self.read_point(key)
        background_click(self.bound_hwnd, x, y)

    def set_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def set_progress(self, text):
        self.root.after(0, lambda: self.progress_var.set(text))

    def pause_checkpoint(self):
        while not self.stop_event.is_set():
            if self.pause_event.wait(timeout=0.12):
                return True
        return False

    def sleep_interruptible(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self.stop_event.is_set():
                return False
            if not self.pause_checkpoint():
                return False
            time.sleep(min(0.07, max(0, end - time.time())))
        return True

    def paste_code(self, code):
        pyperclip.copy(code)

        if self.foreground_paste_var.get():
            previous = win32gui.GetForegroundWindow()
            force_foreground(self.bound_hwnd)
            time.sleep(0.12)

            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord("A"), 0, 0, 0)
            win32api.keybd_event(ord("A"), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)

            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord("V"), 0, 0, 0)
            win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

            time.sleep(0.08)

            if previous and win32gui.IsWindow(previous) and previous != self.bound_hwnd:
                try:
                    force_foreground(previous)
                except Exception:
                    pass
        else:
            post_ctrl_key(self.bound_hwnd, ord("A"))
            time.sleep(0.06)
            post_ctrl_key(self.bound_hwnd, ord("V"))

    def get_codes(self):
        raw = self.codes_text.get("1.0", "end")
        out = []
        seen = set()
        for line in raw.splitlines():
            code = line.strip()
            if code and code not in seen:
                seen.add(code)
                out.append(code)
        return out

    def validate(self):
        if not self.ensure_window():
            messagebox.showwarning(
                "提示",
                "没有绑定有效的小程序窗口。\n请先选择 WeChatAppEx.exe 窗口并点击“绑定”。"
            )
            return None

        try:
            for key, _ in POINTS:
                self.read_point(key)
        except Exception:
            messagebox.showwarning("提示", "请检查 6 个坐标，X/Y 必须填写整数。")
            return None

        codes = self.get_codes()
        if not codes:
            messagebox.showwarning("提示", "请先粘贴礼包码，每行一个。")
            return None

        try:
            delay = float(self.delay_var.get())
            popup_wait = float(self.popup_wait_var.get())
            reward_wait = float(self.reward_wait_var.get())
            if min(delay, popup_wait, reward_wait) < 0.15:
                raise ValueError
        except Exception:
            messagebox.showwarning("提示", "等待时间必须是 ≥ 0.15 的数字。")
            return None

        return codes, delay, popup_wait, reward_wait

    def start(self):
        if self.running:
            return

        val = self.validate()
        if not val:
            return

        codes, delay, popup_wait, reward_wait = val
        self.save_config()

        self.stop_event.clear()
        self.pause_event.set()
        self.running = True

        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal", text="暂停")
        self.stop_btn.config(state="normal")

        threading.Thread(
            target=self.worker,
            args=(codes, delay, popup_wait, reward_wait),
            daemon=True
        ).start()

    def worker(self, codes, delay, popup_wait, reward_wait):
        try:
            total = len(codes)

            for idx, code in enumerate(codes, 1):
                if self.stop_event.is_set():
                    break
                if not self.pause_checkpoint():
                    break

                if not self.ensure_window():
                    self.finish("绑定窗口已失效")
                    return

                self.set_progress(f"{idx} / {total}")
                self.set_status(f"正在兑换：{code}")

                self.click("gift_button")
                if not self.sleep_interruptible(delay):
                    break

                self.click("game_input")
                if not self.sleep_interruptible(popup_wait):
                    break

                self.click("popup_input")
                if not self.sleep_interruptible(0.18):
                    break

                self.paste_code(code)
                if not self.sleep_interruptible(0.25):
                    break

                self.click("done_button")
                if not self.sleep_interruptible(delay):
                    break

                self.click("confirm_button")
                if not self.sleep_interruptible(reward_wait):
                    break

                self.click("reward_close")
                if not self.sleep_interruptible(delay):
                    break

            if self.stop_event.is_set():
                self.finish("已停止")
            else:
                self.finish(f"已完成，本次处理 {len(codes)} 个礼包码")

        except Exception as e:
            self.finish(f"执行出错：{e}")

    def toggle_pause(self):
        if not self.running:
            return

        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.config(text="继续")
            self.status_var.set("已暂停")
        else:
            self.pause_event.set()
            self.pause_btn.config(text="暂停")
            self.status_var.set("继续执行")

    def stop(self):
        self.stop_event.set()
        self.pause_event.set()
        self.status_var.set("正在停止…")

    def finish(self, msg):
        self.running = False
        self.pause_event.set()

        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.pause_btn.config(state="disabled", text="暂停"))
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.set_status(msg)

    def save_config(self):
        data = {
            "coords": {
                key: {
                    "x": self.coord_vars[key][0].get(),
                    "y": self.coord_vars[key][1].get()
                }
                for key, _ in POINTS
            },
            "delay": self.delay_var.get(),
            "popup_wait": self.popup_wait_var.get(),
            "reward_wait": self.reward_wait_var.get(),
            "jitter_mode": self.jitter_mode.get(),
            "custom_jitter": self.custom_jitter_var.get(),
            "foreground_paste": self.foreground_paste_var.get(),
            "auto_resize": self.auto_resize_var.get(),
        }

        try:
            CONFIG_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def load_config(self):
        # EXE 启动时默认读取“EXE同目录”的配置文件
        # 若配置不存在，则创建一份默认配置，方便后续直接修改/分发
        if not CONFIG_FILE.exists():
            default_data = {
                "coords": {
                    "gift_button": {"x": "73", "y": "620"},
                    "game_input": {"x": "205", "y": "366"},
                    "popup_input": {"x": "185", "y": "387"},
                    "done_button": {"x": "142", "y": "451"},
                    "confirm_button": {"x": "213", "y": "505"},
                    "reward_close": {"x": "194", "y": "707"}
                },
                "delay": "0.8",
                "popup_wait": "0.8",
                "reward_wait": "2.0",
                "jitter_mode": "1",
                "custom_jitter": "2",
                "foreground_paste": True,
                "auto_resize": True
            }
            try:
                CONFIG_FILE.write_text(
                    json.dumps(default_data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except Exception:
                pass

        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

            for key, _ in POINTS:
                d = data.get("coords", {}).get(key, {})
                self.coord_vars[key][0].set(str(d.get("x", "")))
                self.coord_vars[key][1].set(str(d.get("y", "")))

            self.delay_var.set(str(data.get("delay", "0.8")))
            self.popup_wait_var.set(str(data.get("popup_wait", "0.8")))
            self.reward_wait_var.set(str(data.get("reward_wait", "2.0")))
            self.jitter_mode.set(str(data.get("jitter_mode", "3")))
            self.custom_jitter_var.set(str(data.get("custom_jitter", "5")))
            self.foreground_paste_var.set(bool(data.get("foreground_paste", False)))
            self.auto_resize_var.set(bool(data.get("auto_resize", True)))
        except Exception:
            pass

    def on_close(self):
        self.save_config()
        self.stop_event.set()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
