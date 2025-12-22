# -*- coding: utf-8 -*-
"""
FLV URL 获取模块

功能:
1. 使用 Playwright 浏览器登录利博网站
2. 捕获 FLV 视频流地址（带签名）
3. 获取后关闭浏览器释放资源

使用方式:
    from flv_push import FLVUrlCapture

    capture = FLVUrlCapture(desk_id=1)
    flv_url = await capture.get_flv_url(headless=True)

注意: 此模块现在是对 auto_login_flv 模块的封装
底层登录逻辑已迁移到 auto_login_flv.login.FLVLogin
"""
import logging
from typing import Optional, Callable, Dict
from datetime import datetime

logger = logging.getLogger("flv_url_capture")


class FLVUrlCapture:
    """
    FLV URL 获取器 - 负责浏览器登录并捕获 FLV 地址

    这是对 auto_login_flv.FLVLogin 的封装，保持向后兼容
    """

    def __init__(self, desk_id: int):
        """
        初始化

        Args:
            desk_id: 桌台ID
        """
        self.desk_id = desk_id
        self.flv_url: Optional[str] = None
        self.flv_url_time: Optional[datetime] = None

        # 回调
        self.on_log: Optional[Callable[[str], None]] = None

        # 内部登录器
        self._login_handler = None

    def log(self, message: str):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] [桌{self.desk_id}] {message}"
        logger.info(log_msg)
        if self.on_log:
            self.on_log(log_msg)
        print(log_msg)

    async def get_credentials(self) -> Optional[Dict]:
        """
        从数据库获取 FLV 登录凭证

        Returns:
            {"username": "xxx", "password": "xxx", "desk_url": "xxx"}
        """
        try:
            from auto_login_flv import FLVLogin
            temp_login = FLVLogin()
            return await temp_login.get_credentials(self.desk_id)
        except Exception as e:
            self.log(f"获取登录凭证失败: {e}")
            return None

    async def get_flv_url(self, headless: bool = True) -> Optional[str]:
        """
        完整流程: 登录并获取 FLV URL

        Args:
            headless: 是否无头模式

        Returns:
            FLV URL 或 None
        """
        try:
            from auto_login_flv import FLVLogin

            self._login_handler = FLVLogin()
            self._login_handler.on_log = self.on_log

            self.log("开始获取 FLV URL...")

            flv_url = await self._login_handler.get_flv_url(
                desk_id=self.desk_id,
                headless=headless
            )

            if flv_url:
                self.flv_url = flv_url
                self.flv_url_time = self._login_handler.flv_url_time
                self.log(f"FLV URL 获取成功!")
                return flv_url
            else:
                self.log("FLV URL 获取失败")
                return None

        except Exception as e:
            self.log(f"获取 FLV URL 失败: {e}")
            return None

    async def close(self):
        """关闭浏览器释放资源"""
        if self._login_handler:
            await self._login_handler.close()
            self._login_handler = None
        self.log("浏览器资源已释放")

    def get_sign_expire_time(self) -> Optional[datetime]:
        """解析签名过期时间"""
        if self._login_handler:
            return self._login_handler.get_sign_expire_time()
        return None

    def get_sign_remaining_seconds(self) -> int:
        """获取签名剩余有效秒数"""
        if self._login_handler:
            return self._login_handler.get_sign_remaining_seconds()
        return 0
