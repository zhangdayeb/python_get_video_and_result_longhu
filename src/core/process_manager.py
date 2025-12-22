# -*- coding: utf-8 -*-
"""
进程管理模块

功能:
1. 记录浏览器进程 PID 到文件
2. 启动时检查并清理残留的旧进程
3. 注册 atexit 清理函数
4. 处理信号（SIGTERM/SIGINT）确保清理
5. 程序关闭时尝试退出登录
"""
import os
import sys
import signal
import atexit
import logging
import psutil
from pathlib import Path
from typing import Optional, Callable, List
from datetime import datetime

logger = logging.getLogger("process_manager")


class ProcessManager:
    """进程管理器"""

    def __init__(self, desk_id: int):
        self.desk_id = desk_id
        self.temp_dir = Path(__file__).parent.parent.parent / "temp" / f"desk_{desk_id}"
        self.pid_file = self.temp_dir / "browser.pid"
        self.main_pid_file = self.temp_dir / "main.pid"

        # 记录的进程 PID
        self.browser_pid: Optional[int] = None
        self.main_pid: int = os.getpid()

        # 清理回调
        self._cleanup_callbacks: List[Callable] = []

        # 是否已执行清理
        self._cleaned_up = False

        # 确保目录存在
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def initialize(self):
        """
        初始化进程管理

        1. 清理旧进程
        2. 记录当前主进程 PID
        3. 注册退出处理
        """
        logger.info(f"[进程管理] 初始化 - 桌号: {self.desk_id}, 主进程PID: {self.main_pid}")

        # 1. 清理旧进程
        self.cleanup_old_processes()

        # 2. 记录当前主进程 PID
        self._write_main_pid()

        # 3. 注册退出处理
        self._register_exit_handlers()

        logger.info("[进程管理] 初始化完成")

    def cleanup_old_processes(self):
        """清理旧的残留进程"""
        cleaned = False

        # 检查并清理旧的浏览器进程
        if self.pid_file.exists():
            try:
                old_pid = int(self.pid_file.read_text().strip())
                if self._kill_process_tree(old_pid, "浏览器"):
                    cleaned = True
            except Exception as e:
                logger.warning(f"[进程管理] 读取旧浏览器PID失败: {e}")
            finally:
                # 删除旧的 PID 文件
                try:
                    self.pid_file.unlink()
                except:
                    pass

        # 检查并清理旧的主进程（如果不是当前进程）
        if self.main_pid_file.exists():
            try:
                old_main_pid = int(self.main_pid_file.read_text().strip())
                if old_main_pid != self.main_pid:
                    if self._kill_process_tree(old_main_pid, "主程序"):
                        cleaned = True
            except Exception as e:
                logger.warning(f"[进程管理] 读取旧主进程PID失败: {e}")
            finally:
                try:
                    self.main_pid_file.unlink()
                except:
                    pass

        if cleaned:
            logger.info("[进程管理] 已清理残留进程")
        else:
            logger.info("[进程管理] 无残留进程需要清理")

    def _kill_process_tree(self, pid: int, name: str = "进程") -> bool:
        """
        杀掉进程及其所有子进程

        Args:
            pid: 进程 ID
            name: 进程名称（用于日志）

        Returns:
            是否成功杀掉进程
        """
        try:
            if not psutil.pid_exists(pid):
                logger.debug(f"[进程管理] {name} PID {pid} 不存在")
                return False

            process = psutil.Process(pid)

            # 获取进程信息
            try:
                proc_name = process.name()
                proc_cmdline = ' '.join(process.cmdline()[:3])  # 只取前3个参数
            except:
                proc_name = "unknown"
                proc_cmdline = ""

            logger.info(f"[进程管理] 发现残留{name}: PID={pid}, 名称={proc_name}")

            # 获取所有子进程
            children = []
            try:
                children = process.children(recursive=True)
            except:
                pass

            # 先杀子进程
            for child in children:
                try:
                    logger.debug(f"[进程管理] 杀掉子进程: PID={child.pid}, 名称={child.name()}")
                    child.kill()
                except:
                    pass

            # 再杀主进程
            try:
                process.kill()
                logger.info(f"[进程管理] 已杀掉{name}: PID={pid}")
                return True
            except psutil.NoSuchProcess:
                logger.debug(f"[进程管理] {name}已不存在: PID={pid}")
                return False
            except Exception as e:
                logger.warning(f"[进程管理] 杀掉{name}失败: PID={pid}, 错误={e}")
                return False

        except psutil.NoSuchProcess:
            return False
        except Exception as e:
            logger.warning(f"[进程管理] 处理{name}进程失败: {e}")
            return False

    def _write_main_pid(self):
        """记录主进程 PID"""
        try:
            self.main_pid_file.write_text(str(self.main_pid))
            logger.debug(f"[进程管理] 已记录主进程PID: {self.main_pid}")
        except Exception as e:
            logger.warning(f"[进程管理] 记录主进程PID失败: {e}")

    def record_browser_pid(self, pid: int):
        """
        记录浏览器进程 PID

        Args:
            pid: 浏览器进程 ID
        """
        self.browser_pid = pid
        try:
            self.pid_file.write_text(str(pid))
            logger.info(f"[进程管理] 已记录浏览器PID: {pid}")
        except Exception as e:
            logger.warning(f"[进程管理] 记录浏览器PID失败: {e}")

    def clear_browser_pid(self):
        """清除浏览器 PID 记录"""
        self.browser_pid = None
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
                logger.debug("[进程管理] 已清除浏览器PID文件")
        except Exception as e:
            logger.warning(f"[进程管理] 清除浏览器PID文件失败: {e}")

    def add_cleanup_callback(self, callback: Callable):
        """
        添加清理回调函数

        程序退出时会调用这些回调
        """
        self._cleanup_callbacks.append(callback)
        logger.debug(f"[进程管理] 已添加清理回调: {callback.__name__ if hasattr(callback, '__name__') else callback}")

    def _register_exit_handlers(self):
        """注册退出处理器"""
        # 注册 atexit
        atexit.register(self._on_exit)

        # 注册信号处理（仅在主线程）
        try:
            # SIGINT (Ctrl+C)
            signal.signal(signal.SIGINT, self._signal_handler)

            # SIGTERM (kill 命令)
            signal.signal(signal.SIGTERM, self._signal_handler)

            # Windows 特有: SIGBREAK (Ctrl+Break)
            if sys.platform == 'win32':
                signal.signal(signal.SIGBREAK, self._signal_handler)

            logger.debug("[进程管理] 已注册信号处理器")
        except Exception as e:
            logger.warning(f"[进程管理] 注册信号处理器失败: {e}")

    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        logger.info(f"[进程管理] 收到信号: {sig_name}")

        # 执行清理
        self._do_cleanup()

        # 退出程序
        sys.exit(0)

    def _on_exit(self):
        """atexit 回调"""
        logger.debug("[进程管理] atexit 触发")
        self._do_cleanup()

    def _do_cleanup(self):
        """执行清理"""
        if self._cleaned_up:
            return
        self._cleaned_up = True

        logger.info("[进程管理] 开始清理...")

        # 1. 执行注册的清理回调
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"[进程管理] 清理回调失败: {e}")

        # 2. 杀掉浏览器进程
        if self.browser_pid:
            self._kill_process_tree(self.browser_pid, "浏览器")

        # 3. 清理 PID 文件
        self.clear_browser_pid()
        try:
            if self.main_pid_file.exists():
                self.main_pid_file.unlink()
        except:
            pass

        logger.info("[进程管理] 清理完成")

    def force_cleanup(self):
        """强制执行清理（供外部调用）"""
        self._cleaned_up = False  # 重置标记，允许再次清理
        self._do_cleanup()

    def get_status(self) -> dict:
        """获取进程状态信息"""
        status = {
            "desk_id": self.desk_id,
            "main_pid": self.main_pid,
            "browser_pid": self.browser_pid,
            "browser_running": False,
            "cleanup_callbacks_count": len(self._cleanup_callbacks)
        }

        # 检查浏览器是否在运行
        if self.browser_pid:
            try:
                status["browser_running"] = psutil.pid_exists(self.browser_pid)
            except:
                pass

        return status


# 全局实例（在 main.py 中初始化）
_process_manager: Optional[ProcessManager] = None


def init_process_manager(desk_id: int) -> ProcessManager:
    """初始化全局进程管理器"""
    global _process_manager
    _process_manager = ProcessManager(desk_id)
    _process_manager.initialize()
    return _process_manager


def get_process_manager() -> Optional[ProcessManager]:
    """获取全局进程管理器"""
    return _process_manager
