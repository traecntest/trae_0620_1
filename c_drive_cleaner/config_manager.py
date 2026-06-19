import json
import os
import hashlib
import tempfile
from datetime import datetime
from pathlib import Path


class ConfigManager:
    """配置层：负责用户设置与清理记录的 JSON 持久化。"""

    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path else self._default_config_path()
        self.config = self._load()

    @staticmethod
    def _default_config_path():
        app_dir = Path.home() / ".c_drive_cleaner"
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            app_dir = Path(tempfile.gettempdir()) / ".c_drive_cleaner"
            app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / "settings.json"

    @staticmethod
    def _default_config():
        return {
            "use_password": False,
            "password_hash": "",
            "autostart": False,
            "shutdown_mode": "countdown",
            "shutdown_time": "22:00",
            "shutdown_minutes": 60,
            "daily_enabled": False,
            "last_cleanup": None,
            "total_freed": 0,
            "cleanup_history": []
        }

    def _load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = self._default_config()
                merged.update(data)
                return merged
            except (json.JSONDecodeError, OSError):
                pass
        return self._default_config()

    def save(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print("保存配置失败:", e)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def has_password(self):
        return bool(self.config.get("use_password") and self.config.get("password_hash"))

    @staticmethod
    def _hash(password):
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def set_password(self, password):
        self.config["password_hash"] = self._hash(password)
        self.config["use_password"] = True
        self.save()

    def clear_password(self):
        self.config["password_hash"] = ""
        self.config["use_password"] = False
        self.save()

    def verify_password(self, password):
        if not self.has_password():
            return True
        return self._hash(password) == self.config.get("password_hash")

    def record_cleanup(self, freed_bytes):
        self.config["last_cleanup"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.config["total_freed"] = self.config.get("total_freed", 0) + freed_bytes
        history = self.config.get("cleanup_history", [])
        history.append({
            "time": self.config["last_cleanup"],
            "freed": freed_bytes
        })
        self.config["cleanup_history"] = history[-20:]
        self.save()

    def last_cleanup_text(self):
        last = self.config.get("last_cleanup")
        total = self.config.get("total_freed", 0)
        if not last:
            return "尚未清理过"
        return "上次清理：{}，累计释放 {}".format(last, ConfigManager.human_size(total))

    @staticmethod
    def human_size(num):
        num = float(num)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if abs(num) < 1024.0:
                return "{:.2f} {}".format(num, unit)
            num /= 1024.0
        return "{:.2f} PB".format(num)
