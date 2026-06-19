import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from config_manager import ConfigManager
from cleaner import Cleaner
from shutdown_manager import ShutdownManager
from autostart import AutostartManager
from password_dialog import PasswordDialog


class MainWindow:
    """UI 层：极简主界面，串联配置层与业务层。"""

    MODE_COUNTDOWN = "countdown"
    MODE_TIMEPOINT = "timepoint"
    MODE_DAILY = "daily"

    def __init__(self, root):
        self.root = root
        self.config = ConfigManager()
        self.cleaner = Cleaner()
        self.shutdown = ShutdownManager()
        self.autostart = AutostartManager()
        self.busy = False
        self.log_queue = queue.Queue()
        self._unlocked = not self.config.has_password()

        self._build_ui()
        self._load_settings()
        self.root.after(150, self._poll_log)
        self.root.after(300, self._maybe_lock)
        self.root.after(500, self._arm_daily_if_needed)

    # ---------------- UI 构建 ----------------
    def _build_ui(self):
        self.root.title("C 盘清理小工具")
        self.root.geometry("460x560")
        self.root.minsize(420, 500)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        self._build_menu()

        pad = {"padx": 12, "pady": 6}
        title = ttk.Label(self.root, text="C 盘清理 · 定时关机",
                          font=("Microsoft YaHei UI", 14, "bold"))
        title.pack(pady=(12, 4))

        self.status_var = tk.StringVar(value=self.config.last_cleanup_text())
        self.lbl_status = ttk.Label(self.root, textvariable=self.status_var,
                                    foreground="#666666")
        self.lbl_status.pack(pady=(0, 4))

        log_frame = ttk.LabelFrame(self.root, text="运行反馈", padding=8)
        log_frame.pack(fill="both", expand=True, **pad)

        self.txt_log = tk.Text(log_frame, height=12, wrap="word",
                              font=("Consolas", 9), state="disabled")
        self.txt_log.tag_config("ok", foreground="#1a7f37")
        self.txt_log.tag_config("err", foreground="#d1242f")
        self.txt_log.tag_config("warn", foreground="#bf8700")
        self.txt_log.tag_config("info", foreground="#333333")
        scr = ttk.Scrollbar(log_frame, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scr.set)
        self.txt_log.pack(side="left", fill="both", expand=True)
        scr.pack(side="right", fill="y")

        clean_frame = ttk.Frame(self.root, padding=(12, 4))
        clean_frame.pack(fill="x")
        self.btn_clean = ttk.Button(clean_frame, text="一键清理 C 盘",
                                    command=self._on_clean)
        self.btn_clean.pack(fill="x", ipady=4)

        shut_frame = ttk.LabelFrame(self.root, text="定时关机", padding=8)
        shut_frame.pack(fill="x", **pad)

        mode_frame = ttk.Frame(shut_frame)
        mode_frame.pack(fill="x")
        self.var_mode = tk.StringVar(value=self.MODE_COUNTDOWN)
        ttk.Radiobutton(mode_frame, text="倒计时(分钟)", value=self.MODE_COUNTDOWN,
                        variable=self.var_mode, command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(mode_frame, text="指定时间", value=self.MODE_TIMEPOINT,
                        variable=self.var_mode, command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(mode_frame, text="每日循环", value=self.MODE_DAILY,
                        variable=self.var_mode, command=self._on_mode_change).pack(side="left")

        in_frame = ttk.Frame(shut_frame)
        in_frame.pack(fill="x", pady=6)
        self.var_shutdown = tk.StringVar()
        self.ent_shutdown = ttk.Entry(in_frame, textvariable=self.var_shutdown)
        self.ent_shutdown.pack(side="left", fill="x", expand=True)
        ttk.Button(in_frame, text="设置关机", command=self._on_set_shutdown).pack(side="left", padx=(6, 0))
        ttk.Button(in_frame, text="取消关机", command=self._on_cancel_shutdown).pack(side="left", padx=(6, 0))

        self._on_mode_change()

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        tools = tk.Menu(menubar, tearoff=False)
        tools.add_command(label="设置 / 修改密码", command=self._set_password)
        tools.add_command(label="清除密码", command=self._clear_password)
        tools.add_separator()
        self.autostart_var = tk.BooleanVar(value=self.autostart.is_enabled())
        tools.add_checkbutton(label="开机自启动", variable=self.autostart_var,
                              command=self._toggle_autostart)
        menubar.add_cascade(label="工具", menu=tools)

        helpm = tk.Menu(menubar, tearoff=False)
        helpm.add_command(label="关于", command=self._about)
        helpm.add_command(label="退出", command=self._quit)
        menubar.add_cascade(label="帮助", menu=helpm)
        self.root.config(menu=menubar)

    # ---------------- 设置加载/保存 ----------------
    def _load_settings(self):
        self.var_mode.set(self.config.get("shutdown_mode", self.MODE_COUNTDOWN))
        if self.var_mode.get() == self.MODE_COUNTDOWN:
            self.var_shutdown.set(str(self.config.get("shutdown_minutes", 60)))
        else:
            self.var_shutdown.set(self.config.get("shutdown_time", "22:00"))
        self._on_mode_change()

    def _save_settings(self):
        self.config.set("shutdown_mode", self.var_mode.get())
        self.config.set("shutdown_minutes", self.var_shutdown.get())

    # ---------------- 密码锁 ----------------
    def _maybe_lock(self):
        if self._unlocked:
            return

        def success(pwd):
            self._unlocked = True
            self.log("已解锁", "ok")

        def on_closed():
            if not self._unlocked:
                self.log("未解锁，程序将退出", "warn")
                self.root.after(300, self._quit)

        dlg = PasswordDialog(self.root, title="请输入密码解锁", on_success=success)
        self.root.wait_window(dlg)
        on_closed()

    def _set_password(self):
        def success(pwd):
            self.config.set_password(pwd)
            self._unlocked = True
            self.log("密码已设置，下次启动需输入密码", "ok")
        PasswordDialog(self.root, title="设置 / 修改密码", confirm=True, on_success=success)

    def _clear_password(self):
        if not self.config.has_password():
            self.log("当前未设置密码", "info")
            return

        def success(pwd):
            if self.config.verify_password(pwd):
                self.config.clear_password()
                self.log("密码已清除", "ok")
            else:
                messagebox.showerror("错误", "密码不正确")
        PasswordDialog(self.root, title="请输入当前密码", on_success=success)

    # ---------------- 清理 ----------------
    def _on_clean(self):
        if self.busy:
            return
        if not self._require_unlock():
            return
        self.busy = True
        self.btn_clean.config(state="disabled", text="清理中...")
        threading.Thread(target=self._clean_worker, daemon=True).start()

    def _clean_worker(self):
        try:
            self._emit("正在扫描可清理项目...", "info")
            before = self.cleaner.scan()
            self._emit("扫描完成，预计可释放：{}".format(ConfigManager.human_size(before)), "ok")
            if before <= 0:
                self._emit("C 盘已经很干净，无需清理", "info")
                return

            freed, count, errors = self.cleaner.clean(progress_callback=self._progress_cb)
            self._emit("清理完成：释放 {}，处理 {} 项".format(
                ConfigManager.human_size(freed), count), "ok")
            if errors:
                self._emit("部分项目已跳过（多为文件被占用或需管理员权限）：", "warn")
                for e in errors[:20]:
                    self._emit("  · " + e, "warn")
            self.config.record_cleanup(freed)
            self.root.after(0, self._refresh_status)
        except Exception as e:
            self._emit("清理出错：" + str(e), "err")
        finally:
            self.root.after(0, self._clean_done)

    def _progress_cb(self, name, delta):
        if delta > 0:
            self._emit("  已清理 {}：{}".format(name, ConfigManager.human_size(delta)), "info")

    def _clean_done(self):
        self.busy = False
        self.btn_clean.config(state="normal", text="一键清理 C 盘")

    # ---------------- 关机 ----------------
    def _on_mode_change(self):
        mode = self.var_mode.get()
        if mode == self.MODE_COUNTDOWN:
            self.ent_shutdown.delete(0, "end")
            self.ent_shutdown.insert(0, str(self.config.get("shutdown_minutes", 60)))
        else:
            self.ent_shutdown.delete(0, "end")
            self.ent_shutdown.insert(0, self.config.get("shutdown_time", "22:00"))

    def _on_set_shutdown(self):
        if not self._require_unlock():
            return
        mode = self.var_mode.get()
        val = self.var_shutdown.get().strip()
        self._save_settings()

        if mode == self.MODE_COUNTDOWN:
            if not val.isdigit() or int(val) <= 0:
                self.log("请输入有效的正整数分钟数", "err")
                return
            ok, msg = self.shutdown.schedule_countdown(int(val))
            tip = "将在 {} 分钟后关机".format(val)
        elif mode == self.MODE_TIMEPOINT:
            ok, msg = self.shutdown.schedule_at_time(val)
            tip = "将在 {} 关机".format(val)
        else:
            ok, msg = self.shutdown.schedule_daily(val)
            tip = "每日 {} 自动关机".format(val)
            self.config.set("daily_enabled", True)
            self.config.set("shutdown_time", val)

        if ok:
            self.log("{}。如需取消请点击“取消关机”。".format(tip), "ok")
        else:
            self.log(msg, "err")

    def _on_cancel_shutdown(self):
        if not self._require_unlock():
            return
        ok, msg = self.shutdown.cancel()
        self.config.set("daily_enabled", False)
        self.log("已取消关机任务" if ok else msg, "ok" if ok else "err")

    def _arm_daily_if_needed(self):
        if self.config.get("daily_enabled") and not self.shutdown.is_daily_active():
            t = self.config.get("shutdown_time", "22:00")
            ok, msg = self.shutdown.schedule_daily(t)
            if ok:
                self.log("已自动恢复每日 {} 关机任务".format(t), "info")

    # ---------------- 自启 ----------------
    def _toggle_autostart(self):
        if self.autostart_var.get():
            ok, msg = self.autostart.enable()
        else:
            ok, msg = self.autostart.disable()
        self.config.set("autostart", self.autostart_var.get())
        self.log(msg, "ok" if ok else "err")
        if not ok:
            self.autostart_var.set(self.autostart.is_enabled())

    # ---------------- 杂项 ----------------
    def _require_unlock(self):
        if self._unlocked:
            return True
        self._maybe_lock()
        return self._unlocked

    def _refresh_status(self):
        self.status_var.set(self.config.last_cleanup_text())

    def _about(self):
        messagebox.showinfo("关于", "C 盘清理小工具\n\n一键清理系统临时文件、浏览器缓存、回收站，"
                                       "并支持定时关机，缓解 C 盘空间不足与电脑过度使用。\n\n"
                                       "仅清理安全目标，不会删除系统关键文件。")

    def _quit(self):
        try:
            self._save_settings()
        except Exception:
            pass
        self.root.destroy()

    # ---------------- 日志 ----------------
    def log(self, msg, tag="info"):
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", msg + "\n", tag)
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def _emit(self, msg, tag="info"):
        self.log_queue.put((msg, tag))

    def _poll_log(self):
        try:
            while True:
                msg, tag = self.log_queue.get_nowait()
                self.log(msg, tag)
        except queue.Empty:
            pass
        finally:
            self.root.after(150, self._poll_log)
