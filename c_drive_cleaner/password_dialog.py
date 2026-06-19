import tkinter as tk
from tkinter import ttk


class PasswordDialog(tk.Toplevel):
    """UI 层：可选密码弹窗。支持校验模式与设置模式。"""

    def __init__(self, parent, title="输入密码", confirm=False, on_success=None):
        super().__init__(parent)
        self.title(title)
        self.confirm = confirm
        self.on_success = on_success
        self.result = None
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)

        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text=title + "：").pack(anchor="w", pady=(0, 8))

        self.var_pwd = tk.StringVar()
        self.entry_pwd = ttk.Entry(container, textvariable=self.var_pwd, show="*")
        self.entry_pwd.pack(fill="x", pady=(0, 8))
        self.entry_pwd.focus_set()

        self.var_pwd2 = tk.StringVar()
        if confirm:
            ttk.Label(container, text="再次输入：").pack(anchor="w", pady=(0, 8))
            self.entry_pwd2 = ttk.Entry(container, textvariable=self.var_pwd2, show="*")
            self.entry_pwd2.pack(fill="x", pady=(0, 8))

        self.lbl_hint = ttk.Label(container, text="", foreground="red")
        self.lbl_hint.pack(anchor="w", pady=(0, 8))

        btns = ttk.Frame(container)
        btns.pack(fill="x")
        ttk.Button(btns, text="确定", command=self._on_ok).pack(side="right", padx=(4, 0))
        ttk.Button(btns, text="取消", command=self._on_cancel).pack(side="right")

        self.entry_pwd.bind("<Return>", lambda e: self._on_ok())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_ok(self):
        pwd = self.var_pwd.get()
        if not pwd:
            self.lbl_hint.config(text="密码不能为空")
            return
        if self.confirm:
            if pwd != self.var_pwd2.get():
                self.lbl_hint.config(text="两次输入不一致")
                return
        self.result = pwd
        if self.on_success:
            self.on_success(pwd)
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()
