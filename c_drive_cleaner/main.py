import sys
import os
import ctypes


def _enable_dpi_awareness():
    """适配高 DPI 屏幕，避免界面模糊。"""
    if os.name != "nt":
        return
    for setter in ("SetProcessDpiAwarenessContext", "SetProcessDpiAwareness",
                   "SetProcessDPIAware"):
        try:
            func = getattr(ctypes.windll.user32, setter, None)
            if func:
                if setter == "SetProcessDpiAwarenessContext":
                    func(-4)
                elif setter == "SetProcessDpiAwareness":
                    func(2)
                else:
                    func()
                return
        except Exception:
            continue


def _ensure_path():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)


def main():
    _enable_dpi_awareness()
    _ensure_path()

    import tkinter as tk
    from main_window import MainWindow

    root = tk.Tk()
    try:
        MainWindow(root)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("启动失败", "程序启动出错：\n{}".format(e))
        except Exception:
            pass
        return 1

    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
