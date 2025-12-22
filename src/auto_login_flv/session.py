# -*- coding: utf-8 -*-
"""
FLV 登录会话管理模块

功能:
1. 监控 FLV URL 签名过期时间
2. 签名即将过期时自动刷新
3. 管理浏览器生命周期
"""
import asyncio
import logging
import re
from typing import Optional, Callable
from datetime import datetime

from .login import FLVLogin

logger = logging.getLogger("flv_session")


class FLVSession:
    """FLV 会话管理器 - 负责监控签名过期并自动刷新"""

    def __init__(self):
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_url_refreshed: Optional[Callable[[str], None]] = None
        self.on_refresh_failed: Optional[Callable[[str], None]] = None

        # 当前 FLV URL 和过期时间
        self.flv_url: Optional[str] = None
        self.flv_url_time: Optional[datetime] = None
        self.sign_expire_time: Optional[datetime] = None

        # 监控配置
        self.refresh_before_expire_seconds = 300  # 提前5分钟刷新
        self.check_interval_seconds = 60  # 每分钟检查一次

        # 状态
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self._desk_id: Optional[int] = None
        self._headless = True

    def log(self, message: str):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] [FLV会话] {message}"
        logger.info(log_msg)
        if self.on_log:
            self.on_log(log_msg)

    def set_flv_url(self, url: str):
        """设置当前 FLV URL 并解析过期时间"""
        self.flv_url = url
        self.flv_url_time = datetime.now()
        self.sign_expire_time = self._parse_sign_expire_time(url)

        if self.sign_expire_time:
            remaining = self.get_remaining_seconds()
            self.log(f"FLV URL 已设置, 签名剩余 {remaining} 秒")
        else:
            self.log("FLV URL 已设置, 无法解析签名过期时间")

    def _parse_sign_expire_time(self, url: str) -> Optional[datetime]:
        """解析 URL 中的签名过期时间"""
        if not url or 'sign=' not in url:
            return None
        try:
            match = re.search(r'sign=(\d+)-', url)
            if match:
                timestamp = int(match.group(1))
                return datetime.fromtimestamp(timestamp)
        except:
            pass
        return None

    def get_remaining_seconds(self) -> int:
        """获取签名剩余有效秒数"""
        if self.sign_expire_time:
            remaining = (self.sign_expire_time - datetime.now()).total_seconds()
            return max(0, int(remaining))
        return 0

    def is_sign_expiring_soon(self) -> bool:
        """检查签名是否即将过期"""
        remaining = self.get_remaining_seconds()
        return remaining > 0 and remaining <= self.refresh_before_expire_seconds

    def is_sign_expired(self) -> bool:
        """检查签名是否已过期"""
        return self.get_remaining_seconds() <= 0

    async def refresh_flv_url(self, desk_id: int = None, headless: bool = True) -> Optional[str]:
        """
        刷新 FLV URL

        Args:
            desk_id: 桌台ID，如果不提供则使用之前的
            headless: 是否无头模式

        Returns:
            新的 FLV URL 或 None
        """
        if desk_id:
            self._desk_id = desk_id
        if not self._desk_id:
            self.log("未设置桌台ID，无法刷新")
            return None

        self._headless = headless

        self.log(f"开始刷新 FLV URL (桌台 {self._desk_id})...")

        flv_login = FLVLogin()
        flv_login.on_log = self.on_log

        try:
            new_url = await flv_login.get_flv_url(self._desk_id, headless=self._headless)

            if new_url:
                self.set_flv_url(new_url)
                self.log("FLV URL 刷新成功!")

                if self.on_url_refreshed:
                    self.on_url_refreshed(new_url)

                return new_url
            else:
                self.log("FLV URL 刷新失败")
                if self.on_refresh_failed:
                    self.on_refresh_failed("获取 FLV URL 失败")
                return None

        except Exception as e:
            self.log(f"刷新 FLV URL 出错: {e}")
            if self.on_refresh_failed:
                self.on_refresh_failed(str(e))
            return None

        finally:
            await flv_login.close()

    async def start_monitor(self, desk_id: int, headless: bool = True):
        """
        启动签名过期监控

        Args:
            desk_id: 桌台ID
            headless: 是否无头模式
        """
        if self._running:
            self.log("监控已在运行")
            return

        self._desk_id = desk_id
        self._headless = headless
        self._running = True

        self.log(f"启动 FLV 签名监控 (桌台 {desk_id})")
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                if self.flv_url:
                    remaining = self.get_remaining_seconds()

                    if remaining <= 0:
                        self.log("签名已过期，立即刷新...")
                        await self.refresh_flv_url()

                    elif remaining <= self.refresh_before_expire_seconds:
                        self.log(f"签名即将过期 (剩余 {remaining}s)，提前刷新...")
                        await self.refresh_flv_url()

                await asyncio.sleep(self.check_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log(f"监控循环出错: {e}")
                await asyncio.sleep(self.check_interval_seconds)

        self.log("FLV 签名监控已停止")

    async def stop_monitor(self):
        """停止签名过期监控"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        self.log("FLV 签名监控已停止")

    def get_status(self) -> dict:
        """获取会话状态"""
        remaining = self.get_remaining_seconds()
        return {
            "has_url": self.flv_url is not None,
            "url_preview": self.flv_url[:60] + "..." if self.flv_url else None,
            "sign_remaining_seconds": remaining,
            "sign_expire_time": self.sign_expire_time.strftime("%H:%M:%S") if self.sign_expire_time else None,
            "is_expiring_soon": self.is_sign_expiring_soon(),
            "is_expired": self.is_sign_expired(),
            "monitor_running": self._running,
            "desk_id": self._desk_id,
        }
