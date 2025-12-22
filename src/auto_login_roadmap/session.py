# -*- coding: utf-8 -*-
"""
路单采集 Session 监控模块

功能:
1. 监控 session 是否过期（被踢出）
2. 自动重新登录
3. 登录失败后的定时重试
"""
import asyncio
import logging
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger("roadmap_session")


class RoadmapSession:
    """路单采集 Session 监控器"""

    # Session 过期的页面特征（被踢出后会跳转到这些页面）
    SESSION_EXPIRED_INDICATORS = [
        "/login",
        "/select-server-line",
    ]

    def __init__(self):
        self.on_log: Optional[Callable[[str], None]] = None
        self._session_monitor_running = False
        self._login_retry_running = False
        self._credentials: Dict[str, Any] = {}
        self.login_retry_interval = 10 * 60  # 默认10分钟
        self.login_retry_max_attempts = 0    # 0表示无限重试

    def log(self, message: str):
        """输出日志"""
        logger.info(message)
        if self.on_log:
            self.on_log(message)

    def save_credentials(self, username: str, password: str, target_url: str = None):
        """保存登录凭证（用于 session 过期后自动重新登录）"""
        self._credentials = {
            "username": username,
            "password": password,
            "target_url": target_url
        }
        logger.info(f"[Session监控] 已保存登录凭证: {username}")

    def clear_credentials(self):
        """清除保存的登录凭证"""
        self._credentials = {}
        logger.info("[Session监控] 已清除登录凭证")

    def get_credentials(self) -> Dict[str, Any]:
        """获取保存的登录凭证"""
        return self._credentials.copy()

    async def check_session_expired(self, page) -> bool:
        """检查 session 是否过期"""
        try:
            current_url = page.url

            for indicator in self.SESSION_EXPIRED_INDICATORS:
                if indicator in current_url:
                    return True

            return False

        except Exception as e:
            logger.error(f"[Session监控] 检查失败: {e}")
            return False

    async def handle_session_expired(self, page, login_func) -> dict:
        """
        处理 session 过期（自动重新登录）

        Args:
            page: Playwright page 对象
            login_func: 登录函数，签名为 async def(page, username, password, target_url) -> dict

        Returns:
            {"success": bool, "message": str}
        """
        if not self._credentials:
            self.log("[Session监控] 无保存的登录凭证，无法自动重新登录")
            return {
                "success": False,
                "message": "无登录凭证"
            }

        username = self._credentials.get("username", "")
        password = self._credentials.get("password", "")
        target_url = self._credentials.get("target_url", "")

        self.log(f"[Session监控] 检测到 session 过期，正在重新登录...")
        self.log(f"[Session监控] 账号: {username}")

        result = await login_func(page, username, password, target_url)

        if result.get("success"):
            self.log("[Session监控] 重新登录成功!")
        else:
            self.log(f"[Session监控] 重新登录失败: {result.get('message')}")

        return result

    async def start_session_monitor(
        self,
        page,
        login_func,
        check_interval: int = 30,
        on_session_expired: Optional[Callable[[], None]] = None,
        on_relogin_success: Optional[Callable[[], None]] = None,
        on_relogin_failed: Optional[Callable[[str], None]] = None
    ):
        """
        启动 session 监控

        Args:
            page: Playwright page 对象
            login_func: 登录函数
            check_interval: 检查间隔（秒）
            on_session_expired: session 过期时的回调
            on_relogin_success: 重新登录成功的回调
            on_relogin_failed: 重新登录失败的回调
        """
        if self._session_monitor_running:
            self.log("[Session监控] 监控已在运行中")
            return

        self._session_monitor_running = True
        self.log(f"[Session监控] 启动监控，检查间隔: {check_interval}秒")

        while self._session_monitor_running:
            try:
                await asyncio.sleep(check_interval)

                if not self._session_monitor_running:
                    break

                is_expired = await self.check_session_expired(page)

                if is_expired:
                    self.log("[Session监控] 检测到 session 过期!")

                    if on_session_expired:
                        on_session_expired()

                    result = await self.handle_session_expired(page, login_func)

                    if result.get("success"):
                        if on_relogin_success:
                            on_relogin_success()
                    else:
                        if on_relogin_failed:
                            on_relogin_failed(result.get("message", "未知错误"))

            except asyncio.CancelledError:
                self.log("[Session监控] 监控任务被取消")
                break
            except Exception as e:
                logger.error(f"[Session监控] 监控出错: {e}")
                await asyncio.sleep(5)

        self._session_monitor_running = False
        self.log("[Session监控] 监控已停止")

    def stop_session_monitor(self):
        """停止 session 监控"""
        if self._session_monitor_running:
            self._session_monitor_running = False
            self.log("[Session监控] 正在停止监控...")

    @property
    def is_monitoring(self) -> bool:
        """是否正在监控 session"""
        return self._session_monitor_running

    async def start_login_retry_loop(
        self,
        page,
        login_func,
        username: str,
        password: str,
        target_url: str = None,
        retry_interval: int = None,
        max_attempts: int = None,
        on_retry_start: Optional[Callable[[int, int], None]] = None,
        on_retry_countdown: Optional[Callable[[int], None]] = None,
        on_login_success: Optional[Callable[[], None]] = None,
        on_login_failed: Optional[Callable[[str], None]] = None
    ):
        """
        启动登录重试循环（用于账号被占用等情况）

        Args:
            page: Playwright page 对象
            login_func: 登录函数
            username: 用户名
            password: 密码
            target_url: 目标页面URL
            retry_interval: 重试间隔（秒）
            max_attempts: 最大重试次数，0表示无限
            on_retry_start: 重试开始回调
            on_retry_countdown: 倒计时回调
            on_login_success: 登录成功回调
            on_login_failed: 登录失败回调
        """
        if self._login_retry_running:
            self.log("[登录重试] 重试循环已在运行中")
            return

        interval = retry_interval or self.login_retry_interval
        max_tries = max_attempts if max_attempts is not None else self.login_retry_max_attempts

        self._login_retry_running = True
        attempt = 0

        self.log(f"[登录重试] 启动重试循环，间隔: {interval}秒 ({interval//60}分钟)")

        while self._login_retry_running:
            attempt += 1

            if max_tries > 0 and attempt > max_tries:
                self.log(f"[登录重试] 已达到最大重试次数 {max_tries}")
                if on_login_failed:
                    on_login_failed(f"已重试 {max_tries} 次，全部失败")
                break

            self.log(f"[登录重试] 第 {attempt} 次尝试" + (f" / {max_tries}" if max_tries > 0 else ""))

            if on_retry_start:
                on_retry_start(attempt, max_tries)

            try:
                result = await login_func(page, username, password, target_url)

                if result.get("success"):
                    self.log("[登录重试] 登录成功!")
                    self._login_retry_running = False
                    if on_login_success:
                        on_login_success()
                    return

                error_msg = result.get("message", "未知错误")
                self.log(f"[登录重试] 登录失败: {error_msg}")
                self.log(f"[登录重试] 等待 {interval//60} 分钟后重试...")

                # 倒计时
                for remaining in range(interval, 0, -1):
                    if not self._login_retry_running:
                        self.log("[登录重试] 重试循环被停止")
                        return

                    if on_retry_countdown and remaining % 60 == 0:
                        on_retry_countdown(remaining)

                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                self.log("[登录重试] 任务被取消")
                break
            except Exception as e:
                self.log(f"[登录重试] 出错: {e}")
                await asyncio.sleep(60)

        self._login_retry_running = False
        self.log("[登录重试] 重试循环结束")

    def stop_login_retry_loop(self):
        """停止登录重试循环"""
        if self._login_retry_running:
            self._login_retry_running = False
            self.log("[登录重试] 正在停止重试循环...")

    @property
    def is_retrying_login(self) -> bool:
        """是否正在重试登录"""
        return self._login_retry_running
