import os
import subprocess
from datetime import datetime


class ShutdownManager:
    """业务层：定时关机。支持倒计时、指定时间点、每日循环三种模式，并可随时取消。"""

    DAILY_TASK_NAME = "CDriveCleanerDailyShutdown"

    def schedule_countdown(self, minutes):
        """倒计时关机：minutes 分钟后关机。

        返回 (ok, msg, level)。
        """
        seconds = max(int(minutes) * 60, 0)
        ok, msg = self._run_shutdown(["/s", "/t", str(seconds)])
        return ok, msg, "ok" if ok else "err"

    def schedule_at_time(self, time_str):
        """指定时间点关机，例如 '22:30'。若今日已过则顺延至次日。

        返回 (ok, msg, level)，level 取值 ok / warn / err。
        """
        seconds = self._seconds_until(time_str)
        if seconds is None:
            return False, "时间格式不正确，请使用 HH:MM", "err"
        is_past = seconds <= 0
        if is_past:
            seconds += 24 * 3600
        ok, msg = self._run_shutdown(["/s", "/t", str(seconds)])
        if ok and is_past:
            msg = "注意：指定时间今日已过，将于明日 {} 关机。" + time_str
            return True, msg, "warn"
        return ok, msg, "ok" if ok else "err"

    def schedule_daily(self, time_str):
        """每日循环关机，通过 Windows 计划任务实现。

        返回 (ok, msg, level)。
        """
        if not self._valid_time(time_str):
            return False, "时间格式不正确，请使用 HH:MM", "err"
        self.cancel_daily()
        cmd = [
            "schtasks", "/Create", "/TN", self.DAILY_TASK_NAME,
            "/TR", "shutdown /s /f", "/SC", "DAILY", "/ST", time_str, "/F"
        ]
        ok, msg = self._run_raw(cmd)
        return ok, msg, "ok" if ok else "err"

    def cancel(self):
        """取消所有由本工具设置的关机任务。

        返回 (ok, msg)。
        """
        ok1, msg1 = self._run_raw(["shutdown", "/a"])
        ok2, msg2 = self.cancel_daily()
        if ok1 or ok2:
            return True, "已取消所有关机任务"
        return False, "取消失败：" + (msg1 if msg1 else msg2)

    def cancel_daily(self):
        """取消每日循环关机计划任务。

        返回 (ok, msg)。
        """
        ok, msg = self._run_raw(["schtasks", "/Delete", "/TN", self.DAILY_TASK_NAME, "/F"])
        if not ok and "找不到" in msg:
            return True, "当前没有每日关机任务"
        return ok, msg

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
