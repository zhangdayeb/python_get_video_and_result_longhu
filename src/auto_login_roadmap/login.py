# -*- coding: utf-8 -*-
"""
路单采集浏览器登录模块

功能:
1. 自动选择可用线路
2. 自动填写用户名、密码、验证码
3. 自动点击登录
4. 登录成功后跳转到指定台桌页面
"""
import asyncio
import logging
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger("roadmap_login")


class RoadmapLogin:
    """路单采集浏览器登录处理器"""

    # 线路选择页面选择器
    LINE_SELECTORS = {
        "available_line": '.server-select-root .btn-group .btn:not(.disabled)',
        "all_lines": '.server-select-root .btn-group .btn',
        "page_root": '.server-select-root',
    }

    # 登录页面选择器
    LOGIN_SELECTORS = {
        "username": '.login-root input[type="text"]',
        "password": '.login-root input[type="password"]',
        "captcha_input": '.login-root input[type="number"]',
        "captcha_text": '.capcha',
        "submit_btn": '.submit',
        "error_msg": '.login-root .error',
        "page_root": '.login-root',
    }

    # 登录成功后的页面特征
    GAME_PAGE_INDICATORS = [
        ".game-root",
        ".game-head",
        ".video-wraps",
    ]

    # 账号被占用等需要长时间等待的错误关键词
    ACCOUNT_OCCUPIED_KEYWORDS = [
        "已经登录",
        "已登录",
        "被占用",
        "占用中",
        "正在使用",
        "account is logged",
        "already logged",
    ]

    def __init__(self):
        self.on_log: Optional[Callable[[str], None]] = None
        self.max_retry = 3

    def log(self, message: str):
        """输出日志"""
        logger.info(message)
        if self.on_log:
            self.on_log(message)

    async def select_server_line(self, page) -> bool:
        """选择可用线路"""
        try:
            current_url = page.url

            if "select-server-line" not in current_url:
                self.log("[线路] 不在线路选择页面，跳过")
                return True

            self.log("[线路] 检测到线路选择页面")

            await page.wait_for_selector(self.LINE_SELECTORS["page_root"], timeout=20000)
            await asyncio.sleep(1)

            available_lines = page.locator(self.LINE_SELECTORS["available_line"])
            count = await available_lines.count()

            if count == 0:
                self.log("[线路] 没有找到可用线路!")
                return False

            self.log(f"[线路] 找到 {count} 个可用线路")

            first_line = available_lines.first
            line_text = await first_line.text_content()
            self.log(f"[线路] 选择: {line_text.strip() if line_text else '线路'}")

            await first_line.click()
            await asyncio.sleep(2)

            current_url = page.url
            if "/login" in current_url:
                self.log("[线路] 已跳转到登录页面")
                return True
            elif "select-server-line" not in current_url:
                self.log(f"[线路] 已跳转到: {current_url}")
                return True
            else:
                self.log("[线路] 点击后未跳转，重试...")
                return False

        except Exception as e:
            self.log(f"[线路] 选择失败: {e}")
            return False

    async def login(
        self,
        page,
        username: str,
        password: str,
        target_url: str = None,
        login_url: str = "https://www.559156667.com/login"
    ) -> dict:
        """
        执行自动登录

        Args:
            page: Playwright page 对象
            username: 用户名
            password: 密码
            target_url: 登录成功后跳转的目标页面
            login_url: 登录页面地址

        Returns:
            {"success": bool, "message": str, "current_url": str}
        """
        result = {
            "success": False,
            "message": "",
            "current_url": ""
        }

        for attempt in range(1, self.max_retry + 1):
            self.log(f"[登录] 第 {attempt} 次尝试...")

            try:
                current_url = page.url
                base_url = "https://www.559156667.com"

                # 访问网站首页
                if not current_url or current_url == "about:blank":
                    self.log(f"[登录] 访问网站: {base_url}")
                    await page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(2)
                    current_url = page.url

                # 处理线路选择页面
                if "select-server-line" in current_url:
                    self.log("[登录] 检测到线路选择页面")
                    line_result = await self.select_server_line(page)
                    if not line_result:
                        await asyncio.sleep(1)
                        continue
                    await asyncio.sleep(1)
                    current_url = page.url

                # 如果已在游戏页面
                if "/game" in current_url:
                    self.log("[登录] 检测到已在游戏页面...")
                    if target_url and target_url not in current_url:
                        try:
                            self.log(f"[登录] 跳转到目标台桌: {target_url[:60]}...")
                            await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                            await asyncio.sleep(1)
                        except Exception as e:
                            self.log(f"[登录] 跳转超时，但已在游戏页面: {e}")
                    result["success"] = True
                    result["message"] = "已在游戏页面"
                    result["current_url"] = page.url
                    return result

                # 跳转到登录页
                if "/login" not in current_url:
                    self.log(f"[登录] 访问登录页面: {login_url}")
                    await page.goto(login_url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(1)

                    current_url = page.url
                    if "select-server-line" in current_url:
                        line_result = await self.select_server_line(page)
                        if not line_result:
                            continue
                        await asyncio.sleep(1)

                    current_url = page.url
                    if "/game" in current_url:
                        self.log("[登录] 访问登录页后被重定向到游戏页面，session有效")
                        if target_url and target_url not in current_url:
                            try:
                                await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                                await asyncio.sleep(1)
                            except Exception as nav_err:
                                self.log(f"[登录] 跳转超时（已登录）: {nav_err}")
                        result["success"] = True
                        result["message"] = "Session有效，已登录"
                        result["current_url"] = page.url
                        return result

                # 等待登录表单加载
                self.log("[登录] 等待登录表单加载...")
                await page.wait_for_selector(self.LOGIN_SELECTORS["username"], timeout=20000)

                # 填写用户名
                self.log(f"[登录] 填写用户名: {username}")
                await page.fill(self.LOGIN_SELECTORS["username"], "")
                await page.fill(self.LOGIN_SELECTORS["username"], username)
                await asyncio.sleep(0.3)

                # 填写密码
                self.log("[登录] 填写密码: ******")
                await page.fill(self.LOGIN_SELECTORS["password"], "")
                await page.fill(self.LOGIN_SELECTORS["password"], password)
                await asyncio.sleep(0.3)

                # 读取验证码
                captcha_text = await page.text_content(self.LOGIN_SELECTORS["captcha_text"])
                captcha_text = captcha_text.strip() if captcha_text else ""

                if not captcha_text:
                    self.log("[登录] 警告: 未能读取到验证码")
                    await asyncio.sleep(1)
                    continue

                self.log(f"[登录] 读取验证码: {captcha_text}")

                # 填写验证码
                await page.fill(self.LOGIN_SELECTORS["captcha_input"], "")
                await page.fill(self.LOGIN_SELECTORS["captcha_input"], captcha_text)
                await asyncio.sleep(0.3)

                # 点击登录
                self.log("[登录] 点击登录按钮...")
                await page.click(self.LOGIN_SELECTORS["submit_btn"])
                await asyncio.sleep(2)

                # 检查错误消息
                error_element = page.locator(self.LOGIN_SELECTORS["error_msg"])
                error_text = await error_element.text_content() if await error_element.count() > 0 else ""

                if error_text and error_text.strip():
                    error_text_clean = error_text.strip()
                    self.log(f"[登录] 登录失败: {error_text_clean}")

                    is_account_occupied = any(
                        keyword in error_text_clean.lower()
                        for keyword in self.ACCOUNT_OCCUPIED_KEYWORDS
                    )

                    if is_account_occupied:
                        result["error_type"] = "account_occupied"
                        result["message"] = error_text_clean
                        result["current_url"] = page.url
                        return result

                    await asyncio.sleep(1)
                    continue

                # 检查是否登录成功
                current_url = page.url
                self.log(f"[登录] 当前URL: {current_url}")

                if "/login" not in current_url:
                    self.log("[登录] 登录成功!")

                    if target_url:
                        self.log(f"[登录] 跳转到目标页面: {target_url}")
                        try:
                            # 使用较短超时和domcontentloaded，避免网络活动导致卡住
                            await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                            await asyncio.sleep(2)
                        except Exception as nav_err:
                            # 跳转超时不影响登录成功状态
                            self.log(f"[登录] 跳转超时（已登录）: {nav_err}")

                        for indicator in self.GAME_PAGE_INDICATORS:
                            try:
                                await page.wait_for_selector(indicator, timeout=5000)
                                self.log(f"[登录] 游戏页面已加载")
                                break
                            except:
                                continue

                    result["success"] = True
                    result["message"] = "登录成功"
                    result["current_url"] = page.url
                    return result

            except Exception as e:
                self.log(f"[登录] 尝试 {attempt} 失败: {e}")
                await asyncio.sleep(1)

        result["message"] = f"登录失败，已重试 {self.max_retry} 次"
        result["current_url"] = page.url if page else ""
        return result

    async def check_login_status(self, page) -> bool:
        """检查是否已登录"""
        try:
            current_url = page.url

            if "/login" in current_url:
                return False

            if "/game" in current_url:
                return True

            for indicator in self.GAME_PAGE_INDICATORS:
                try:
                    count = await page.locator(indicator).count()
                    if count > 0:
                        return True
                except:
                    continue

            return False

        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return False

    async def ensure_logged_in(
        self,
        page,
        username: str,
        password: str,
        target_url: str = None
    ) -> dict:
        """确保已登录（如果未登录则自动登录）"""
        is_logged_in = await self.check_login_status(page)

        if is_logged_in:
            self.log("[登录] 检测到已登录状态")

            if target_url and target_url not in page.url:
                self.log(f"[登录] 跳转到目标页面: {target_url}")
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)
                except Exception as nav_err:
                    self.log(f"[登录] 跳转超时（已登录）: {nav_err}")

            return {
                "success": True,
                "message": "已登录",
                "was_logged_in": True,
                "current_url": page.url
            }

        self.log("[登录] 检测到未登录状态，开始自动登录...")
        result = await self.login(page, username, password, target_url)
        result["was_logged_in"] = False
        return result
