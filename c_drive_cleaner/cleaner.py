import os
import glob
import shutil
import ctypes
import tempfile
import threading


class Cleaner:
    """业务层：安全扫描并清理 C 盘冗余文件。

    清理范围：用户/系统临时文件、预读取文件、浏览器缓存、应用日志、回收站。
    安全策略：仅清理预定义目标目录内部内容，保留目录本身；通过允许根校验防止误删。
    交互支持：支持暂停/取消，按类别返回统计结果。
    """

    # 绝不允许删除的系统关键位置（路径片段匹配）
    PROTECTED_FRAGMENTS = [
        "\\system32\\", "\\windows\\system32", "\\program files",
        "\\program files (x86)", "\\programdata", "\\boot\\",
        "\\recovery", "\\system volume information", "\\windows.old",
        "\\$recycle.bin", "\\perflogs",
    ]

    # 仅允许清理以下根目录之下的内容，防止环境变量被篡改导致误删
    ALLOWED_ROOTS = []

    SHERB_NOCONFIRMATION = 0x00000001
    SHERB_NOPROGRESSUI = 0x00000002
    SHERB_NOSOUND = 0x00000004

    def __init__(self):
        self.before_size = 0
        self.after_size = 0
        self.deleted_count = 0
        self.errors = []
        self.category_results = []

        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def is_paused(self):
        return not self._pause_event.is_set()

    def cancel(self):
        self._cancel_event.set()
        self._pause_event.set()

    def is_cancelled(self):
        return self._cancel_event.is_set()

    def reset(self):
        self._cancel_event.clear()
        self._pause_event.set()
        self.before_size = 0
        self.after_size = 0
        self.deleted_count = 0
        self.errors = []
        self.category_results = []

    def _check_cancel_pause(self):
        if self._cancel_event.is_set():
            return False
        self._pause_event.wait()
        if self._cancel_event.is_set():
            return False
        return True

    @classmethod
    def _allowed_roots(cls):
        if cls.ALLOWED_ROOTS:
            return cls.ALLOWED_ROOTS
        env = os.environ
        roots = []
        for key in ("TEMP", "TMP", "LOCALAPPDATA", "APPDATA", "ProgramData"):
            val = env.get(key)
            if val:
                roots.append(os.path.normpath(val).lower())
        roots.append(r"c:\windows\temp")
        roots.append(r"c:\windows\prefetch")
        roots.append(r"c:\windows\logs")
        cls.ALLOWED_ROOTS = roots
        return roots

    def _is_protected(self, path):
        lower = os.path.normpath(path).lower()
        for frag in self.PROTECTED_FRAGMENTS:
            if frag in lower:
                return True
        return False

    def _is_within_allowed(self, path):
        if not path:
            return False
        norm = os.path.normpath(path).lower()
        for root in self._allowed_roots():
            try:
                common = os.path.commonpath([norm, root])
            except ValueError:
                continue
            if common == root or norm == root:
                return True
        return False

    def _safe_to_clean(self, path):
        if not path or not os.path.isabs(path):
            return False
        if self._is_protected(path):
            return False
        if not self._is_within_allowed(path):
            return False
        return True

    @staticmethod
    def _expand(pattern):
        try:
            return glob.glob(pattern)
        except (OSError, TypeError):
            return []

    def get_targets(self):
        env = os.environ
        local = env.get("LOCALAPPDATA", "")
        roaming = env.get("APPDATA", "")
        user_temp = env.get("TEMP") or env.get("TMP") or tempfile.gettempdir()

        targets = []

        targets.append(("用户临时文件", "dir", user_temp))
        targets.append(("系统临时文件", "dir", r"C:\Windows\Temp"))
        targets.append(("系统预读取", "dir", r"C:\Windows\Prefetch"))
        targets.append(("系统日志", "dir", r"C:\Windows\Logs"))

        # Chrome 缓存（含多用户配置）
        targets.append(("Chrome 浏览器缓存", "dir",
                        os.path.join(local, r"Google\Chrome\User Data")))
        # Edge 缓存
        targets.append(("Edge 浏览器缓存", "dir",
                        os.path.join(local, r"Microsoft\Edge\User Data")))
        # Firefox 缓存（profile 目录用通配）
        for prof in self._expand(os.path.join(roaming, r"Mozilla\Firefox\Profiles\*")):
            targets.append(("Firefox 缓存", "dir", os.path.join(prof, "cache2")))

        # 回收站
        targets.append(("回收站", "recycle", None))
        return targets

    @staticmethod
    def _get_dir_size(path):
        total = 0
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        total += Cleaner._get_dir_size(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            pass
        return total

    @staticmethod
    def _browser_cache_dirs(root):
        """在浏览器 User Data 目录下收集各 profile 的 Cache/Code Cache/GPUCache。"""
        dirs = []
        if not root or not os.path.isdir(root):
            return dirs
        try:
            for entry in os.scandir(root):
                if not entry.is_dir(follow_symlinks=False):
                    continue
                for sub in ("Cache", "Code Cache", "GPUCache"):
                    dirs.append(os.path.join(entry.path, sub))
        except (OSError, PermissionError):
            pass
        return dirs

    def _target_size(self, kind, path):
        if kind == "recycle":
            return self._recycle_bin_size()[0]
        if not path or not os.path.isdir(path):
            return 0
        # 浏览器 User Data 目录按子缓存统计
        if self._is_browser_user_data(path):
            return sum(self._get_dir_size(d) for d in self._browser_cache_dirs(path))
        return self._get_dir_size(path)

    @staticmethod
    def _is_browser_user_data(path):
        lower = os.path.normpath(path).lower()
        return ("user data" in lower) or lower.endswith("cache2")

    def scan(self):
        self.before_size = 0
        self.category_results = []
        for name, kind, path in self.get_targets():
            size = self._target_size(kind, path)
            self.before_size += size
            self.category_results.append({
                "name": name,
                "kind": kind,
                "path": path,
                "before_size": size,
                "freed": 0,
                "count": 0,
                "status": "pending"
            })
        return self.before_size

    def get_category_summary(self):
        grouped = {}
        for cat in self.category_results:
            name = cat["name"]
            if name not in grouped:
                grouped[name] = {"before": 0, "freed": 0, "count": 0, "status": "pending"}
            grouped[name]["before"] += cat["before_size"]
            grouped[name]["freed"] += cat["freed"]
            grouped[name]["count"] += cat["count"]
            grouped[name]["status"] = cat["status"]
        return grouped

    def clean(self, progress_callback=None):
        self.errors = []
        self.deleted_count = 0
        freed = 0
        if not self.category_results:
            self.scan()

        for cat in self.category_results:
            if not self._check_cancel_pause():
                cat["status"] = "cancelled"
                break

            name = cat["name"]
            kind = cat["kind"]
            path = cat["path"]

            try:
                if kind == "recycle":
                    before = self._recycle_bin_size()[0]
                    ok = self._empty_recycle_bin()
                    after = self._recycle_bin_size()[0]
                    delta = max(before - after, 0)
                    freed += delta
                    self.deleted_count += 1
                    cat["freed"] += delta
                    cat["count"] += 1
                    cat["status"] = "done"
                    if progress_callback:
                        progress_callback(name, delta, 1)
                    continue

                if not self._safe_to_clean(path):
                    self.errors.append("{}：路径不在允许范围，已跳过".format(name))
                    cat["status"] = "skipped"
                    continue

                # 浏览器目录：仅清理 Cache 子目录
                if self._is_browser_user_data(path) and path.lower().endswith("user data"):
                    total_freed = 0
                    total_count = 0
                    for cache_dir in self._browser_cache_dirs(path):
                        if not self._check_cancel_pause():
                            break
                        if self._safe_to_clean(cache_dir):
                            f, c = self._clear_dir(cache_dir, progress_callback, name)
                            total_freed += f
                            total_count += c
                    freed += total_freed
                    cat["freed"] += total_freed
                    cat["count"] += total_count
                    cat["status"] = "done" if not self._cancel_event.is_set() else "cancelled"
                    continue

                f, c = self._clear_dir(path, progress_callback, name)
                freed += f
                cat["freed"] += f
                cat["count"] += c
                cat["status"] = "done"

            except Exception as e:
                self.errors.append("{}：{}".format(name, str(e)))
                cat["status"] = "error"

        if self._cancel_event.is_set():
            for cat in self.category_results:
                if cat["status"] == "pending":
                    cat["status"] = "cancelled"

        self.after_size = self.before_size - freed
        if self.after_size < 0:
            self.after_size = 0
        return freed, self.deleted_count, self.errors

    def _clear_dir(self, path, progress_callback=None, name=""):
        freed = 0
        count = 0
        if not path or not os.path.isdir(path):
            return freed, count
        try:
            entries = list(os.scandir(path))
        except (OSError, PermissionError):
            return freed, count
        check_every = 20
        i = 0
        for entry in entries:
            i += 1
            if i % check_every == 0:
                if not self._check_cancel_pause():
                    return freed, count
            try:
                if entry.is_dir(follow_symlinks=False):
                    size = self._get_dir_size(entry.path)
                    shutil.rmtree(entry.path, ignore_errors=True)
                    if not os.path.exists(entry.path):
                        freed += size
                        count += 1
                elif entry.is_file(follow_symlinks=False):
                    size = entry.stat(follow_symlinks=False).st_size
                    try:
                        os.remove(entry.path)
                        freed += size
                        count += 1
                    except (OSError, PermissionError):
                        pass
            except (OSError, PermissionError):
                continue
        if progress_callback and freed > 0:
            progress_callback(name, freed, count)
        return freed, count

    @staticmethod
    def _recycle_bin_size():
        try:
            class SHQUERYRBINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("i64Size", ctypes.c_longlong),
                    ("i64NumItems", ctypes.c_longlong),
                ]
            info = SHQUERYRBINFO()
            info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
            ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
            return info.i64Size, info.i64NumItems
        except Exception:
            return 0, 0

    def _empty_recycle_bin(self):
        if os.name != "nt":
            return False
        try:
            flags = (self.SHERB_NOCONFIRMATION | self.SHERB_NOPROGRESSUI | self.SHERB_NOSOUND)
            result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
            return result in (0, 1)
        except Exception:
            return False
