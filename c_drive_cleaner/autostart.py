import os
import subprocess
import sys
from pathlib import Path


class AutostartManager:
    """开机自启管理：在 Windows 启动文件夹创建快捷方式实现开机自启。"""

    SHORTCUT_NAME = "C盘清理小工具.lnk"

    def __init__(self):
        self.startup_dir = self._get_startup_dir()

    @staticmethod
    def _get_startup_dir():
        appdata = os.environ.get("APPDATA", "")
        path = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        return path

    def get_shortcut_path(self):
        return os.path.join(self.startup_dir, self.SHORTCUT_NAME)

    def is_enabled(self):
        return os.path.exists(self.get_shortcut_path())

    def enable(self):
        """创建启动快捷方式，目标使用 pythonw 静默运行本脚本。"""
        try:
            script = os.path.abspath(sys.argv[0])
            startup_path = self.get_shortcut_path()
            python_exe = self._pythonw_path()
            ps = (
                "$ws = New-Object -ComObject WScript.Shell; "
                "$sc = $ws.CreateShortcut('{lnk}'); "
                "$sc.TargetPath = '{py}'; "
                "$sc.Arguments = '\"{script}\"'; "
                "$sc.WorkingDirectory = '{cwd}'; "
                "$sc.WindowStyle = 7; "
                "$sc.Description = 'C盘清理小工具'; "
                "$sc.Save()"
            ).format(lnk=startup_path, py=python_exe, script=script,
                     cwd=os.path.dirname(script))
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                shell=True,
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
            )
            return True, "已设置开机自启"
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("gbk", errors="ignore") if e.stderr else str(e)
            return False, "设置自启失败，请尝试以管理员身份运行：" + err.strip()
        except Exception as e:
            return False, "设置自启失败：" + str(e)

    def disable(self):
        try:
            path = self.get_shortcut_path()
            if os.path.exists(path):
                os.remove(path)
            return True, "已取消开机自启"
        except OSError as e:
            return False, "取消自启失败：" + str(e)

    @staticmethod
    def _pythonw_path():
        exe = sys.executable
        directory = os.path.dirname(exe)
        pythonw = os.path.join(directory, "pythonw.exe")
        if os.path.exists(pythonw):
            return pythonw
        return exe
