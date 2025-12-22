# -*- coding: utf-8 -*-
"""
FLV 浏览器登录模块

功能:
1. 自动选择可用线路
2. 自动填写用户名、密码、验证码
3. 登录成功后捕获 FLV 视频流地址
4. 获取成功后关闭浏览器

与路单登录的区别:
- FLV 登录目的是获取 FLV URL，获取后立即关闭浏览器
- 使用独立的浏览器数据目录，与路单浏览器完全隔离
"""
import asyncio
import logging
import re
from typing import Optional, Callable, Dict
from datetime import datetime

from playwright.async_api import async_playwright, Page, BrowserContext

logger = logging.getLogger("flv_login")


class FLVLogin:
    """FLV 浏览器登录处理器"""

    # 线路选择页面选择器
    LINE_SELECTORS = {
        "available_line": '.server-select-root .btn-group .btn:not(.disabled)',
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

    def __init__(self):
        self.on_log: Optional[Callable[[str], None]] = None
        self.max_retry = 3

        # FLV URL 捕获
        self.flv_url: Optional[str] = None
        self.flv_url_time: Optional[datetime] = None

        # Playwright 资源
        self._playwright = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def log(self, message: str):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        logger.info(log_msg)
        if self.on_log:
            self.on_log(log_msg)

    async def get_credentials(self, desk_id: int) -> Optional[Dict]:
        """从API获取 FLV 登录凭证"""
        try:
            from api.online_get_xue_pu import get_caiji_config
            response = await get_caiji_config(desk_id)
            if response.success and response.data:
                return {
                    "username": response.data.get("caiji_flv_username"),
                    "password": response.data.get("caiji_flv_password"),
                    "desk_url": response.data.get("caiji_desk_url")
                }
            return None
        except Exception as e:
            self.log(f"获取登录凭证失败: {e}")
            return None

    async def start_browser(self, desk_id: int, headless: bool = None) -> bool:
        """启动浏览器"""
        try:
            self.log("启动浏览器...")

            # 使用独立的用户数据目录
            from core.config import config
            flv_user_data_dir = config.base_dir / "temp" / f"desk_{desk_id}" / "flv_browser_data"
            flv_user_data_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"浏览器数据目录: {flv_user_data_dir}")

            # 从配置读取 FLV 浏览器的 headless 模式，默认隐藏
            if headless is None:
                headless = config.get("browser.flv_headless", True)

            self._playwright = await async_playwright().start()

            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(flv_user_data_dir),
                headless=headless,
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--no-first-run',
                    '--no-default-browser-check',
                ]
            )

            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = await self._context.new_page()

            # 设置网络请求监听 - 捕获 FLV URL
            self._page.on("request", self._on_request)

            self.log("浏览器启动成功")
            return True

        except Exception as e:
            self.log(f"启动浏览器失败: {e}")
            return False

    def _on_request(self, request):
        """HTTP 请求监听 - 捕获 FLV 地址"""
        try:
            url = request.url
            if '.flv' in url and 'sign=' in url:
                old_url = self.flv_url
                self.flv_url = url
                self.flv_url_time = datetime.now()

                if old_url != url:
                    self.log(f"捕获 FLV 地址: {url[:80]}...")
        except:
            pass

    async def select_server_line(self) -> bool:
        """选择服务器线路"""
        try:
            current_url = self._page.url

            if "select-server-line" not in current_url:
                return True

            self.log("检测到线路选择页面...")

            await self._page.wait_for_selector(
                self.LINE_SELECTORS["page_root"],
                timeout=20000
            )
            await asyncio.sleep(1)

            available_lines = self._page.locator(self.LINE_SELECTORS["available_line"])
            count = await available_lines.count()

            if count == 0:
                self.log("没有可用线路!")
                return False

            self.log(f"找到 {count} 个可用线路，选择第一个...")
            await available_lines.first.click()
            await asyncio.sleep(2)

            current_url = self._page.url
            if "/login" in current_url:
                self.log("已跳转到登录页面")
                return True

            return "select-server-line" not in current_url

        except Exception as e:
            self.log(f"选择线路失败: {e}")
            return False

    async def login(self, username: str, password: str) -> bool:
        """执行登录"""
        for attempt in range(1, self.max_retry + 1):
            self.log(f"登录尝试 {attempt}/{self.max_retry}...")

            try:
                current_url = self._page.url
                base_url = "https://www.559156667.com"

                if not current_url or current_url == "about:blank":
                    self.log(f"访问网站: {base_url}")
                    await self._page.goto(base_url, wait_until="networkidle")
                    await asyncio.sleep(2)
                    current_url = self._page.url

                if "select-server-line" in current_url:
                    if not await self.select_server_line():
                        continue
                    current_url = self._page.url

                if "/login" not in current_url:
                    login_url = f"{base_url}/login"
                    self.log(f"访问登录页: {login_url}")
                    await self._page.goto(login_url, wait_until="networkidle")
                    await asyncio.sleep(1)

                    current_url = self._page.url
                    if "select-server-line" in current_url:
                        if not await self.select_server_line():
                            continue

                # 等待登录表单
                self.log("等待登录表单...")
                await self._page.wait_for_selector(
                    self.LOGIN_SELECTORS["username"],
                    timeout=20000
                )

                # 填写用户名
                self.log(f"填写用户名: {username}")
                await self._page.fill(self.LOGIN_SELECTORS["username"], "")
                await self._page.fill(self.LOGIN_SELECTORS["username"], username)
                await asyncio.sleep(0.3)

                # 填写密码
                self.log("填写密码: ******")
                await self._page.fill(self.LOGIN_SELECTORS["password"], "")
                await self._page.fill(self.LOGIN_SELECTORS["password"], password)
                await asyncio.sleep(0.3)

                # 读取验证码
                captcha_text = await self._page.text_content(
                    self.LOGIN_SELECTORS["captcha_text"]
                )
                captcha_text = captcha_text.strip() if captcha_text else ""

                if not captcha_text:
                    self.log("未能读取验证码，重试...")
                    await asyncio.sleep(1)
                    continue

                self.log(f"验证码: {captcha_text}")

                # 填写验证码
                await self._page.fill(self.LOGIN_SELECTORS["captcha_input"], "")
                await self._page.fill(self.LOGIN_SELECTORS["captcha_input"], captcha_text)
                await asyncio.sleep(0.3)

                # 点击登录
                self.log("点击登录...")
                await self._page.click(self.LOGIN_SELECTORS["submit_btn"])
                await asyncio.sleep(2)

                # 检查错误
                error_element = self._page.locator(self.LOGIN_SELECTORS["error_msg"])
                error_text = await error_element.text_content() if await error_element.count() > 0 else ""

                if error_text and error_text.strip():
                    self.log(f"登录失败: {error_text.strip()}")
                    await asyncio.sleep(1)
                    continue

                current_url = self._page.url
                if "/login" not in current_url:
                    self.log("登录成功!")
                    return True

            except Exception as e:
                self.log(f"登录尝试 {attempt} 出错: {e}")
                await asyncio.sleep(1)

        self.log(f"登录失败，已重试 {self.max_retry} 次")
        return False

    async def navigate_to_game(self, desk_url: str, desk_id: int) -> bool:
        """跳转到游戏页面并捕获 FLV URL"""
        try:
            if not desk_url:
                desk_url = f"https://www.559156667.com/game?desk={desk_id}&gameType=2&xian=1"

            self.log(f"跳转到游戏页面...")

            try:
                await self._page.goto(desk_url, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                self.log(f"页面加载: {e}")

            # 等待视频流加载
            self.log("等待视频流...")
            for i in range(10):
                await asyncio.sleep(1)
                if self.flv_url:
                    self.log(f"FLV 地址已捕获!")
                    return True

            if self.flv_url:
                return True
            else:
                self.log("未能捕获 FLV 地址")
                return False

        except Exception as e:
            self.log(f"跳转游戏页面失败: {e}")
            if self.flv_url:
                return True
            return False

    async def get_flv_url(self, desk_id: int, headless: bool = True) -> Optional[str]:
        """
        完整流程: 登录并获取 FLV URL

        Args:
            desk_id: 桌台ID
            headless: 是否无头模式

        Returns:
            FLV URL 或 None
        """
        self.flv_url = None
        self.flv_url_time = None

        try:
            # 获取登录凭证
            credentials = await self.get_credentials(desk_id)
            if not credentials:
                self.log("未找到登录凭证，请检查数据库配置")
                return None

            username = credentials.get("username")
            password = credentials.get("password")
            desk_url = credentials.get("desk_url")

            self.log(f"使用账号: {username}")

            # 启动浏览器
            if not await self.start_browser(desk_id, headless=headless):
                return None

            # 登录
            if not await self.login(username, password):
                return None

            # 跳转到游戏页面
            if not await self.navigate_to_game(desk_url, desk_id):
                return None

            return self.flv_url

        except Exception as e:
            self.log(f"获取 FLV URL 失败: {e}")
            return None

    async def close(self):
        """关闭浏览器释放资源"""
        if self._page:
            try:
                await self._page.close()
            except:
                pass
        if self._context:
            try:
                await self._context.close()
            except:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except:
                pass

        self._page = None
        self._context = None
        self._playwright = None
        self.log("浏览器资源已释放")

    def get_sign_expire_time(self) -> Optional[datetime]:
        """解析签名过期时间"""
        if not self.flv_url or 'sign=' not in self.flv_url:
            return None
        try:
            match = re.search(r'sign=(\d+)-', self.flv_url)
            if match:
                timestamp = int(match.group(1))
                return datetime.fromtimestamp(timestamp)
        except:
            pass
        return None

    def get_sign_remaining_seconds(self) -> int:
        """获取签名剩余有效秒数"""
        expire_time = self.get_sign_expire_time()
        if expire_time:
            remaining = (expire_time - datetime.now()).total_seconds()
            return max(0, int(remaining))
        return 0
