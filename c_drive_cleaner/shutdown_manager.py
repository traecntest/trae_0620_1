import os
import subprocess
from datetime import datetime


class ShutdownManager:
    """业务层：定时关机。支持倒计时、指定时间点、每日循环三种模式，并可随时取消。"""

    DAILY_TASK_NAME = "CDriveCleanerDailyShutdown"

    def schedule_countdown(self, minutes):
        """倒计时关机：minutes 分钟后关机。"""
        seconds = max(int(minutes) * 60, 0)
        return self._run_shutdown(["/s", "/t", str(seconds)])

    def schedule_at_time(self, time_str):
        """指定时间点关机，例如 '22:30'。"""
        seconds = self._seconds_until(time_str)
        if seconds is None:
            return False, "时间格式不正确，请使用 HH:MM"
        if seconds <= 0:
            seconds += 24 * 3600
        return self._run_shutdown(["/s", "/t", str(seconds)])

    def schedule_daily(self, time_str):
        """每日循环关机，通过 Windows 计划任务实现。"""
        if not self._valid_time(time_str):
            return False, "时间格式不正确，请使用 HH:MM"
        self.cancel_daily()
        cmd = [
            "schtasks", "/Create", "/TN", self.DAILY_TASK_NAME,
            "/TR", "shutdown /s /f", "/SC", "DAILY", "/ST", time_str, "/F"
        ]
        return self._run_raw(cmd)

    def cancel(self):
        """取消所有由本工具设置的关机任务。"""
        self._run_raw(["shutdown", "/a"])
        self.cancel_daily()

    def cancel_daily(self):
        self._run_raw(["schtasks", "/Delete", "/TN", self.DAILY_TASK_NAME, "/F"])

    @staticmethod
    def _valid_time(time_str):
        try:
            datetime.strptime(time_str.strip(), "%H:%M")
            return True
        except ValueError:
            return False

    @classmethod
    def _seconds_until(cls, time_str):
        if not cls._valid_time(time_str):
            return None
        now = datetime.now()
        target = datetime.strptime(time_str.strip(), "%H:%M").replace(
            year=now.year, month=now.month, day=now.day)
        return int((target - now).total_seconds())

    @staticmethod
    def _run_raw(cmd):
        try:
            if os.name == "nt":
                creationflags = 0x08000000
            else:
                creationflags = 0
            subprocess.run(
                cmd,
                shell=True,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
            )
            return True, "命令已执行"
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("gbk", errors="ignore") if e.stderr else str(e)
            return False, "执行失败：" + err.strip()
        except Exception as e:
            return False, "执行失败：" + str(e)

    @classmethod
    def _run_shutdown(cls, extra_args):
        return cls._run_raw(["shutdown"] + extra_args)

    def is_daily_active(self):
        try:
            result = subprocess.run(
                ["schtasks", "/Query", "/TN", self.DAILY_TASK_NAME],
                shell=True,
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
        except Exception:
            return False
