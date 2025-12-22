# -*- coding: utf-8 -*-
"""
路单采集退出登录模块

功能:
1. 尝试多种方式退出登录
2. 清除浏览器存储
"""
import asyncio
import logging
from typing import Optional, Callable

logger = logging.getLogger("roadmap_logout")


class RoadmapLogout:
    """路单采集退出登录处理器"""

    # 退出登录相关选择器
    LOGOUT_SELECTORS = {
        "user_menu": [
            '.user-info',
            '.user-avatar',
            '.header-user',
            '.user-menu',
            '.dropdown-toggle',
        ],
        "logout_btn": [
            'a[href*="logout"]',
            'button:has-text("退出")',
            'a:has-text("退出")',
            'button:has-text("登出")',
            'a:has-text("登出")',
            '.logout',
            '.logout-btn',
            '#logout',
        ],
    }

    def __init__(self):
        self.on_log: Optional[Callable[[str], None]] = None

    def log(self, message: str):
        """输出日志"""
        logger.info(message)
        if self.on_log:
            self.on_log(message)

    async def logout(self, page) -> dict:
        """
        执行退出登录

        Args:
            page: Playwright page 对象

        Returns:
            {"success": bool, "message": str}
        """
        result = {
            "success": False,
            "message": ""
        }

        try:
            current_url = page.url

            # 检查是否在登录页面（已经退出了）
            if "/login" in current_url or "/select-server-line" in current_url:
                self.log("[退出] 当前已在登录页面，无需退出")
                result["success"] = True
                result["message"] = "已在登录页面"
                return result

            self.log("[退出] 尝试退出登录...")

            # 方法1: 尝试直接访问退出URL
            logout_urls = [
                "https://www.559156667.com/logout",
                "https://www.559156667.com/api/logout",
                "https://www.559156667.com/user/logout",
            ]

            for logout_url in logout_urls:
                try:
                    self.log(f"[退出] 尝试访问: {logout_url}")
                    await page.goto(logout_url, wait_until="networkidle", timeout=5000)
                    await asyncio.sleep(1)

                    current_url = page.url
                    if "/login" in current_url or "/select-server-line" in current_url:
                        self.log("[退出] 退出成功!")
                        result["success"] = True
                        result["message"] = "退出成功"
                        return result
                except Exception as e:
                    self.log(f"[退出] URL {logout_url} 失败: {e}")
                    continue

            # 方法2: 尝试点击退出按钮
            self.log("[退出] 尝试查找退出按钮...")

            for menu_selector in self.LOGOUT_SELECTORS["user_menu"]:
                try:
                    menu = page.locator(menu_selector)
                    if await menu.count() > 0:
                        self.log(f"[退出] 点击用户菜单: {menu_selector}")
                        await menu.first.click()
                        await asyncio.sleep(0.5)
                        break
                except:
                    continue

            for logout_selector in self.LOGOUT_SELECTORS["logout_btn"]:
                try:
                    logout_btn = page.locator(logout_selector)
                    if await logout_btn.count() > 0:
                        self.log(f"[退出] 点击退出按钮: {logout_selector}")
                        await logout_btn.first.click()
                        await asyncio.sleep(2)

                        current_url = page.url
                        if "/login" in current_url or "/select-server-line" in current_url:
                            self.log("[退出] 退出成功!")
                            result["success"] = True
                            result["message"] = "退出成功"
                            return result
                except:
                    continue

            # 方法3: 清除浏览器存储来强制退出
            self.log("[退出] 尝试清除浏览器存储...")
            try:
                await page.evaluate("""
                    localStorage.clear();
                    sessionStorage.clear();
                """)
                self.log("[退出] 已清除本地存储")

                await page.reload()
                await asyncio.sleep(2)

                current_url = page.url
                if "/login" in current_url or "/select-server-line" in current_url:
                    self.log("[退出] 退出成功（通过清除存储）!")
                    result["success"] = True
                    result["message"] = "退出成功（清除存储）"
                    return result
            except Exception as e:
                self.log(f"[退出] 清除存储失败: {e}")

            result["message"] = "退出失败，未找到退出方式"
            self.log(f"[退出] {result['message']}")

        except Exception as e:
            result["message"] = f"退出出错: {e}"
            self.log(f"[退出] {result['message']}")

        return result
