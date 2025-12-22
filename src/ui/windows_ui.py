# -*- coding: utf-8 -*-
"""
龙虎监控系统 - 主界面

使用拆分的UI组件:
- InfoPanel: 台桌信息统计
- LogPanel: 日志输出
- PreviewPanel: 截图预览
"""
import tkinter as tk
from tkinter import messagebox
import asyncio
import threading
import logging
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright

# 导入核心模块
from core.config import config
from core.roadmap_sync import roadmap_syncer
from api.online_get_xue_pu import get_current_xue_pu, get_caiji_config, get_last_n_results, sync_incremental
from core.process_manager import get_process_manager
from monitor.browser_monitor import BrowserMonitor

# 导入自动登录模块
from auto_login_roadmap import roadmap_login, roadmap_session, roadmap_logout

# 导入UI组件
from ui.info_panel import InfoPanel
from ui.log_panel import LogPanel
from ui.preview_panel import PreviewPanel

logger = logging.getLogger(__name__)

# 全局监控器实例
_browser_monitor_instance = None


def get_browser_monitor(desk_id: int = None):
    """获取浏览器监控器单例"""
    global _browser_monitor_instance
    if _browser_monitor_instance is None:
        _browser_monitor_instance = BrowserMonitor(desk_id=desk_id)
    return _browser_monitor_instance


class MainGUI:
    """主控制界面"""

    def __init__(self, root, desk_id: int = 1, debug_port: int = 9223):
        self.root = root
        self.desk_id = desk_id
        self.debug_port = debug_port

        # 窗口标题显示桌号
        desk_name = config.get_desk_name(desk_id)
        self.root.title(f"龙虎监控 - {desk_name} (端口:{debug_port})")
        self.root.geometry("1280x720")

        # 浏览器相关
        self.playwright = None
        self.browser = None
        self.context = None
        self.current_page = None
        self.browser_opened = False
        self.captured_roadmap_data = None
        self.last_synced_pu = None

        # 浏览器监控模块 (传入desk_id用于信号发送)
        self.browser_monitor: BrowserMonitor = get_browser_monitor(desk_id=desk_id)

        # 自动刷新定时器
        self.auto_refresh_id = None

        # 数据库同步相关
        self.db_sync_count = 0
        self.db_check_count = 0
        self.db_sync_timer_id = None
        self.is_first_db_sync = True
        self.current_local_roadmap = []
        self.current_desk_id = None
        self.sync_countdown_seconds = 0
        self.current_online_pu = 0
        self.current_local_pu = 0
        self.last_countdown = None  # 记录上一次倒计时值，用于检测从1变0

        # 自动登录配置
        self.caiji_config = None
        self._load_caiji_config()

        # 运行时长计时器
        self.roadmap_start_time = None  # 路单采集开始时间
        self.roadmap_duration_timer_id = None

        # FLV推流相关（使用 flv_push 模块）
        self.flv_url = None           # FLV 视频源地址
        self.flv_url_capture = None   # FLV URL 获取器
        self.stream_pusher = None     # FLV 推流器
        self.flv_start_time = None
        self.flv_total_bytes = 0
        self.flv_duration_timer_id = None

        # 登录状态追踪
        self.roadmap_login_success = False  # 路单采集浏览器登录状态
        self.flv_login_success = False      # FLV推流浏览器登录状态
        self.is_logging_in = False          # 是否正在登录中（防止页面导航干扰）

        # 创建界面
        self._create_widgets()

        # 设置回调
        self._setup_monitor_callbacks()
        self._setup_roadmap_syncer()
        self._setup_game_processor_callback()

        # 初始化
        self.log("系统已启动")
        self._check_ai_model()
        self.check_db_connection()

        # 窗口关闭
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 启动后自动开始采集（延迟1秒等待界面完成）
        self.root.after(1000, self.start_capture)

    def _create_widgets(self):
        """创建界面组件"""
        # 标题
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)

        tk.Label(
            title_frame,
            text="龙虎监控系统 v5.1",
            font=("Arial", 18, "bold"),
            fg="white",
            bg="#2c3e50"
        ).pack(pady=15)

        # 主内容区域（左右分栏）
        main_frame = tk.Frame(self.root, bg="#ecf0f1")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左侧区域
        left_frame = tk.Frame(main_frame, bg="#ecf0f1")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 右侧区域 (固定宽度420)
        right_frame = tk.Frame(main_frame, bg="#ecf0f1", width=420)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_frame.pack_propagate(False)

        # === 左侧: 按钮区域 ===
        self._create_buttons(left_frame)

        # === 左侧: 台桌信息面板 ===
        self.info_panel = InfoPanel(left_frame)

        # === 左侧: 日志面板 ===
        self.log_panel = LogPanel(left_frame)

        # === 右侧: 截图预览面板 ===
        self.preview_panel = PreviewPanel(right_frame, log_callback=self.log)

        # === 底部状态栏 ===
        status_frame = tk.Frame(self.root, bg="#34495e", height=25)
        status_frame.pack(fill=tk.X)
        status_frame.pack_propagate(False)

        self.status_label = tk.Label(
            status_frame,
            text="状态: 就绪",
            font=("Arial", 9),
            fg="white",
            bg="#34495e",
            anchor="w"
        )
        self.status_label.pack(fill=tk.X, padx=10)

    def _create_buttons(self, parent):
        """创建按钮区域"""
        button_frame = tk.Frame(parent, bg="#ecf0f1", height=60)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        button_config = {
            "font": ("Arial", 10),
            "width": 14,
            "height": 2,
            "relief": tk.RAISED,
            "bd": 2
        }

        self.btn_start = tk.Button(
            button_frame,
            text="1. 启动采集",
            bg="#3498db",
            fg="white",
            command=self.start_capture,
            **button_config
        )
        self.btn_start.pack(side=tk.LEFT, padx=2)

        self.btn_roadmap = tk.Button(
            button_frame,
            text="2. 同步路单",
            bg="#e67e22",
            fg="white",
            command=self.sync_roadmap,
            **button_config
        )
        self.btn_roadmap.pack(side=tk.LEFT, padx=2)

    # ========== 回调设置 ==========

    def _setup_roadmap_syncer(self):
        """设置路单同步模块回调"""
        roadmap_syncer.on_log = lambda msg: self.root.after(0, lambda m=msg: self.log(m))

        def on_sync_complete(pu_count: int):
            """同步完成回调，pu_count = 已完成的铺数"""
            online_pu = pu_count + 1  # 线上当前进行中的铺号
            self.current_online_pu = online_pu
            self.root.after(0, lambda p=online_pu: self.info_panel.update_online_pu(p, "#9b59b6"))
            self.root.after(0, lambda p=self.current_local_pu: self.info_panel.update_local_pu(p, "#3498db"))

        roadmap_syncer.on_sync_complete = on_sync_complete

        def on_pu_update(new_pu: int):
            """铺号更新回调，new_pu = 当前进行中的铺号"""
            self.current_local_pu = new_pu
            # 同步到browser_monitor，确保post_data使用正确的铺号
            if self.browser_monitor:
                self.browser_monitor.current_pu = new_pu
            self.root.after(0, lambda p=new_pu: self.info_panel.update_round_num(p))
            self.root.after(0, lambda p=new_pu: self.info_panel.update_local_pu(p))

        roadmap_syncer.on_pu_update = on_pu_update

    def _setup_monitor_callbacks(self):
        """设置监控模块回调"""
        # 倒计时
        def on_countdown_change(countdown):
            color = "#e74c3c" if countdown <= 5 else "#2980b9"
            self.root.after(0, lambda: self.info_panel.update_countdown(countdown, color))
            if countdown in [30, 20, 10, 5, 3, 2, 1, 0]:
                self.root.after(0, lambda c=countdown: self.log(f"[倒计时] {c}秒"))

            # 倒计时从1变成0时触发路单同步（只触发一次）
            # 此时上一局已经开完牌，利博API肯定已更新，可以安全同步
            if countdown == 0 and self.last_countdown == 1:
                self.root.after(0, lambda: self.log("[同步] 倒计时1->0，触发路单同步..."))
                self.root.after(500, lambda: self._do_roadmap_sync(source="倒计时"))

            # 记录当前倒计时值，供下次比较
            self.last_countdown = countdown

        self.browser_monitor.on_countdown_change = on_countdown_change

        # 投注状态
        def on_status_change(old_status, new_status):
            if new_status and "投注" in new_status:
                color = "#27ae60"
            elif new_status and ("停止" in new_status or "开牌" in new_status):
                color = "#e74c3c"
            else:
                color = "#f39c12"
            self.root.after(0, lambda: self.info_panel.update_bet_status(new_status or "--", color))
            self.root.after(0, lambda: self.log(f"[状态] {old_status} -> {new_status}"))

        self.browser_monitor.on_status_change = on_status_change

        # 新一局
        def on_new_game(game_number):
            self.root.after(0, lambda: self.info_panel.update_result("--"))
            self.root.after(0, lambda: self.info_panel.update_dragon_card("--"))
            self.root.after(0, lambda: self.info_panel.update_tiger_card("--"))

        self.browser_monitor.on_new_game = on_new_game

        # 铺号/靴号变化
        self.browser_monitor.on_pu_change = lambda pu: self.root.after(0, lambda: (
            self.info_panel.update_round_num(pu),
            self.log(f"[铺号] 当前第{pu}铺")
        ))
        self.browser_monitor.on_xue_change = lambda xue: self.root.after(0, lambda: (
            self.info_panel.update_shoe_num(xue),
            self.log(f"[靴号] 当前第{xue}靴")
        ))

        # 换靴检测回调 - 发送换靴信号
        def on_shoe_change():
            self.root.after(0, lambda: self.log("[换靴] 检测到源站点换靴，发送换靴信号..."))

            # 使用异步任务发送换靴信号
            async def do_add_xue():
                try:
                    from core.config import config
                    from api.online_add_xue import send_add_xue

                    desk_id = config.get("desk_id", 1)
                    result = await send_add_xue(desk_id)

                    if result.success:
                        self.root.after(0, lambda: self.log(f"[换靴] ✓ 换靴信号发送成功"))
                    else:
                        self.root.after(0, lambda: self.log(f"[换靴] ✗ 换靴信号发送失败: {result.error}"))
                except Exception as e:
                    self.root.after(0, lambda: self.log(f"[换靴] ✗ 换靴信号异常: {e}"))

            # 在事件循环中执行
            import threading
            def run_async():
                import asyncio
                asyncio.run(do_add_xue())
            threading.Thread(target=run_async, daemon=True).start()

        self.browser_monitor.on_shoe_change = on_shoe_change

        # HTTP请求
        def on_http_request(info):
            req_type = info.get("type", "")
            url = info.get("url", "")
            if req_type == "response" and "httpapi" in url.lower():
                data = info.get("data", {})
                result = data.get("result", "")
                if result:
                    self.captured_roadmap_data = {
                        'desk': data.get('desk', ''),
                        'game_id': data.get('GameID', ''),
                        'result': result,
                        'raw': str(data)
                    }
                    results = [r for r in result.split('#') if r]
                    self.current_local_roadmap = [{"round": i+1, "result": r} for i, r in enumerate(results)]
                    self.root.after(0, lambda c=len(results): self.log(f"[路单] 捕获{c}局记录"))
                    self.root.after(500, self._process_captured_roadmap)

        self.browser_monitor.on_http_request = on_http_request

        # 开牌截图
        def on_cards_captured(screenshot_path: str, card_data: dict):
            game_number = card_data.get('game_number', '')
            card_crops = card_data.get('card_crops', {})
            print(f"[DEBUG] on_cards_captured 被调用: game={game_number}, screenshot={screenshot_path}, crops={list(card_crops.keys())}")
            self.root.after(0, lambda: self.log(f"[开牌截图] 局号{game_number}, 截图{len(card_crops)}张"))

            if screenshot_path:
                self.root.after(100, lambda: self.preview_panel.update_screenshot(screenshot_path, card_data))

            # 更新AI识别结果到信息面板 (龙虎版本)
            ai_result = card_data.get("ai_result")
            if ai_result:
                result = self.preview_panel.display_ai_result(ai_result)
                if result:
                    result_text, result_color, dragon_str, tiger_str = result
                    self.root.after(0, lambda: self.info_panel.update_dragon_card(dragon_str or "--"))
                    self.root.after(0, lambda: self.info_panel.update_tiger_card(tiger_str or "--"))
                    self.root.after(0, lambda: self.info_panel.update_result(result_text, result_color))
                    self.root.after(0, lambda: self.log(f"[开牌结果] {result_text}"))

        self.browser_monitor.on_cards_captured = on_cards_captured

        # 截图失败
        def on_card_capture_failed(game_number: str):
            self.root.after(0, lambda: self.log(f"[截图失败] 局{game_number} - 自动触发路单同步"))
            self.root.after(0, self._do_db_sync)

        self.browser_monitor.on_card_capture_failed = on_card_capture_failed

    def _setup_game_processor_callback(self):
        """设置game_processor回调"""
        try:
            from core.game_processor import game_processor

            # 日志回调
            game_processor.on_log = lambda msg: self.root.after(0, lambda m=msg: self.log(m))

            # post_data完成后的回调 - 仅记录日志，不再触发同步
            # 同步逻辑已移至倒计时结束时触发，避免时序问题
            def on_upload_complete(success: bool, error: str):
                if success:
                    self.root.after(0, lambda: self.log("[开牌] post_data发送成功"))
                else:
                    self.root.after(0, lambda: self.log(f"[开牌] post_data发送失败: {error}"))

            game_processor.on_upload_complete = on_upload_complete

            self.log("[初始化] game_processor 回调已设置")
        except Exception as e:
            self.log(f"[初始化] game_processor 回调设置失败: {e}")

    # ========== 公共方法 ==========

    def log(self, message: str):
        """输出日志"""
        self.log_panel.log(message)

    def update_status(self, status: str):
        """更新状态栏"""
        self.status_label.config(text=f"状态: {status}")

    def check_browser(self) -> bool:
        """检查浏览器是否打开"""
        if not self.browser_opened or not self.current_page:
            self.log("[错误] 请先打开浏览器并进入游戏页面")
            return False
        return True

    def run_async(self, coro, keep_running: bool = False):
        """
        在后台线程运行异步任务

        Args:
            coro: 要运行的协程
            keep_running: 如果为True，协程完成后事件循环继续运行（支持后台任务如监控循环）
        """
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(coro)
                if keep_running:
                    # 协程完成后，继续运行事件循环以支持后台任务（如监控循环）
                    # 这允许通过 asyncio.create_task() 创建的任务继续运行
                    loop.run_forever()
            except Exception as e:
                self.root.after(0, lambda: self.log(f"[异步错误] {e}"))
            finally:
                try:
                    # 取消所有待处理的任务
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    # 等待任务被取消
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except:
                    pass
                loop.close()

        threading.Thread(target=run, daemon=True).start()

    # ========== 初始化检测 ==========

    def _check_ai_model(self):
        """检测AI模型"""
        try:
            # models 在项目根目录 (src 的上一级)
            model_path = Path(__file__).parent.parent.parent / "models" / "best_resnet101_model.pth"
            if model_path.exists():
                self.log(f"[AI] 模型文件已找到: {model_path.name}")
                try:
                    from ai.recognizer import CardAIRecognizer
                    recognizer = CardAIRecognizer(str(model_path))
                    self.log(f"[AI] 模型加载成功, 设备: {recognizer.recognizer.device}")
                except Exception as e:
                    self.log(f"[AI] 模型加载失败: {e}")
            else:
                self.log(f"[AI] 警告: 模型文件不存在")
        except Exception as e:
            self.log(f"[AI] 检测失败: {e}")

    def check_db_connection(self):
        """检测后端API连接"""
        def check_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response = loop.run_until_complete(get_current_xue_pu(self.desk_id))
                loop.close()

                api_url = config.get("backend_api.base_url", "unknown")

                if response.success:
                    self.info_panel.update_db_status(True, "API", api_url)
                    self.log(f"[后端API] 连接成功: {api_url}")
                else:
                    self.info_panel.update_db_status(False)
                    self.log(f"[后端API] 连接失败: {response.error}")
            except Exception as e:
                self.info_panel.update_db_status(False)
                self.log(f"[后端API] 连接异常: {e}")

        threading.Thread(target=check_task, daemon=True).start()

    def _load_caiji_config(self):
        """加载采集配置 - 通过API获取"""
        def load_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response = loop.run_until_complete(get_caiji_config(self.desk_id))
                loop.close()

                if response.success and response.data:
                    self.caiji_config = response.data
                    roadmap_user = self.caiji_config.get("caiji_username", "")
                    flv_user = self.caiji_config.get("caiji_flv_username", "")
                    desk_url = self.caiji_config.get("caiji_desk_url", "")
                    logger.info(f"[采集配置] 桌{self.desk_id}: roadmap={roadmap_user}, flv={flv_user}, url={desk_url[:50] if desk_url else 'N/A'}...")
                else:
                    logger.warning(f"[采集配置] 桌{self.desk_id}: 获取失败({response.error})，将使用手动登录")
                    self.caiji_config = None
            except Exception as e:
                logger.error(f"[采集配置] 加载失败: {e}")
                self.caiji_config = None

        threading.Thread(target=load_task, daemon=True).start()

    # ========== 采集操作 ==========

    def start_capture(self):
        """启动采集 - 同时启动路单采集和FLV推流两个浏览器"""
        if self.browser_opened:
            self.log("[采集] 已在运行，无需重复操作")
            return

        self.log("[系统] 正在启动...")
        self.log("[系统] 步骤1: 登录FLV推流浏览器（获取推流地址）")
        self.log("[系统] 步骤2: 登录路单采集浏览器（保持在线）")
        self.log("[系统] 步骤3: 两个都成功后开始工作")
        self.btn_start.config(state=tk.DISABLED)

        # 重置登录状态
        self.roadmap_login_success = False
        self.flv_login_success = False

        # 更新状态显示，同时显示两个账号
        if self.caiji_config:
            roadmap_username = self.caiji_config.get("caiji_username", "")
            # FLV账号：使用独立的FLV采集账号
            flv_username = self.caiji_config.get("caiji_flv_username", "") or roadmap_username

            self.info_panel.update_roadmap_status("登录中", "#e67e22")
            self.info_panel.update_roadmap_user(roadmap_username)
            self.info_panel.update_flv_status("登录中", "#e67e22")
            self.info_panel.update_flv_user(flv_username)

            self.log(f"[账号] 路单采集: {roadmap_username}")
            self.log(f"[账号] FLV推流: {flv_username}")

        # 同时启动两个浏览器的登录
        # keep_running=True 确保事件循环在登录完成后继续运行，支持监控循环
        self.run_async(self._start_both_browsers(), keep_running=True)

    async def _start_both_browsers(self):
        """
        按顺序启动FLV推流和路单采集两个浏览器的登录

        登录顺序调整说明：
        1. 先登录FLV账号 - 只需要获取FLV URL，获取完后浏览器可以关闭
        2. 再登录路单账号 - 需要一直保持在线监控

        这样可以避免两个账号的session冲突
        """
        if not self.caiji_config:
            self.root.after(0, lambda: self.log("[错误] 未配置采集账号！"))
            self.root.after(0, lambda: self.log("[提示] 请在数据库中配置桌台采集账号后重新启动"))
            self.root.after(0, lambda: self.update_status("错误：未配置采集账号"))
            self.root.after(0, lambda: self.btn_start.config(text="1. 配置错误", bg="#e74c3c", state=tk.NORMAL))
            self.root.after(0, lambda: self.info_panel.update_roadmap_status("无账号", "#e74c3c"))
            self.root.after(0, lambda: self.info_panel.update_flv_status("无账号", "#e74c3c"))
            return

        # 标记登录中，防止页面导航干扰
        self.is_logging_in = True

        try:
            # ===== 步骤1: 登录FLV推流浏览器（先登录，获取URL后关闭浏览器）=====
            self.log("[步骤1] >>>>>> 开始登录FLV推流浏览器...")
            self.flv_login_success = await self._login_flv_browser()
            self.log(f"[步骤1] FLV登录结果: {self.flv_login_success}")

            if not self.flv_login_success:
                # FLV登录失败，30秒后完全重启
                self.log("[步骤1] ✗ FLV登录失败，30秒后重启")
                self.root.after(0, lambda: self.update_status("FLV登录失败，30秒后重启..."))
                self.root.after(0, lambda: self.btn_start.config(text="1. 等待重启", bg="#e67e22", state=tk.NORMAL))
                self.root.after(30000, lambda: self._restart_all())
                return

            self.log("[步骤1] ✓ FLV登录成功，已获取推流地址")

            # FLV获取成功后立即启动推流（不等路单登录）
            flv_url = getattr(self, 'flv_url', None)
            if flv_url:
                self.log("[FLV] 立即启动推流...")
                self.root.after(0, lambda: self.info_panel.update_flv_status("推流中", "#27ae60"))
                self.root.after(0, lambda u=flv_url: self._start_flv_push(u))
            else:
                self.log("[FLV] 警告: 无FLV URL")

            # ===== 步骤2: 登录路单采集浏览器（后登录，一直保持在线）=====
            self.log("[步骤2] >>>>>> 开始登录路单采集浏览器...")
            self.roadmap_login_success = await self._login_roadmap_browser()
            self.log(f"[步骤2] 路单登录结果: {self.roadmap_login_success}")

            if not self.roadmap_login_success:
                # 路单登录失败，但FLV推流继续运行，只重试路单登录
                self.log("[步骤2] ✗ 路单登录失败，FLV推流继续，30秒后重试路单")
                self.root.after(0, lambda: self.update_status("路单登录失败，FLV继续推流..."))
                self.root.after(0, lambda: self.info_panel.update_roadmap_status("登录失败", "#e74c3c"))
                self.root.after(0, lambda: self.btn_start.config(text="1. 路单重试中", bg="#e67e22", state=tk.NORMAL))
                # 只重试路单登录，不影响FLV推流
                self.root.after(30000, lambda: self._retry_roadmap_login())
                return

            self.log("[步骤2] ✓ 路单登录成功")

            # ===== 步骤3: 两个都成功，开始工作 =====
            self.log("[步骤3] ✓ 两个浏览器都登录成功！开始工作...")

            # 登录流程结束，取消标记（在调用 _on_both_login_success 之前）
            self.is_logging_in = False

            # 直接调用成功回调（使用 root.after 确保在主线程执行）
            def call_success_callback():
                try:
                    self._on_both_login_success()
                except Exception as e:
                    self.log(f"[错误] _on_both_login_success 执行失败: {e}")
                    import traceback
                    traceback.print_exc()

            self.root.after(100, call_success_callback)
            return  # 成功时直接返回，不再执行 finally

        except Exception as e:
            # 捕获未预期的异常
            self.root.after(0, lambda err=str(e): self.log(f"[系统错误] 启动过程异常: {err}"))
            self.root.after(0, lambda: self.update_status("启动异常"))
            self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
            import traceback
            traceback.print_exc()
        finally:
            # 登录流程结束，取消标记
            self.is_logging_in = False

    async def _login_roadmap_browser(self) -> bool:
        """登录路单采集浏览器"""
        self.root.after(0, lambda: self.log("[路单] ========== 开始登录 =========="))

        try:
            # 启动浏览器并登录
            self.root.after(0, lambda: self.log("[路单] 调用 _open_browser_async..."))
            await self._open_browser_async()

            # 检查登录结果
            self.root.after(0, lambda: self.log(f"[路单] 检查: browser_opened={self.browser_opened}, page={self.current_page is not None}"))

            if self.browser_opened and self.current_page:
                self.root.after(0, lambda: self.log("[路单] ✓ 登录成功!"))
                self.root.after(0, lambda: self.info_panel.update_roadmap_status("已登录", "#27ae60"))
                return True
            else:
                self.root.after(0, lambda: self.log("[路单] ✗ 登录失败 (browser_opened 或 current_page 为空)"))
                self.root.after(0, lambda: self.info_panel.update_roadmap_status("登录失败", "#e74c3c"))
                return False
        except Exception as e:
            self.root.after(0, lambda err=str(e): self.log(f"[路单] 登录异常: {err}"))
            self.root.after(0, lambda: self.info_panel.update_roadmap_status("异常", "#e74c3c"))
            import traceback
            traceback.print_exc()
            return False

    async def _login_flv_browser(self) -> bool:
        """
        获取FLV推流地址

        流程（参考 test_flv_capture.py）：
        1. 启动浏览器登录获取 FLV URL
        2. 获取成功后立即关闭浏览器
        3. 后续用 requests + FFmpeg 推流
        """
        self.root.after(0, lambda: self.log("[FLV] ========== 开始获取FLV地址 =========="))

        try:
            from flv_push import FLVUrlCapture

            self.flv_url_capture = FLVUrlCapture(self.desk_id)

            # 设置日志回调
            def flv_log_callback(msg):
                self.root.after(0, lambda m=msg: self.log(f"[FLV] {m}"))
            self.flv_url_capture.on_log = flv_log_callback

            # 获取账号并显示
            self.root.after(0, lambda: self.log("[FLV] 获取登录凭证..."))
            credentials = await self.flv_url_capture.get_credentials()
            if credentials:
                flv_username = credentials.get("username", "")
                self.root.after(0, lambda u=flv_username: self.log(f"[FLV] 使用账号: {u}"))
                self.root.after(0, lambda u=flv_username: self.info_panel.update_flv_user(u))
            else:
                self.root.after(0, lambda: self.log("[FLV] ✗ 未配置FLV账号"))
                self.root.after(0, lambda: self.info_panel.update_flv_status("无账号", "#e74c3c"))
                return False

            # 获取FLV URL (会执行登录流程)
            self.root.after(0, lambda: self.log("[FLV] 启动浏览器获取FLV地址..."))
            self.root.after(0, lambda: self.info_panel.update_flv_status("获取中", "#e67e22"))

            flv_url = await self.flv_url_capture.get_flv_url(headless=True)

            if flv_url:
                self.flv_url = flv_url  # 保存 URL 供后续推流使用
                self.root.after(0, lambda: self.log(f"[FLV] ✓ FLV地址获取成功!"))
                self.root.after(0, lambda u=flv_url[:60]: self.log(f"[FLV] URL: {u}..."))
                self.root.after(0, lambda: self.info_panel.update_flv_status("已获取", "#27ae60"))

                # 关闭浏览器，释放资源
                self.root.after(0, lambda: self.log("[FLV] 关闭浏览器，准备推流..."))
                await self.flv_url_capture.close()
                await asyncio.sleep(0.5)

                return True
            else:
                self.root.after(0, lambda: self.log("[FLV] ✗ FLV地址获取失败"))
                self.root.after(0, lambda: self.info_panel.update_flv_status("获取失败", "#e74c3c"))
                # 清理
                if self.flv_url_capture:
                    await self.flv_url_capture.close()
                    self.flv_url_capture = None
                return False

        except Exception as e:
            self.root.after(0, lambda err=str(e): self.log(f"[FLV] 获取异常: {err}"))
            self.root.after(0, lambda: self.info_panel.update_flv_status("异常", "#e74c3c"))
            import traceback
            traceback.print_exc()
            if hasattr(self, 'flv_url_capture') and self.flv_url_capture:
                try:
                    await self.flv_url_capture.close()
                except:
                    pass
                self.flv_url_capture = None
            return False

    def _restart_all(self):
        """
        完全重启所有登录流程

        当任何一个登录失败时，清理所有资源并重新开始
        """
        self.log("[重启] 开始完全重启...")

        # 重置登录状态
        self.roadmap_login_success = False
        self.flv_login_success = False
        self.browser_opened = False

        # 停止 FLV 推流
        self._stop_flv_push()

        # 清理 FLV URL 获取器
        if self.flv_url_capture:
            self.log("[重启] 清理FLV资源...")
            self.run_async(self._cleanup_flv_async())

        # 清理路单浏览器资源
        if self.context or self.current_page:
            self.log("[重启] 清理路单浏览器资源...")
            self.run_async(self._cleanup_roadmap_browser_async())

        # 停止定时器
        self._stop_auto_refresh()
        self._stop_db_sync_timer()
        self._stop_roadmap_duration_timer()
        self._stop_flv_duration_timer()

        # 停止session监控
        roadmap_session.stop_session_monitor()
        roadmap_session.stop_login_retry_loop()

        # 重置UI状态
        self.info_panel.update_roadmap_status("等待重启", "#e67e22")
        self.info_panel.update_flv_status("等待重启", "#e67e22")
        self.btn_start.config(text="1. 重启中...", bg="#e67e22", state=tk.DISABLED)

        # 延迟2秒后重新启动（等待资源清理完成）
        self.root.after(2000, self._do_restart)

    def _do_restart(self):
        """执行重启"""
        self.log("[重启] 重新启动采集...")
        self.btn_start.config(state=tk.NORMAL)
        self.start_capture()

    async def _cleanup_flv_async(self):
        """异步清理FLV资源"""
        try:
            if self.flv_url_capture:
                await self.flv_url_capture.close()
        except Exception as e:
            logger.warning(f"[清理] FLV资源清理出错: {e}")
        finally:
            self.flv_url_capture = None
            self.flv_url = None

    async def _cleanup_roadmap_browser_async(self):
        """异步清理路单浏览器资源"""
        try:
            if self.current_page and not self.current_page.is_closed():
                await self.current_page.close()
            if self.context:
                await self.context.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.warning(f"[清理] 路单浏览器资源清理出错: {e}")
        finally:
            self.current_page = None
            self.context = None
            self.browser = None
            self.playwright = None

    def _retry_roadmap_login(self):
        """重试路单登录（不影响FLV推流）"""
        self.log("[路单] 开始重试登录...")
        self.info_panel.update_roadmap_status("重试中", "#e67e22")
        self.run_async(self._do_retry_roadmap_login())

    async def _do_retry_roadmap_login(self):
        """异步重试路单登录"""
        try:
            # 清理之前的浏览器资源
            await self._cleanup_roadmap_browser_async()

            # 重新登录
            self.roadmap_login_success = await self._login_roadmap_browser()

            if self.roadmap_login_success:
                self.log("[路单] 重试登录成功!")
                # 调用成功回调
                self.root.after(100, self._on_both_login_success)
            else:
                self.log("[路单] 重试登录失败，30秒后再次重试")
                self.root.after(0, lambda: self.info_panel.update_roadmap_status("登录失败", "#e74c3c"))
                self.root.after(30000, lambda: self._retry_roadmap_login())

        except Exception as e:
            self.root.after(0, lambda err=str(e): self.log(f"[路单] 重试异常: {err}"))
            self.root.after(30000, lambda: self._retry_roadmap_login())

    def _on_both_login_success(self):
        """两个浏览器都登录成功后的回调"""
        self.log("[系统] _on_both_login_success 被调用!")

        try:
            # 更新UI状态
            self.log("[系统] 更新UI状态为运行中...")
            self.info_panel.update_roadmap_status("运行中", "#27ae60")
            self.btn_start.config(text="1. 采集运行中", bg="#27ae60", state=tk.NORMAL)
            self.update_status("系统正常运行中")

            # 主动获取并更新台桌ID（因为登录过程中页面导航事件被忽略）
            self._update_desk_id_from_page()

            # 启动运行时长计时器
            self.log("[系统] 启动运行时长计时器...")
            self._start_roadmap_duration_timer()

            # FLV推流已在步骤1后立即启动，这里只检查状态
            if self.stream_pusher:
                self.log("[FLV] 推流已在运行中")
            else:
                # 如果推流器不存在，尝试启动
                flv_url = getattr(self, 'flv_url', None)
                if flv_url:
                    self.log("[FLV] 启动推流...")
                    self.info_panel.update_flv_status("推流中", "#27ae60")
                    self._start_flv_push(flv_url)
                else:
                    self.log("[FLV] 跳过推流 (无FLV URL)")
                    self.info_panel.update_flv_status("无URL", "#e74c3c")

            # 启动自动刷新
            self.log("[系统] 启动自动刷新...")
            self._start_auto_refresh()

            # 启动 session 监控（两个浏览器都成功后才启动）
            self.log("[Session监控] 启动自动重登功能")
            self.run_async(self._start_session_monitor())

            self.log("[系统] _on_both_login_success 完成!")

        except Exception as e:
            self.log(f"[系统错误] _on_both_login_success 内部异常: {e}")
            import traceback
            traceback.print_exc()

    def _update_desk_id_from_page(self):
        """从当前页面URL获取并更新台桌ID"""
        try:
            if not self.current_page:
                return

            url = self.current_page.url
            if not url:
                return

            import re
            match = re.search(r'desk=(\d+)', url)
            if match:
                desk_id = match.group(1)
                self.info_panel.update_desk_id(desk_id)
                self.current_desk_id = desk_id
                self.log(f"[台桌] 当前桌号: {desk_id}")

                # 首次同步路单 (取消定时同步，改为post_data后检测)
                self.root.after(1000, lambda d=desk_id: self._do_roadmap_sync(d, "登录成功"))
                # 不再启动定时同步: self.root.after(3000, self._start_db_sync_timer)
            else:
                self.log(f"[台桌] 未能从URL提取桌号: {url[:60]}...")

        except Exception as e:
            self.log(f"[台桌] 获取桌号失败: {e}")

    async def _open_browser_async(self):
        """异步打开浏览器"""
        try:
            # 使用实例专属的浏览器数据目录
            user_data_dir = config.instance_browser_data_dir
            user_data_dir.mkdir(parents=True, exist_ok=True)

            # 启动 Playwright
            self.playwright = await async_playwright().start()

            self.root.after(0, lambda: self.log(f"启动 Chromium (端口:{self.debug_port})..."))

            # 从配置获取视口大小和无头模式设置
            viewport_width = config.get("browser.viewport.width", 1280)
            viewport_height = config.get("browser.viewport.height", 720)
            headless_mode = config.get("browser.roadmap_headless", False)  # 路单采集浏览器，默认显示

            # 使用 launch_persistent_context 保持用户数据
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=headless_mode,
                viewport={"width": viewport_width, "height": viewport_height},
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                    f"--window-size={viewport_width},{viewport_height}",
                    f"--remote-debugging-port={self.debug_port}",
                ]
            )

            self.browser_opened = True

            # 记录浏览器进程 PID 到进程管理器
            self._record_browser_pid()

            # 监听浏览器关闭事件
            self.context.on("close", lambda: self._on_browser_closed())

            # 获取或创建页面
            if self.context.pages:
                self.current_page = self.context.pages[0]
            else:
                self.current_page = await self.context.new_page()

            # 设置网络请求监听
            await self._setup_network_listener(self.current_page)

            # 监听页面导航事件 (使用lambda包装)
            self.current_page.on("framenavigated", lambda frame: self._on_page_navigated(frame))

            # ========== 自动登录流程 ==========
            if self.caiji_config:
                # 有采集配置，执行自动登录
                username = self.caiji_config.get("caiji_username", "")
                password = self.caiji_config.get("caiji_password", "")
                target_url = self.caiji_config.get("caiji_desk_url", "")

                self.root.after(0, lambda: self.log(f"[自动登录] 账号: {username}"))
                self.root.after(0, lambda: self.log(f"[自动登录] 目标: {target_url[:60]}..." if target_url else "[自动登录] 目标: 默认"))

                # 设置日志回调
                roadmap_login.on_log = lambda msg: self.root.after(0, lambda m=msg: self.log(m))

                # 执行自动登录
                login_result = await roadmap_login.ensure_logged_in(
                    page=self.current_page,
                    username=username,
                    password=password,
                    target_url=target_url
                )

                if login_result.get("success"):
                    self.root.after(0, lambda: self.log("[路单] 登录成功!"))

                    # 保存登录凭证，用于 session 过期后自动重新登录
                    roadmap_session.save_credentials(username, password, target_url)

                    # 注意：session 监控在 _on_both_login_success 中启动，确保两个浏览器都成功后才监控

                    # 登录成功，返回（不再在这里启动计时器和FLV推流）
                    return
                else:
                    error_msg = login_result.get("message", "未知错误")
                    self.root.after(0, lambda: self.log(f"[路单] 登录失败: {error_msg}"))
                    # 登录失败，标记状态
                    self.browser_opened = False
                    return
            else:
                # 没有采集配置
                self.root.after(0, lambda: self.log("[路单] 未配置采集账号"))
                self.browser_opened = False
                return

        except Exception as e:
            self.root.after(0, lambda err=str(e): self.log(f"[错误] 启动浏览器失败: {err}"))
            self.root.after(0, lambda: self.update_status("启动失败"))
            self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
            self.browser_opened = False

    def _record_browser_pid(self):
        """记录浏览器进程 PID"""
        try:
            # 从 context 获取浏览器进程
            # Playwright 的 context 有一个 browser 属性可以获取进程信息
            import psutil

            # 通过调试端口找到 Chrome 进程
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline') or []
                    cmdline_str = ' '.join(cmdline)
                    # 查找带有我们调试端口的 Chrome 进程
                    if f'--remote-debugging-port={self.debug_port}' in cmdline_str:
                        browser_pid = proc.info['pid']
                        # 记录到进程管理器
                        pm = get_process_manager()
                        if pm:
                            pm.record_browser_pid(browser_pid)
                            self.root.after(0, lambda p=browser_pid: self.log(f"[进程管理] 浏览器PID: {p}"))
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.warning(f"[进程管理] 记录浏览器PID失败: {e}")

    def _on_browser_closed(self):
        """浏览器关闭回调"""
        self.browser_opened = False
        self.context = None
        self.playwright = None

        # 停止自动刷新
        self._stop_auto_refresh()

        # 停止 session 监控
        roadmap_session.stop_session_monitor()

        # 停止登录重试循环
        roadmap_session.stop_login_retry_loop()

        # 清除浏览器 PID 记录
        pm = get_process_manager()
        if pm:
            pm.clear_browser_pid()

        self.root.after(0, lambda: self.log("[浏览器] 已关闭"))
        self.root.after(0, lambda: self.btn_start.config(
            text="1. 打开浏览器",
            bg="#3498db",
            state=tk.NORMAL
        ))
        self.root.after(0, lambda: self.update_status("浏览器已关闭"))

    async def _start_login_retry_loop(self, username: str, password: str, target_url: str = None):
        """启动登录失败重试循环（10分钟间隔）"""
        if not self.current_page:
            return

        def on_retry_start(attempt: int, max_attempts: int):
            """重试开始回调"""
            msg = f"第 {attempt} 次重试" + (f" / {max_attempts}" if max_attempts > 0 else "")
            self.root.after(0, lambda: self.log(f"[登录重试] {msg}"))

        def on_retry_countdown(remaining: int):
            """倒计时回调（每分钟更新一次）"""
            minutes = remaining // 60
            self.root.after(0, lambda m=minutes: self.update_status(f"账号被占用，{m}分钟后重试"))
            self.root.after(0, lambda m=minutes: self.btn_start.config(
                text=f"1. {m}分钟后重试"
            ))

        def on_login_success():
            """登录成功回调"""
            self.root.after(0, lambda: self.log("[登录重试] ✓ 登录成功!"))
            self.root.after(0, lambda: self.update_status("已登录并进入游戏页面"))
            self.root.after(0, lambda: self.btn_start.config(
                text="1. 已自动登录",
                bg="#27ae60"
            ))

            # 保存登录凭证，用于 session 过期后自动重新登录
            roadmap_session.save_credentials(username, password, target_url)

            # 启动 session 监控
            self.root.after(0, lambda: self.log("[Session监控] 启动自动重登功能"))
            asyncio.create_task(self._start_session_monitor())

        def on_login_failed(error_msg: str):
            """登录失败回调"""
            self.root.after(0, lambda m=error_msg: self.log(f"[登录重试] ✗ 最终失败: {m}"))
            self.root.after(0, lambda: self.log("[提示] 请手动登录"))
            self.root.after(0, lambda: self.update_status("登录失败，请手动登录"))
            self.root.after(0, lambda: self.btn_start.config(
                text="1. 浏览器已打开",
                bg="#e74c3c"
            ))

        # 启动重试循环（10分钟间隔，无限重试）
        await roadmap_session.start_login_retry_loop(
            page=self.current_page,
            username=username,
            password=password,
            target_url=target_url,
            retry_interval=10 * 60,  # 10分钟
            max_attempts=0,  # 无限重试
            on_retry_start=on_retry_start,
            on_retry_countdown=on_retry_countdown,
            on_login_success=on_login_success,
            on_login_failed=on_login_failed
        )

    async def _start_session_monitor(self):
        """启动 session 过期监控"""
        if not self.current_page:
            return

        def on_session_expired():
            """session 过期回调"""
            self.root.after(0, lambda: self.log("[Session监控] ⚠️ 检测到被踢出，正在重新登录..."))
            self.root.after(0, lambda: self.update_status("Session过期，正在重新登录..."))
            self.root.after(0, lambda: self.btn_start.config(
                text="1. 重新登录中...",
                bg="#e67e22"
            ))

        def on_relogin_success():
            """重新登录成功回调"""
            self.root.after(0, lambda: self.log("[Session监控] ✓ 重新登录成功!"))
            self.root.after(0, lambda: self.update_status("已重新登录"))
            self.root.after(0, lambda: self.btn_start.config(
                text="1. 已自动登录",
                bg="#27ae60"
            ))

        def on_relogin_failed(error_msg: str):
            """重新登录失败回调"""
            self.root.after(0, lambda m=error_msg: self.log(f"[Session监控] ✗ 重新登录失败: {m}"))
            self.root.after(0, lambda: self.log("[提示] 请手动登录"))
            self.root.after(0, lambda: self.update_status("重新登录失败，请手动登录"))
            self.root.after(0, lambda: self.btn_start.config(
                text="1. 浏览器已打开",
                bg="#e74c3c"
            ))

        # 定义重新登录函数
        async def relogin_func():
            """重新登录函数"""
            if not self.caiji_config:
                return {"success": False, "message": "无登录配置"}
            username = self.caiji_config.get("caiji_username", "")
            password = self.caiji_config.get("caiji_password", "")
            target_url = self.caiji_config.get("caiji_desk_url", "")
            return await roadmap_login.login(
                page=self.current_page,
                username=username,
                password=password,
                target_url=target_url
            )

        # 启动监控（每30秒检查一次）
        await roadmap_session.start_session_monitor(
            page=self.current_page,
            login_func=relogin_func,
            check_interval=30,
            on_session_expired=on_session_expired,
            on_relogin_success=on_relogin_success,
            on_relogin_failed=on_relogin_failed
        )

    async def _setup_network_listener(self, page):
        """
        设置网络监听和DOM监控

        使用 BrowserMonitor 模块 (合并HTTP和DOM监控):
        - 监听浏览器URL、Cookie、LocalStorage
        - 监听所有HTTP请求/响应、WebSocket
        - 监听DOM变化: 倒计时、投注状态、台桌信息、开牌
        - 日志按 table_时间 命名，保留20分钟
        """
        # 启动浏览器监控 (与原版一致)
        await self.browser_monitor.start(self.context, page)

        # 显示日志路径
        log_dir = self.browser_monitor.log_dir
        self.root.after(0, lambda d=str(log_dir): self.log(f"[监控] 日志目录: {d}"))
        self.root.after(0, lambda: self.log("[监控] 监控内容:"))
        self.root.after(0, lambda: self.log("  - URL/Cookie/Storage"))
        self.root.after(0, lambda: self.log("  - HTTP请求/WebSocket"))
        self.root.after(0, lambda: self.log("  - DOM变化(倒计时/状态/台桌)"))
        self.root.after(0, lambda: self.log(f"[监控] 日志保留: {self.browser_monitor.retention_minutes}分钟"))

    def _on_page_navigated(self, frame):
        """页面导航时的回调 - 进入游戏页面时自动同步FLV和路单"""
        try:
            # 登录中不处理页面导航，避免干扰登录流程
            if self.is_logging_in:
                return

            # 只处理主frame的导航（忽略iframe）
            if frame != self.current_page.main_frame:
                return

            url = frame.url
            is_login = "/login" in url or "/select-server-line" in url
            is_game = "game" in url or "desk=" in url

            # 检测是否需要跳回游戏页面（不在目标URL且不是登录页面）
            if not is_login and self.caiji_config:
                target_url = self.caiji_config.get("caiji_desk_url", "")
                if target_url and not self._is_at_target_url(url, target_url):
                    # 不在目标游戏页面，自动跳回
                    self._handle_lobby_redirect(url, target_url)
                    return

            # 检测游戏页面 (与原版一致的简单逻辑)
            if is_game:
                self.log(f"[导航] 进入游戏页面: {url}")

                # 提取desk_id
                import re
                match = re.search(r'desk=(\d+)', url)
                if match:
                    desk_id = match.group(1)
                    self.root.after(0, lambda d=desk_id: self.info_panel.update_desk_id(d))
                    self.log(f"[台桌] 当前桌号: {desk_id}")

                    # 更新当前桌号
                    old_desk_id = self.current_desk_id
                    self.current_desk_id = desk_id

                    # 如果切换了桌台，重置同步状态
                    if old_desk_id != desk_id:
                        self.is_first_db_sync = True
                        self.current_local_roadmap = []
                        self.db_sync_count = 0
                        self.log(f"[台桌] 切换到桌{desk_id}，准备全量同步")
                    else:
                        # 刷新同一页面，也需要重新同步
                        self.log(f"[台桌] 页面刷新，重新同步数据")

                    # 重置同步标记
                    self.last_synced_pu = None

                    # 进入游戏页面时自动同步路单 (延迟1秒等待页面稳定)
                    self.root.after(1000, lambda d=desk_id: self._do_roadmap_sync(d, "进入/刷新页面"))
                    # 不再启动定时同步: self.root.after(3000, self._start_db_sync_timer)

                    # 更新路单采集状态为运行中，启动计时器
                    if not self.roadmap_start_time:
                        self.root.after(0, lambda: self.info_panel.update_roadmap_status("运行中", "#27ae60"))
                        self.root.after(0, self._start_roadmap_duration_timer)

                    # 启动FLV推流 (如果尚未启动)
                    if self.stream_pusher is None and self.flv_url:
                        self.root.after(3000, lambda: self._start_flv_push(self.flv_url))
        except Exception as e:
            self.root.after(0, lambda err=str(e): self.log(f"[导航错误] {err}"))

    def _is_at_target_url(self, current_url: str, target_url: str) -> bool:
        """
        检测当前URL是否是目标游戏页面

        比较关键参数: desk= 是否一致
        """
        if not current_url or not target_url:
            return False

        # 提取两个URL中的desk参数
        import re
        current_desk = re.search(r'desk=(\d+)', current_url)
        target_desk = re.search(r'desk=(\d+)', target_url)

        if current_desk and target_desk:
            # 两个URL都有desk参数，比较是否一致
            return current_desk.group(1) == target_desk.group(1)

        # 如果目标URL包含game且当前URL也包含相同的game路径
        if "/game" in target_url and "/game" in current_url:
            return True

        return False

    def _handle_lobby_redirect(self, current_url: str, target_url: str = None):
        """处理跳转到非目标页面的情况 - 自动跳回游戏页面"""
        self.log(f"[导航] 检测到离开游戏页面: {current_url}")

        # 如果没有传入target_url，尝试从配置获取
        if not target_url and self.caiji_config:
            target_url = self.caiji_config.get("caiji_desk_url", "")

        if target_url:
            self.log(f"[导航] 自动跳回游戏页面...")
            self.root.after(0, lambda: self.update_status("检测到离开游戏，正在跳回..."))

            # 延迟1秒后跳转，避免页面还没稳定
            self.root.after(1000, lambda t=target_url: self._navigate_to_game(t))
        else:
            self.log("[导航] 无法跳回: 未配置目标游戏页面")

    def _navigate_to_game(self, target_url: str):
        """导航到游戏页面"""
        if self.current_page and self.browser_opened:
            async def do_navigate():
                try:
                    await self.current_page.goto(target_url, wait_until="networkidle")
                    self.root.after(0, lambda: self.log("[导航] 已跳回游戏页面"))
                    self.root.after(0, lambda: self.update_status("已跳回游戏页面"))
                except Exception as e:
                    self.root.after(0, lambda err=str(e): self.log(f"[导航] 跳转失败: {err}"))

            self.run_async(do_navigate())

    # ========== 同步相关 ==========

    def _do_roadmap_sync(self, desk_id: str = None, source: str = "手动"):
        """
        执行路单同步 - 统一入口 (与原版一致)

        调用场景：
        1. 进入游戏页面时 (source="进入页面")
        2. 点击"3. 同步路单"按钮 (source="按钮")
        3. 检测到铺号不一致时 (source="检测")
        """
        # 获取桌号
        if not desk_id:
            desk_id = self.current_desk_id
        if not desk_id:
            self.log(f"[同步] 跳过: 无桌号 (来源: {source})")
            return

        # 更新同步次数
        self.db_sync_count += 1
        sync_num = self.db_sync_count
        self.root.after(0, lambda n=sync_num: self.info_panel.update_sync_count(n))

        self.log(f"[同步 #{sync_num}] 开始 (来源: {source}, 桌号: {desk_id})")

        def sync_task():
            try:
                # 从 browser_monitor 获取凭证 (与原版一致)
                if hasattr(self, 'browser_monitor') and self.browser_monitor:
                    session_id = getattr(self.browser_monitor, 'cached_session_id', '')
                    username = getattr(self.browser_monitor, 'cached_username', '')
                    roadmap_syncer.set_credentials(session_id, username)

                # 执行同步
                result = roadmap_syncer.sync(desk_id)

                if result["success"]:
                    self.root.after(0, lambda c=result["inserted_count"]: self.log(
                        f"[同步 #{sync_num}] 完成: 写入 {c} 条"
                    ))
                else:
                    error = result.get("error", "未知错误")
                    self.root.after(0, lambda e=error: self.log(
                        f"[同步 #{sync_num}] 失败: {e}"
                    ))

            except Exception as e:
                self.root.after(0, lambda err=str(e): self.log(
                    f"[同步 #{sync_num}] 异常: {err}"
                ))

        # 在后台线程执行
        thread = threading.Thread(target=sync_task, daemon=True)
        thread.start()

    def _start_db_sync_timer(self):
        """启动定时同步"""
        if self.db_sync_timer_id:
            self.root.after_cancel(self.db_sync_timer_id)

        sync_interval = config.get("monitor.intervals.sync_check", 60)
        self.sync_countdown_seconds = sync_interval

        self.info_panel.update_sync_status("运行中", "#27ae60")
        self.info_panel.update_sync_countdown(sync_interval)

        def sync_timer():
            self.sync_countdown_seconds -= 1
            self.info_panel.update_sync_countdown(self.sync_countdown_seconds)

            if self.sync_countdown_seconds <= 0:
                self._do_db_check_and_sync()
                self.sync_countdown_seconds = sync_interval

            self.db_sync_timer_id = self.root.after(1000, sync_timer)

        self.db_sync_timer_id = self.root.after(1000, sync_timer)
        self.log(f"[同步] 定时同步已启动 (间隔: {sync_interval}秒)")

    def _stop_db_sync_timer(self):
        """停止定时同步"""
        if self.db_sync_timer_id:
            self.root.after_cancel(self.db_sync_timer_id)
            self.db_sync_timer_id = None

        self.info_panel.update_sync_status("已停止", "#95a5a6")
        self.info_panel.update_sync_countdown("--")

    def _do_db_check_and_sync(self):
        """检测并同步 (通过API)"""
        self.db_check_count += 1
        self.root.after(0, lambda: self.info_panel.update_check_count(self.db_check_count))

        def check_task():
            try:
                if not self.current_desk_id:
                    return

                desk_id = int(self.current_desk_id)

                # 通过API获取线上铺号
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response = loop.run_until_complete(get_current_xue_pu(desk_id))
                loop.close()

                if not response.success:
                    self.root.after(0, lambda: self.log(f"[检测] 获取线上铺号失败: {response.error}"))
                    return

                online_pu = response.data.get('pu_number', 1)
                remote_count = online_pu - 1

                self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu))
                self.current_online_pu = online_pu

                # 检测条件1: 铺号是否一致
                pu_mismatch = (online_pu != self.current_local_pu)

                # 检测条件2: 最后2铺结果是否一致
                result_mismatch = False
                if not pu_mismatch and remote_count >= 2:
                    # 只在铺号一致时检查结果，避免重复同步
                    loop2 = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop2)
                    api_response = loop2.run_until_complete(get_last_n_results(desk_id, 2))
                    loop2.close()

                    if api_response.success:
                        online_results = api_response.data.get('results', [])
                        local_results = roadmap_syncer.get_local_last_n_results(str(desk_id), 2)

                        if online_results and local_results:
                            result_mismatch = (online_results != local_results)
                            if result_mismatch:
                                self.root.after(0, lambda: self.log(
                                    f"[检测 #{self.db_check_count}] 最后2铺结果不一致: 线上{online_results} vs 采集{local_results}"
                                ))

                # 满足任一条件则触发同步
                if pu_mismatch or result_mismatch:
                    self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu, "#e74c3c"))
                    self.root.after(0, lambda: self.info_panel.update_local_pu(self.current_local_pu, "#e74c3c"))

                    if pu_mismatch:
                        self.root.after(0, lambda: self.log(
                            f"[检测 #{self.db_check_count}] 铺号不一致: 线上{online_pu} vs 采集{self.current_local_pu}, 触发同步"
                        ))

                    self.root.after(100, lambda: self._do_roadmap_sync(source="检测"))
                else:
                    self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu, "#9b59b6"))
                    self.root.after(0, lambda: self.info_panel.update_local_pu(self.current_local_pu, "#3498db"))

            except Exception as e:
                self.root.after(0, lambda: self.log(f"[检测] 异常: {e}"))

        threading.Thread(target=check_task, daemon=True).start()

    def _do_db_sync(self):
        """执行同步"""
        self._do_roadmap_sync(source="自动")

    def _check_and_incremental_sync(self):
        """
        post_data后检测是否需要增量同步 (通过API获取线上铺数)

        注意: source_pu 是本地采集器的当前铺号
              online_pu 是后端返回的下一铺号（即已完成铺数+1）

        检测逻辑 (diff = source_pu - online_pu):
        ┌─────────────────────────────────────────────────────────┐
        │ diff = 0      → 同步正常（本地=线上）                   │
        │ diff = 1      → 正常（刚开完牌，post_data尚未返回）     │
        │ diff >= 2     → 漏铺，增量同步补齐                      │
        ├─────────────────────────────────────────────────────────┤
        │ diff = -1     → 正常（post_data刚成功，线上已+1）       │
        │ diff <= -2 且 diff > -10 → 数据异常，全量同步修复       │
        │ diff <= -10   → 换靴（由 on_shoe_change 先触发）        │
        └─────────────────────────────────────────────────────────┘
        """
        def check_task():
            try:
                if not self.current_desk_id:
                    return

                desk_id = int(self.current_desk_id)

                # 通过API获取线上铺数
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response = loop.run_until_complete(get_current_xue_pu(desk_id))
                loop.close()

                if not response.success:
                    self.root.after(0, lambda: self.log(f"[增量检测] 获取线上铺号失败: {response.error}"))
                    return

                # API返回的 pu_number 就是下一铺（即当前进行中的铺号）
                online_pu = response.data.get('pu_number', 1)
                online_count = online_pu - 1  # 已完成的铺数

                # 获取源站铺数 (从browser_monitor缓存)
                source_pu = self.current_local_pu or 1

                self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu))
                self.current_online_pu = online_pu

                # 计算差距
                diff = source_pu - online_pu

                if diff == 0:
                    # 同步正常
                    self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu, "#27ae60"))
                    return

                elif diff == 1:
                    # 正常，刚post_data完成，下次检测应该同步
                    self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu, "#27ae60"))
                    return

                elif diff >= 2:
                    # 漏了铺，需要增量同步补齐
                    self.root.after(0, lambda: self.log(
                        f"[增量检测] 源站第{source_pu}铺，线上第{online_pu}铺，漏{diff}铺，触发增量同步"
                    ))
                    self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu, "#e74c3c"))
                    self.root.after(100, lambda: self._do_incremental_sync(desk_id, online_count, source_pu - 1))

                elif diff == -1:
                    # diff=-1 有两种情况:
                    # 1. 正常: post_data刚成功，线上pu已更新为下一铺，但本地pu还没更新
                    #    (因为新局还没开始，browser_monitor.current_pu还是当前铺)
                    # 2. 异常: 线上真的多了一条记录
                    #
                    # 解决方案: 认为这是正常情况，不触发同步
                    # 如果真的有问题，下一次开牌检测会发现并修复
                    self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu, "#27ae60"))
                    # 不再触发同步，这是post_data刚成功后的正常状态

                elif diff <= -10:
                    # 换靴（线上还是旧靴数据，源站已新靴）
                    # 正常情况下 on_shoe_change 应该先触发，这里是兜底
                    self.root.after(0, lambda: self.log(
                        f"[增量检测] 检测到换靴: 源站{source_pu}铺，线上{online_pu}铺，触发换靴处理"
                    ))
                    self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu, "#e74c3c"))
                    # 触发换靴 (发送add_xue信号)
                    if self.browser_monitor and self.browser_monitor.on_shoe_change:
                        self.browser_monitor.on_shoe_change()

                elif diff <= -2:
                    # 数据异常 (差2-9铺)，需要全量同步修复
                    self.root.after(0, lambda: self.log(
                        f"[增量检测] 数据异常: 源站{source_pu}铺，线上{online_pu}铺，差{abs(diff)}铺，触发全量同步"
                    ))
                    self.root.after(0, lambda: self.info_panel.update_online_pu(online_pu, "#e74c3c"))
                    self.root.after(100, lambda: self._do_roadmap_sync(source="数据修复"))

            except Exception as e:
                self.root.after(0, lambda: self.log(f"[增量检测] 异常: {e}"))

        threading.Thread(target=check_task, daemon=True).start()

    def _do_incremental_sync(self, desk_id: int, online_count: int, source_count: int):
        """
        执行增量同步 - 通过API补齐缺失的铺

        Args:
            desk_id: 桌号
            online_count: 线上已有记录数
            source_count: 源站已有记录数 (不含当前进行中的铺)
        """
        def sync_task():
            try:
                # 设置凭证
                session_id = self.browser_monitor.cached_session_id
                username = self.browser_monitor.cached_username
                if session_id and username:
                    roadmap_syncer.set_credentials(session_id, username)

                # 获取源站完整路单
                roadmap_data = roadmap_syncer._fetch_roadmap_from_api(str(desk_id))
                if not roadmap_data:
                    self.root.after(0, lambda: self.log("[增量同步] 获取源站路单失败"))
                    return

                results = roadmap_data.get("results", [])
                if not results:
                    self.root.after(0, lambda: self.log("[增量同步] 源站路单为空"))
                    return

                # 只插入缺失的铺 (从 online_count+1 到 len(results))
                missing_start = online_count  # 0-indexed
                missing_results = results[missing_start:]

                if not missing_results:
                    self.root.after(0, lambda: self.log("[增量同步] 无需补齐"))
                    return

                self.root.after(0, lambda c=len(missing_results): self.log(
                    f"[增量同步] 需要补齐 {c} 铺 (第{online_count+1}铺 到 第{len(results)}铺)"
                ))

                # 构建要同步的记录列表
                records = []
                for i, code in enumerate(missing_results):
                    pu_num = online_count + i + 1  # 铺号从 online_count+1 开始
                    records.append({
                        "pu_number": pu_num,
                        "libo_result": code
                    })

                # 调用增量同步API
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response = loop.run_until_complete(sync_incremental(desk_id, records))
                loop.close()

                if response.success:
                    result_data = response.data
                    inserted = result_data.get('inserted', 0)
                    updated = result_data.get('updated', 0)
                    skipped = result_data.get('skipped', 0)

                    self.root.after(0, lambda: self.log(
                        f"[增量同步] ✓ 完成: 插入{inserted}, 更新{updated}, 跳过{skipped}"
                    ))

                    # 更新显示
                    new_online_pu = online_count + inserted + 1
                    self.root.after(0, lambda p=new_online_pu: self.info_panel.update_online_pu(p, "#27ae60"))
                else:
                    self.root.after(0, lambda: self.log(f"[增量同步] API失败: {response.error}"))

            except Exception as e:
                self.root.after(0, lambda: self.log(f"[增量同步] 异常: {e}"))

        threading.Thread(target=sync_task, daemon=True).start()

    # ========== 按钮回调 ==========

    def sync_roadmap(self):
        """按钮2: 同步路单信息"""
        if not self.check_browser():
            return

        self.log("点击: 同步路单")
        self.update_status("正在同步路单...")

        self._do_roadmap_sync(source="按钮")
        self.root.after(2000, lambda: self.update_status("就绪"))

    # ========== 运行时长计时器 ==========

    def _start_roadmap_duration_timer(self):
        """启动路单采集运行时长计时器"""
        self.roadmap_start_time = datetime.now()
        self._update_roadmap_duration()

    def _update_roadmap_duration(self):
        """更新路单采集运行时长显示"""
        if self.roadmap_start_time:
            elapsed = int((datetime.now() - self.roadmap_start_time).total_seconds())
            self.info_panel.update_roadmap_duration(elapsed)
            # 每秒更新一次
            self.roadmap_duration_timer_id = self.root.after(1000, self._update_roadmap_duration)

    def _stop_roadmap_duration_timer(self):
        """停止路单采集运行时长计时器"""
        if self.roadmap_duration_timer_id:
            self.root.after_cancel(self.roadmap_duration_timer_id)
            self.roadmap_duration_timer_id = None
        self.roadmap_start_time = None
        self.info_panel.update_roadmap_duration(-1)  # 显示 --

    # ========== FLV推流相关（使用 flv_push 模块）==========

    def _start_flv_push(self, flv_url: str):
        """
        启动 FLV 推流（使用独立的 flv_push 模块）

        Args:
            flv_url: FLV 视频源地址
        """
        from flv_push import FLVStreamPusher

        # 创建推流器
        self.stream_pusher = FLVStreamPusher(self.desk_id)

        # 设置回调
        self.stream_pusher.on_log = lambda msg: self.root.after(0, lambda m=msg: self.log(m))

        def on_started():
            self.flv_start_time = datetime.now()
            self.flv_total_bytes = 0
            self.root.after(0, lambda: self.info_panel.update_flv_status("推流中", "#27ae60"))
            self.root.after(0, lambda p=self.stream_pusher.ffmpeg_pid: self.log(f"[FLV推流] FFmpeg 已启动 (PID: {p})"))
            self.root.after(0, self._start_flv_duration_timer)

        def on_stopped():
            self.root.after(0, lambda: self.info_panel.update_flv_status("已停止", "#95a5a6"))
            self.root.after(0, self._stop_flv_duration_timer)

        def on_error(msg):
            self.root.after(0, lambda m=msg: self.log(f"[FLV推流] 错误: {m}"))
            self.root.after(0, lambda: self.info_panel.update_flv_status("错误", "#e74c3c"))

        def on_stats_update(stats):
            self.flv_total_bytes = stats['total_bytes']
            self.root.after(0, lambda s=stats['speed_kbps']: self.info_panel.update_flv_speed(s))
            self.root.after(0, lambda t=stats['total_bytes']: self.info_panel.update_flv_total(t))

        self.stream_pusher.on_started = on_started
        self.stream_pusher.on_stopped = on_stopped
        self.stream_pusher.on_error = on_error
        self.stream_pusher.on_stats_update = on_stats_update

        # 启动推流
        self.stream_pusher.start(flv_url)

    def _stop_flv_push(self):
        """停止 FLV 推流"""
        if hasattr(self, 'stream_pusher') and self.stream_pusher:
            self.stream_pusher.stop()
            self.stream_pusher = None

        self._stop_flv_duration_timer()
        self.info_panel.update_flv_status("已停止", "#95a5a6")

    def _on_flv_error(self, msg: str):
        """FLV错误回调"""
        self.log(f"[FLV] 错误: {msg}")
        self.info_panel.update_flv_status("错误", "#e74c3c")

    def _start_flv_duration_timer(self):
        """启动FLV推流统计更新定时器"""
        self._update_flv_stats()

    def _update_flv_stats(self):
        """更新FLV推流统计"""
        if self.flv_start_time:
            elapsed = (datetime.now() - self.flv_start_time).total_seconds()

            # 使用 self.flv_total_bytes（requests方式的统计）
            total_bytes = getattr(self, 'flv_total_bytes', 0) or 0
            self.info_panel.update_flv_total(total_bytes)

            # 计算速度
            if elapsed > 0 and total_bytes > 0:
                speed = total_bytes / elapsed / 1024  # KB/s
                self.info_panel.update_flv_speed(speed)
            elif elapsed > 0:
                # 还没收到数据，显示等待中
                self.info_panel.update_flv_speed(0)

            # 每秒更新一次
            self.flv_duration_timer_id = self.root.after(1000, self._update_flv_stats)

    def _stop_flv_duration_timer(self):
        """停止FLV统计更新定时器"""
        if self.flv_duration_timer_id:
            self.root.after_cancel(self.flv_duration_timer_id)
            self.flv_duration_timer_id = None


    # ========== 自动刷新 ==========

    def _start_auto_refresh(self):
        """启动自动刷新台桌信息"""
        if self.browser_opened:
            self.run_async(self._fetch_desk_info_async())
            # 每2秒刷新一次
            self.auto_refresh_id = self.root.after(2000, self._start_auto_refresh)

    def _stop_auto_refresh(self):
        """停止自动刷新"""
        if self.auto_refresh_id:
            self.root.after_cancel(self.auto_refresh_id)
            self.auto_refresh_id = None

    async def _fetch_desk_info_async(self):
        """异步获取台桌信息 - 使用与 browser_monitor 相同的选择器"""
        if not self.context or not self.current_page:
            return

        try:
            # 检查页面是否有效
            if self.current_page.is_closed():
                return

            # 只在游戏页面获取信息
            url = self.current_page.url
            if "game" not in url and "desk=" not in url:
                return

            # 执行JavaScript获取页面信息 (与 browser_monitor.py _check_dom_changes 保持一致)
            info = await self.current_page.evaluate(r"""
                () => {
                    let result = {
                        countdown: null,
                        bet_status: null,
                        round_num: null
                    };

                    // 1. 倒计时 - 使用 browser_monitor 相同的选择器
                    const timer = document.querySelector('.timer, .m-timer');
                    if (timer) {
                        const text = timer.textContent.trim();
                        const num = parseInt(text);
                        if (!isNaN(num)) result.countdown = num;
                    }

                    // 2. 投注状态
                    const status = document.querySelector('.status');
                    if (status) result.bet_status = status.textContent.trim();

                    // 3. 局号
                    const gameNum = document.querySelector('.m-timer-and-table-info .bottom');
                    if (gameNum) {
                        const match = gameNum.textContent.match(/\d+/);
                        if (match) result.round_num = parseInt(match[0]);
                    }

                    return result;
                }
            """)

            # 更新UI
            if info.get('countdown') is not None:
                countdown = info['countdown']
                color = "#e74c3c" if countdown <= 5 else "#2980b9"
                self.root.after(0, lambda c=countdown, col=color: self.info_panel.update_countdown(c, col))

            if info.get('bet_status'):
                status = info['bet_status']
                if "接受" in status:
                    color = "#27ae60"
                elif "停止" in status or "开牌" in status:
                    color = "#e74c3c"
                else:
                    color = "#2980b9"
                self.root.after(0, lambda s=status, col=color: self.info_panel.update_bet_status(s, col))

            if info.get('round_num') is not None:
                round_num = info['round_num']
                self.root.after(0, lambda r=round_num: self.info_panel.update_round_num(r))
                # 更新本地铺号
                self.current_local_pu = round_num
                self.root.after(0, lambda r=round_num: self.info_panel.update_local_pu(r))

        except Exception as e:
            # 静默处理错误，不打印日志避免刷屏
            pass

    # ========== 辅助方法 ==========

    def _process_captured_roadmap(self):
        """处理捕获的路单数据"""
        if not self.captured_roadmap_data:
            return

        try:
            result_str = self.captured_roadmap_data.get('result', '')
            desk = self.captured_roadmap_data.get('desk', '')

            if desk and not self.current_desk_id:
                self.current_desk_id = desk
                self.root.after(0, lambda: self.info_panel.update_desk_id(desk))

            results = [r for r in result_str.split('#') if r]
            if results:
                self.current_local_pu = len(results) + 1
                self.root.after(0, lambda: self.info_panel.update_local_pu(self.current_local_pu))
                self.root.after(0, lambda: self.info_panel.update_round_num(self.current_local_pu))

        except Exception as e:
            self.log(f"[路单处理] 异常: {e}")

    # ========== 关闭 ==========

    def on_closing(self):
        """窗口关闭"""
        self.log("[关闭] 正在退出程序...")

        # 停止 FLV 推流
        self._stop_flv_push()

        self._stop_db_sync_timer()

        # 停止 session 监控和登录重试
        roadmap_session.stop_session_monitor()
        roadmap_session.stop_login_retry_loop()

        if self.browser_monitor:
            try:
                self.browser_monitor.stop_monitoring()
            except:
                pass

        # 执行退出登录后再关闭
        self.run_async(self._logout_and_close_async())

    async def _logout_and_close_async(self):
        """退出登录后关闭所有资源"""
        try:
            # 如果浏览器已打开且有页面，先尝试退出登录
            if self.browser_opened and self.current_page:
                self.root.after(0, lambda: self.log("[关闭] 正在退出登录..."))
                self.root.after(0, lambda: self.update_status("正在退出登录..."))

                try:
                    logout_result = await roadmap_logout.logout(self.current_page)
                    if logout_result.get("success"):
                        self.root.after(0, lambda: self.log("[关闭] 退出登录成功"))
                    else:
                        self.root.after(0, lambda m=logout_result.get("message", ""): self.log(f"[关闭] 退出登录: {m}"))
                except Exception as e:
                    self.root.after(0, lambda err=str(e): self.log(f"[关闭] 退出登录出错: {err}"))

                # 等待一下确保退出完成
                await asyncio.sleep(1)

            # 关闭浏览器资源
            await self._close_all_async()

        except Exception as e:
            logger.error(f"[关闭] 退出过程出错: {e}")

        finally:
            # 销毁窗口
            self.root.after(100, self.root.destroy)

    async def _close_all_async(self):
        """异步关闭资源"""
        try:
            if self.current_page:
                await self.current_page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except:
            pass

        # 清除浏览器 PID 记录
        pm = get_process_manager()
        if pm:
            pm.clear_browser_pid()

    def emergency_cleanup(self):
        """
        紧急清理（供进程管理器调用）

        当程序被强制关闭时，这个方法会被调用来清理资源
        """
        logger.info("[紧急清理] 开始...")

        # 1. 停止所有定时器
        try:
            self._stop_db_sync_timer()
            self._stop_auto_refresh()
            self._stop_roadmap_duration_timer()
            self._stop_flv_duration_timer()
        except:
            pass

        # 1.5 停止FLV推流
        try:
            if self.stream_pusher:
                self.stream_pusher.stop()
        except:
            pass

        # 2. 停止监控模块
        try:
            roadmap_session.stop_session_monitor()
            roadmap_session.stop_login_retry_loop()
        except:
            pass

        try:
            if self.browser_monitor:
                self.browser_monitor.stop_monitoring()
        except:
            pass

        # 3. 尝试同步退出登录（在信号处理中可能无法完成异步操作）
        # 这里只能做同步的清理工作
        logger.info("[紧急清理] 完成")
