# -*- coding: utf-8 -*-
"""
Cookie/Storage监控器
"""
import base64
import time
import logging
from typing import Optional, Callable

logger = logging.getLogger("storage_monitor")


class StorageMonitor:
    """Cookie和Storage监控器"""

    def __init__(self, write_log_callback: Callable = None):
        """
        初始化Storage监控器

        Args:
            write_log_callback: 日志写入回调函数
        """
        self._write_log = write_log_callback
        self._last_check_time = 0
        self.check_interval = 10  # 每10秒检查一次

        # 缓存凭证 (用于API调用)
        self.cached_session_id: str = ""
        self.cached_username: str = ""

    async def capture(self, context, page):
        """
        捕获Cookie和Storage

        Args:
            context: Playwright browser context
            page: Playwright page
        """
        # 限制检查频率
        now = time.time()
        if now - self._last_check_time < self.check_interval:
            return
        self._last_check_time = now

        try:
            await self._capture_cookies(context)
            await self._capture_local_storage(page)
            await self._capture_session_storage(page)
        except Exception as e:
            logger.error(f"捕获存储失败: {e}")

    async def _capture_cookies(self, context):
        """捕获Cookie"""
        try:
            cookies = await context.cookies()
            if cookies and self._write_log:
                self._write_log("cookies", {
                    "count": len(cookies),
                    "items": [{"name": c["name"], "value": c["value"][:50]} for c in cookies[:10]]
                })
        except Exception as e:
            pass

    async def _capture_local_storage(self, page):
        """捕获LocalStorage"""
        try:
            storage = await page.evaluate("""
                () => {
                    const result = {};
                    try {
                        for (let i = 0; i < localStorage.length; i++) {
                            const key = localStorage.key(i);
                            result[key] = localStorage.getItem(key);
                        }
                    } catch(e) {}
                    return result;
                }
            """)

            if storage and self._write_log:
                self._write_log("local_storage", {
                    "count": len(storage),
                    "keys": list(storage.keys())[:20]
                })
        except Exception as e:
            pass

    async def _capture_session_storage(self, page):
        """捕获SessionStorage并提取凭证"""
        try:
            session_storage = await page.evaluate("""
                () => {
                    const result = {};
                    try {
                        for (let i = 0; i < sessionStorage.length; i++) {
                            const key = sessionStorage.key(i);
                            result[key] = sessionStorage.getItem(key);
                        }
                    } catch(e) {}
                    return result;
                }
            """)

            if session_storage:
                # 提取并缓存API调用凭证
                ply004 = session_storage.get('ply004', '')
                user_name = session_storage.get('USER_NAME', '')

                if ply004:
                    try:
                        self.cached_session_id = base64.b64decode(ply004).decode('utf-8')
                    except:
                        self.cached_session_id = ply004
                    logger.info(f"[Storage] 获取到sessionID: {self.cached_session_id[:30]}...")

                if user_name:
                    try:
                        self.cached_username = base64.b64decode(user_name).decode('utf-8')
                    except:
                        self.cached_username = user_name
                    logger.info(f"[Storage] 获取到username: {self.cached_username}")

                if self._write_log:
                    self._write_log("session_storage", {
                        "count": len(session_storage),
                        "keys": list(session_storage.keys())[:20],
                        "has_credentials": bool(ply004)
                    })
        except Exception as e:
            pass
