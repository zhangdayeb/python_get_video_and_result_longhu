# -*- coding: utf-8 -*-
"""
浏览器全面监控模块

功能:
1. 浏览器信息: URL、Cookie、LocalStorage、SessionStorage
2. HTTP/WebSocket请求监控
3. DOM变化监控: 倒计时、投注状态、开牌信息、台桌信息

日志管理:
- 按类型分文件: {table}_{type}_{date}.jsonl
- 类型: dom, http, storage
- 自动清理过期日志
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List
import logging

from monitor.http_monitor import HttpMonitor
from monitor.storage_monitor import StorageMonitor

logger = logging.getLogger("browser_monitor")


class BrowserMonitor:
    """浏览器全面监控器"""

    # DOM选择器配置 (基于利博页面分析)
    DOM_SELECTORS = {
        "countdown": {
            "selectors": [".timer", ".m-timer"],
            "type": "text",
            "description": "倒计时秒数"
        },
        "bet_status": {
            "selectors": [".status", ".timer-and-status .status"],
            "type": "text",
            "description": "投注状态文字"
        },
        "table_info": {
            "selectors": [".inf", ".m-timer-and-table-info"],
            "type": "multi",
            "description": "台号、局数等"
        },
        "table_id": {
            "selectors": [".inf-value", ".m-timer-and-table-info .top"],
            "type": "text",
            "description": "台号如F1"
        },
        "game_number": {
            "selectors": [".m-timer-and-table-info .bottom", "[class*='局数']"],
            "type": "text",
            "description": "局数"
        },
        "roadmap_stats": {
            "selectors": [".sumary", ".pc-pediction"],
            "type": "multi",
            "description": "龙虎和统计"
        },
        "balance": {
            "selectors": [".inf-value:nth-child(3)", "[class*='余额']"],
            "type": "text",
            "description": "账户余额"
        },
        "bet_amount": {
            "selectors": [".total-bet-group .value1"],
            "type": "text",
            "description": "当前下注金额"
        },
        "win_amount": {
            "selectors": [".total-winloss-group .value1"],
            "type": "text",
            "description": "赢得金额"
        }
    }

    def __init__(self, log_dir: str = None, retention_minutes: int = 20, desk_id: int = None):
        """
        初始化浏览器监控器

        Args:
            log_dir: 日志目录，如果不指定则使用实例专属目录
            retention_minutes: 日志保留时间(分钟)
            desk_id: 台桌ID (用于信号发送，直接使用配置值)
        """
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            # 使用实例专属的日志目录 (支持多开)
            from core.config import config
            self.log_dir = config.instance_logs_dir / "monitor"

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.retention_minutes = retention_minutes

        # 台桌ID (直接使用配置值，用于信号发送)
        self.desk_id: Optional[int] = desk_id

        # 当前监控的台桌名称 (如 F1，用于日志)
        self.current_table: Optional[str] = None

        # 分类日志文件 (按类型分开)
        self._log_files: Dict[str, Path] = {}
        self._current_log_date: Optional[str] = None

        # 状态缓存 (用于检测变化)
        self.state_cache = {
            "url": None,
            "countdown": None,
            "bet_status": None,
            "game_number": None,
            "cards_visible": False,
        }

        # 已截图的局号集合 (防止重复截图)
        self.captured_games = set()

        # 使用实例专属的截图目录 (支持多开)
        from core.config import config
        self.screenshot_dir = config.instance_screenshots_dir

        # 铺号/靴号管理 (延迟初始化，从API获取)
        self.current_pu: Optional[int] = None
        self.current_xue: Optional[int] = None
        self._xue_pu_initialized: bool = False

        # 换靴检测: 记录上次路单铺数
        self._last_pu_count: Optional[int] = None

        # 回调函数
        self.on_countdown_change: Optional[Callable[[int], None]] = None
        self.on_status_change: Optional[Callable[[str, str], None]] = None
        self.on_new_game: Optional[Callable[[str], None]] = None
        self.on_cards_captured: Optional[Callable[[str, Dict], None]] = None
        self.on_url_change: Optional[Callable[[str, str], None]] = None
        self.on_pu_change: Optional[Callable[[int], None]] = None
        self.on_xue_change: Optional[Callable[[int], None]] = None
        self.on_http_request: Optional[Callable[[Dict], None]] = None
        self.on_websocket_message: Optional[Callable[[Dict], None]] = None
        self.on_card_capture_failed: Optional[Callable[[str], None]] = None
        self.on_shoe_change: Optional[Callable[[], None]] = None  # 换靴回调

        # 监控状态
        self.is_running = False
        self._page = None
        self._context = None
        self._monitor_task = None

        # 子监控器 (传入分类日志回调)
        self._http_monitor = HttpMonitor(write_log_callback=lambda t, d: self._write_log("http", t, d))
        self._storage_monitor = StorageMonitor(write_log_callback=lambda t, d: self._write_log("storage", t, d))

        # 设置HTTP监控器的游戏API回调
        self._http_monitor.on_game_api = self._handle_game_api

        # 设置HTTP请求回调（传递FLV等请求给外部）
        self._http_monitor.on_http_request = self._forward_http_request

        # 统计
        self.stats = {
            "http_requests": 0,
            "http_responses": 0,
            "websocket_messages": 0,
            "dom_changes": 0,
            "screenshots": 0,
        }

        # 单独的 roadmap 日志文件
        self.roadmap_log_file = self.log_dir / "roadmap.jsonl"

        # 后端API
        self._backend_api = None
        self._init_backend_api()

        logger.info(f"浏览器监控器初始化, 日志目录: {self.log_dir}, 保留{retention_minutes}分钟")

    @property
    def cached_session_id(self) -> str:
        """获取缓存的session ID"""
        return self._storage_monitor.cached_session_id

    @property
    def cached_username(self) -> str:
        """获取缓存的用户名"""
        return self._storage_monitor.cached_username

    def _init_backend_api(self):
        """初始化后端API"""
        try:
            from api.backend import BackendAPI
            self._backend_api = BackendAPI()
            logger.info("[Backend] API初始化成功")
        except Exception as e:
            logger.error(f"[Backend] API初始化失败: {e}")
            self._backend_api = None

    async def send_start_signal(self, countdown_time: int = 45):
        """发送开局信号 (开始下注)"""
        if not self._backend_api:
            logger.warning("[Backend] API未初始化，无法发送开局信号")
            return

        desk_id = self._get_desk_id()
        if not desk_id:
            logger.warning("[Backend] 未配置台桌ID，跳过开局信号")
            return

        try:
            logger.info(f"[Backend] 准备发送start信号: 桌{desk_id}, 倒计时{countdown_time}秒")
            response = await self._backend_api.send_start_signal(desk_id, countdown_time)
            if response.success:
                logger.info(f"[Backend] ✓ start信号发送成功: 桌{desk_id}, 倒计时{countdown_time}秒")
            else:
                logger.error(f"[Backend] ✗ start信号发送失败: {response.error}")
        except Exception as e:
            logger.error(f"[Backend] 发送start信号异常: {e}")

    async def send_end_signal(self):
        """发送结束信号 (停止下注)"""
        if not self._backend_api:
            logger.warning("[Backend] API未初始化，无法发送结束信号")
            return

        desk_id = self._get_desk_id()
        if not desk_id:
            logger.warning("[Backend] 未配置台桌ID，跳过结束信号")
            return

        try:
            logger.info(f"[Backend] 准备发送end信号: 桌{desk_id}")
            response = await self._backend_api.send_end_signal(desk_id)
            if response.success:
                logger.info(f"[Backend] ✓ end信号发送成功: 桌{desk_id}")
            else:
                logger.error(f"[Backend] ✗ end信号发送失败: {response.error}")
        except Exception as e:
            logger.error(f"[Backend] 发送结束信号异常: {e}")

    def _get_desk_id(self) -> Optional[int]:
        """获取台桌ID (直接返回配置值)"""
        return self.desk_id

    async def init_xue_pu_from_api(self):
        """从后端API初始化靴号铺号"""
        if self._xue_pu_initialized:
            return

        if not self._backend_api:
            self._init_backend_api()

        desk_id = self._get_desk_id()
        if not desk_id:
            logger.warning("[初始化] 未配置台桌ID，使用默认靴号铺号")
            self.current_xue = 1
            self.current_pu = 1
            self._xue_pu_initialized = True
            return

        try:
            logger.info(f"[初始化] 从API获取靴号铺号: desk_id={desk_id}")
            response = await self._backend_api.get_current_xue_pu(desk_id)
            if response.success and response.data:
                data = response.data
                self.current_xue = data.get('xue_number', 1)
                self.current_pu = data.get('pu_number', 1)
                logger.info(f"[初始化] ✓ 从API获取成功: xue={self.current_xue}, pu={self.current_pu}")
            else:
                logger.warning(f"[初始化] API获取失败: {response.error}，使用默认值")
                self.current_xue = 1
                self.current_pu = 1
        except Exception as e:
            logger.error(f"[初始化] 获取靴号铺号异常: {e}，使用默认值")
            self.current_xue = 1
            self.current_pu = 1

        self._xue_pu_initialized = True

    async def _handle_status_signal(self, old_status: str, new_status: str, countdown: int):
        """处理投注状态变化，发送开局/结束信号 (非阻塞)"""
        if not new_status:
            return

        # 使用 create_task 让API调用在后台运行，不阻塞监控循环
        if "开始" in new_status and "投注" in new_status:
            logger.info(f"[状态] 检测到开始投注状态: {new_status}, 倒计时: {countdown}秒")
            asyncio.create_task(self._safe_send_start_signal(countdown))
        elif "停止" in new_status and "投注" in new_status:
            logger.info(f"[状态] 检测到停止投注状态: {new_status}")
            asyncio.create_task(self._safe_send_end_signal())
        elif "请下注" in new_status:
            logger.info(f"[状态] 检测到请下注状态: {new_status}, 倒计时: {countdown}秒")
            asyncio.create_task(self._safe_send_start_signal(countdown))

    async def _safe_send_start_signal(self, countdown: int):
        """安全发送开局信号 (带完整异常处理)"""
        try:
            await self.send_start_signal(countdown)
        except Exception as e:
            logger.error(f"[Backend] _safe_send_start_signal异常: {e}")

    async def _safe_send_end_signal(self):
        """安全发送结束信号 (带完整异常处理)"""
        try:
            await self.send_end_signal()
        except Exception as e:
            logger.error(f"[Backend] _safe_send_end_signal异常: {e}")

    def _get_log_file(self, log_category: str) -> Path:
        """
        获取分类日志文件路径

        Args:
            log_category: 日志类别 (dom, http, storage)

        Returns:
            日志文件路径: desk{id}_{category}_{YYYYMMDD}.jsonl
        """
        # 使用desk_id作为文件名前缀，永远不会是unknown
        desk_prefix = f"desk{self.desk_id}" if self.desk_id else "desk0"
        date_str = datetime.now().strftime("%Y%m%d")

        # 检查是否需要切换日期
        if self._current_log_date != date_str:
            self._current_log_date = date_str
            self._log_files.clear()  # 清空缓存，重新创建

        # 获取或创建日志文件路径
        cache_key = f"{desk_prefix}_{log_category}"
        if cache_key not in self._log_files:
            filename = f"{desk_prefix}_{log_category}_{date_str}.jsonl"
            self._log_files[cache_key] = self.log_dir / filename

        return self._log_files[cache_key]

    def _write_log(self, log_category: str, log_type: str, data: Dict):
        """
        写入分类日志

        Args:
            log_category: 日志类别 (dom, http, storage)
            log_type: 具体日志类型 (如 countdown_change, http_response 等)
            data: 日志数据
        """
        try:
            log_file = self._get_log_file(log_category)

            # 简化的日志格式
            record = {
                "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],  # 简化时间戳
                "type": log_type,
                "data": data
            }

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        except Exception as e:
            logger.error(f"写入日志失败: {e}")

    def _cleanup_old_logs(self):
        """
        清理过期日志文件

        新格式: {table}_{category}_{YYYYMMDD}.jsonl
        保留最近 retention_minutes 分钟内的日志
        """
        try:
            cutoff_date = (datetime.now() - timedelta(minutes=self.retention_minutes)).strftime("%Y%m%d")

            for log_file in self.log_dir.glob("*.jsonl"):
                try:
                    name = log_file.stem
                    # 新格式: F2_dom_20251218
                    parts = name.rsplit("_", 1)
                    if len(parts) >= 2:
                        date_str = parts[-1]
                        if len(date_str) == 8 and date_str.isdigit():
                            if date_str < cutoff_date:
                                log_file.unlink()
                                logger.info(f"清理过期日志: {log_file.name}")
                                continue

                    # 回退: 按修改时间判断
                    cutoff_time = datetime.now() - timedelta(minutes=self.retention_minutes)
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime < cutoff_time:
                        log_file.unlink()
                        logger.info(f"清理过期日志(按修改时间): {log_file.name}")

                except Exception as e:
                    logger.warning(f"清理日志文件失败 {log_file.name}: {e}")

        except Exception as e:
            logger.error(f"清理日志失败: {e}")

    async def start(self, context, page):
        """启动监控"""
        self._context = context
        self._page = page
        self.is_running = True

        # 从API初始化靴号铺号
        await self.init_xue_pu_from_api()

        # 设置HTTP监听
        self._http_monitor.setup_listeners(page)

        # 设置WebSocket监听
        await self._setup_websocket_listener(context)

        # 启动DOM监控循环
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        # 启动日志清理定时任务
        asyncio.create_task(self._cleanup_loop())

        logger.info("[监控] 浏览器监控已启动")

    async def stop(self):
        """停止监控"""
        self.is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("[监控] 浏览器监控已停止")

    def stop_monitoring(self):
        """同步停止监控 (供UI调用)"""
        self.is_running = False
        logger.info("[监控] 收到停止请求")

    async def _setup_websocket_listener(self, context):
        """设置WebSocket监听"""
        try:
            for page in context.pages:
                cdp = await page.context.new_cdp_session(page)
                await cdp.send("Network.enable")

                def on_ws_received(params):
                    try:
                        self.stats["websocket_messages"] += 1
                        data = params.get("response", {}).get("payloadData", "")

                        self._write_log("http", "websocket", {
                            "request_id": params.get("requestId"),
                            "data": data[:500] if data else None
                        })

                        if self.on_websocket_message:
                            self.on_websocket_message({"data": data})

                    except Exception as e:
                        pass

                cdp.on("Network.webSocketFrameReceived", on_ws_received)

        except Exception as e:
            logger.warning(f"WebSocket监听设置失败: {e}")

    async def _monitor_loop(self):
        """
        DOM监控循环 - 永不崩溃设计

        核心原则: 除非人工退出程序，否则监控永远运行
        """
        import time
        import traceback

        loop_count = 0
        last_heartbeat = 0
        consecutive_errors = 0  # 连续错误计数
        max_consecutive_errors = 10  # 连续错误阈值

        logger.info("[监控循环] 开始运行 (永不崩溃模式)")

        while True:  # 永远循环，只有人工退出才停止
            loop_start = time.time()
            try:
                # 检查是否应该退出
                if not self.is_running:
                    logger.info("[监控循环] is_running=False, 准备退出")
                    break

                loop_count += 1
                now = time.time()

                # 每30秒输出一次心跳日志
                if now - last_heartbeat > 30:
                    last_heartbeat = now
                    page_status = "ok" if self._page and not self._page.is_closed() else "invalid"
                    logger.info(f"[监控心跳] #{loop_count}, page={page_status}, errors={consecutive_errors}")

                # 检查page状态
                if not self._page:
                    if loop_count % 100 == 0:
                        logger.warning("[监控] page对象为None，等待page恢复...")
                    await asyncio.sleep(1)
                    continue

                if self._page.is_closed():
                    if loop_count % 100 == 0:
                        logger.warning("[监控] page已关闭，等待page恢复...")
                    await asyncio.sleep(1)
                    continue

                # 执行监控任务
                try:
                    await self._check_browser_state()
                except Exception as e:
                    logger.error(f"[监控] _check_browser_state异常: {e}")

                try:
                    await self._check_dom_changes()
                    consecutive_errors = 0  # 成功执行，重置错误计数
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"[监控] _check_dom_changes异常 ({consecutive_errors}次): {e}")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"[监控] 连续{max_consecutive_errors}次DOM检查失败，等待5秒后重试")
                        logger.error(f"[监控] 堆栈: {traceback.format_exc()}")
                        await asyncio.sleep(5)
                        consecutive_errors = 0  # 重置，继续尝试

                await asyncio.sleep(0.3)

            except asyncio.CancelledError:
                logger.info("[监控循环] 收到CancelledError，退出循环")
                break
            except Exception as e:
                # 最外层异常捕获 - 确保循环永不崩溃
                logger.error(f"[监控循环] 未预期的异常: {e}")
                logger.error(f"[监控循环] 堆栈: {traceback.format_exc()}")
                # 等待后继续，不退出
                try:
                    await asyncio.sleep(2)
                except:
                    pass
            finally:
                # 记录每次循环耗时（调试用）
                loop_elapsed = time.time() - loop_start
                if loop_elapsed > 2.0:  # 如果单次循环超过2秒，记录警告
                    logger.warning(f"[监控循环] #{loop_count} 耗时过长: {loop_elapsed:.2f}秒")

        logger.info(f"[监控循环] 已退出, 总循环次数={loop_count}")

    async def _cleanup_loop(self):
        """日志清理循环"""
        while self.is_running:
            try:
                self._cleanup_old_logs()
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理循环错误: {e}")

    async def _check_browser_state(self):
        """检查浏览器状态(URL, Cookie等)"""
        try:
            # URL变化
            current_url = self._page.url
            if current_url != self.state_cache["url"]:
                old_url = self.state_cache["url"]
                self.state_cache["url"] = current_url

                # 解析台桌ID
                match = re.search(r'desk=(\d+)', current_url)
                if match:
                    desk_id = match.group(1)
                    table_map = {
                        "1": "F1", "2": "F2", "3": "F3", "4": "F4",
                        "5": "F5", "6": "F6", "10": "F10"
                    }
                    self.current_table = table_map.get(desk_id, f"T{desk_id}")
                    self._log_files.clear()  # 台桌变化，重新创建日志文件

                self._write_log("dom", "url_change", {
                    "old": old_url,
                    "new": current_url,
                    "table": self.current_table
                })

                if self.on_url_change:
                    self.on_url_change(old_url, current_url)

            # 获取Cookie和Storage
            await self._storage_monitor.capture(self._context, self._page)

        except Exception as e:
            logger.error(f"检查浏览器状态失败: {e}")

    async def _check_dom_changes(self):
        """检查DOM变化 - 每次循环必须记录日志"""
        import time
        start_time = time.time()

        # 初始化日志数据（确保无论如何都有记录）
        poll_data = {
            "countdown": None,
            "status": None,
            "game": None,
            "cards_visible": False,
            "cards_count": 0
        }

        try:
            # 使用asyncio.wait_for添加超时保护，避免page.evaluate阻塞
            dom_state = await asyncio.wait_for(
                self._page.evaluate("""
                () => {
                    const result = {
                        countdown: null,
                        bet_status: null,
                        game_number: null,
                        cards: {
                            visible: false,
                            data: null,
                            positions: null
                        },
                        _debug: {
                            url: window.location.href,
                            hasAppRoot: !!document.querySelector('#app'),
                            hasTimerClass: !!document.querySelector('.timer'),
                            hasMTimerClass: !!document.querySelector('.m-timer'),
                            hasStatusClass: !!document.querySelector('.status'),
                            timerText: null,
                            statusText: null
                        }
                    };

                    // 1. 倒计时 - 尝试多种选择器
                    const timerSelectors = ['.timer', '.m-timer', '.countdown', '[class*="timer"]', '[class*="countdown"]'];
                    for (const sel of timerSelectors) {
                        const timer = document.querySelector(sel);
                        if (timer) {
                            const text = timer.textContent.trim();
                            result._debug.timerText = text;
                            const num = parseInt(text);
                            if (!isNaN(num) && num >= 0 && num <= 60) {
                                result.countdown = num;
                                break;
                            }
                        }
                    }

                    // 2. 投注状态
                    const status = document.querySelector('.status');
                    if (status) {
                        result.bet_status = status.textContent.trim();
                        result._debug.statusText = status.textContent.trim();
                    }

                    // 3. 局号
                    const gameNum = document.querySelector('.m-timer-and-table-info .bottom');
                    if (gameNum) {
                        const match = gameNum.textContent.match(/\\d+/);
                        if (match) result.game_number = match[0];
                    }

                    // 4. 牌型数据 (龙虎版本 - 只需2张牌)
                    const cardResultRoot = document.querySelector('.d-card-result-root.card-result');
                    if (cardResultRoot) {
                        // 龙虎使用 dragon-result-group 和 tiger-result-group
                        const dragonGroup = cardResultRoot.querySelector('.dragon-result-group');
                        const tigerGroup = cardResultRoot.querySelector('.tiger-result-group');

                        if (dragonGroup && tigerGroup) {
                            const suits = ['s', 'h', 'c', 'd'];

                            const parseCard = (element) => {
                                if (!element) return null;
                                const classes = (element.className || '').split(' ');

                                for (let cls of classes) {
                                    const match = cls.match(/^([vh])_([0-9A-Fa-f]{4})$/);
                                    if (match) {
                                        const hexCode = match[2].toUpperCase();
                                        const value = parseInt(hexCode.substring(0, 2), 16) >> 4;
                                        const suitIndex = parseInt(hexCode.substring(2, 4), 16) & 0x03;
                                        const suit = suits[suitIndex];

                                        if (value >= 1 && value <= 13) {
                                            return { value, suit, cls };
                                        }
                                    }
                                    if (cls.match(/^([vh])_$/)) {
                                        return null;
                                    }
                                }
                                return null;
                            };

                            const dpr = window.devicePixelRatio || 1;
                            const getPosition = (element, index) => {
                                if (!element) return null;
                                const rect = element.getBoundingClientRect();
                                if (rect.width === 0 || rect.height === 0) return null;

                                const classes = (element.className || '').split(' ');
                                let direction = 'v';
                                let cardClass = '';
                                for (let cls of classes) {
                                    const match = cls.match(/^([vh])_([0-9A-Fa-f]{4})?$/);
                                    if (match) {
                                        direction = match[1].toLowerCase();
                                        cardClass = cls;
                                        break;
                                    }
                                }

                                return {
                                    index: index,
                                    x: Math.round(rect.x * dpr),
                                    y: Math.round(rect.y * dpr),
                                    width: Math.round(rect.width * dpr),
                                    height: Math.round(rect.height * dpr),
                                    direction: direction,
                                    class: cardClass,
                                    dpr: dpr
                                };
                            };

                            // 龙虎只有2张牌: 龙牌(.card1) 和 虎牌(.card1)
                            const dragonCard = dragonGroup.querySelector('.card1');
                            const tigerCard = tigerGroup.querySelector('.card1');

                            const card1 = parseCard(dragonCard);  // 龙牌
                            const card2 = parseCard(tigerCard);   // 虎牌

                            // 龙虎只需要2张牌都有效
                            const hasValidCards = (card1 && card2);

                            if (hasValidCards) {
                                result.cards.visible = true;
                                result.cards.data = {
                                    "1": card1 ? card1.value + "|" + card1.suit : "0|0",  // 龙牌
                                    "2": card2 ? card2.value + "|" + card2.suit : "0|0"   // 虎牌
                                };
                                result.cards.positions = [
                                    getPosition(dragonCard, 1),  // 龙牌位置
                                    getPosition(tigerCard, 2)    // 虎牌位置
                                ].filter(p => p !== null);
                            }
                        }
                    }

                    return result;
                }
            """),
                timeout=5.0  # 5秒超时
            )

            # 更新日志数据 (独立try，不影响后续回调)
            try:
                poll_data["countdown"] = dom_state.get("countdown")
                poll_data["status"] = dom_state.get("bet_status")
                poll_data["game"] = dom_state.get("game_number")
                cards_info_for_log = dom_state.get("cards") or {}
                poll_data["cards_visible"] = cards_info_for_log.get("visible", False)
                positions_for_log = cards_info_for_log.get("positions") or []
                poll_data["cards_count"] = len(positions_for_log)
            except Exception as log_err:
                poll_data["error"] = f"log_data: {log_err}"

            changes = {}

            # 调试日志 - 每3秒输出一次DOM状态 (便于调试)
            if not hasattr(self, '_last_debug_time'):
                self._last_debug_time = 0
            now = time.time()
            if now - self._last_debug_time > 3:
                self._last_debug_time = now
                countdown = dom_state.get('countdown')
                status = dom_state.get('bet_status')
                game = dom_state.get('game_number')
                debug_info = dom_state.get('_debug', {})
                # 输出详细调试信息
                logger.info(f"[DOM调试] countdown={countdown}, status={status}, game={game}")
                # 如果DOM获取失败，输出更多调试信息
                if countdown is None and status is None:
                    logger.info(f"[DOM调试详情] url={debug_info.get('url', 'N/A')[:50]}..., "
                               f"hasApp={debug_info.get('hasAppRoot')}, "
                               f"hasTimer={debug_info.get('hasTimerClass')}, "
                               f"hasMTimer={debug_info.get('hasMTimerClass')}, "
                               f"hasStatus={debug_info.get('hasStatusClass')}")

            # 1. 倒计时 - 优先使用DOM获取的值，失败时使用缓存递减
            new_countdown = dom_state.get("countdown")
            old_countdown = self.state_cache.get("countdown")

            # 初始化倒计时递减计时器
            if not hasattr(self, '_countdown_last_update'):
                self._countdown_last_update = now

            if new_countdown is not None:
                # DOM成功获取到倒计时，更新缓存
                self.state_cache["countdown"] = new_countdown
                self._countdown_last_update = now
                try:
                    if self.on_countdown_change:
                        self.on_countdown_change(new_countdown)
                except Exception as cb_err:
                    logger.error(f"[回调] on_countdown_change异常: {cb_err}")
            elif old_countdown is not None and old_countdown > 0:
                # DOM获取失败，但有缓存值，每秒递减
                time_elapsed = now - self._countdown_last_update
                if time_elapsed >= 1.0:
                    decremented = max(0, old_countdown - int(time_elapsed))
                    self.state_cache["countdown"] = decremented
                    self._countdown_last_update = now
                    try:
                        if self.on_countdown_change:
                            self.on_countdown_change(decremented)
                    except Exception as cb_err:
                        logger.error(f"[回调] on_countdown_change异常: {cb_err}")

            # 记录变化日志
            if new_countdown != old_countdown and new_countdown is not None:
                changes["countdown"] = {"old": old_countdown, "new": new_countdown}

            # 2. 投注状态变化
            if dom_state.get("bet_status") != self.state_cache.get("bet_status"):
                old_val = self.state_cache.get("bet_status")
                new_val = dom_state.get("bet_status")
                self.state_cache["bet_status"] = new_val
                changes["bet_status"] = {"old": old_val, "new": new_val}

                countdown = dom_state.get("countdown") or 45
                try:
                    await self._handle_status_signal(old_val, new_val, countdown)
                except Exception as sig_err:
                    logger.error(f"[信号] _handle_status_signal异常: {sig_err}")

                try:
                    if self.on_status_change:
                        self.on_status_change(old_val, new_val)
                except Exception as cb_err:
                    logger.error(f"[回调] on_status_change异常: {cb_err}")

            # 3. 局号变化
            if dom_state.get("game_number") != self.state_cache.get("game_number"):
                old_val = self.state_cache.get("game_number")
                new_val = dom_state.get("game_number")
                self.state_cache["game_number"] = new_val
                changes["game_number"] = {"old": old_val, "new": new_val}

                self.state_cache["cards_visible"] = False

                if old_val is not None and new_val:
                    old_pu = self.current_pu
                    self.current_pu += 1
                    logger.info(f"[铺号] 新局开始: {old_pu} -> {self.current_pu}")
                    try:
                        if self.on_pu_change:
                            self.on_pu_change(self.current_pu)
                    except Exception as cb_err:
                        logger.error(f"[回调] on_pu_change异常: {cb_err}")

                try:
                    if self.on_new_game and new_val:
                        self.on_new_game(new_val)
                except Exception as cb_err:
                    logger.error(f"[回调] on_new_game异常: {cb_err}")

            # 4. 牌型数据检测
            cards_info = dom_state.get("cards", {})
            cards_visible = cards_info.get("visible", False)

            if cards_visible != self.state_cache.get("cards_visible"):
                old_visible = self.state_cache.get("cards_visible")
                self.state_cache["cards_visible"] = cards_visible
                changes["cards_visible"] = {"old": old_visible, "new": cards_visible}

                if cards_visible and not old_visible:
                    game_number = dom_state.get("game_number")
                    if game_number and game_number not in self.captured_games:
                        await asyncio.sleep(0.8)
                        try:
                            await self._capture_cards(game_number, cards_info)
                        except Exception as cap_err:
                            logger.error(f"[截图] _capture_cards异常: {cap_err}")

            if changes:
                self.stats["dom_changes"] += 1
                self._write_log("dom", "state_change", {
                    "changes": changes,
                    "state": {
                        "countdown": dom_state.get("countdown"),
                        "status": dom_state.get("bet_status"),
                        "game": dom_state.get("game_number"),
                        "cards": cards_visible
                    }
                })

        except asyncio.TimeoutError:
            logger.warning("[DOM] page.evaluate超时 (5秒)")
            poll_data["error"] = "timeout"
        except Exception as e:
            logger.error(f"检查DOM变化失败: {e}")
            poll_data["error"] = str(e)
        finally:
            # 无论成功还是失败，都记录日志
            elapsed_ms = int((time.time() - start_time) * 1000)
            poll_data["ms"] = elapsed_ms
            self._write_log("dom", "poll", poll_data)

    async def _capture_cards(self, game_number: str, cards_info: Dict):
        """截图并保存牌面数据"""
        try:
            from core.game_processor import game_processor

            desk_id = self._get_desk_id() or 1
            desk_name = self.current_table or "unknown"

            logger.info(f"[处理] 开始处理局号 {game_number}, 桌{desk_id}, 靴{self.current_xue}, 铺{self.current_pu}")

            # 获取牌面坐标 (用于备用裁剪)
            card_positions = cards_info.get("positions", [])

            result = await game_processor.process(
                page=self._page,
                game_number=game_number,
                desk_id=desk_id,
                xue_number=self.current_xue,
                pu_number=self.current_pu,
                card_positions=card_positions
            )

            logger.info(f"[处理] game_processor返回: success={result.get('success')}, upload={result.get('upload_success')}, error={result.get('error')}")

            capture_success = result.get("success", False) and result.get("upload_success", False)

            json_path = self.screenshot_dir / f"{desk_name}_game{game_number}.json"
            card_data = {
                "desk_id": desk_name,
                "game_number": game_number,
                "xue": self.current_xue,
                "pu": self.current_pu,
                "timestamp": datetime.now().isoformat(),
                "screenshot": Path(result.get("screenshot_path", "")).name if result.get("screenshot_path") else None,
                "card_data": cards_info.get("data"),
                "card_positions": cards_info.get("positions"),
                "card_crops": result.get("card_crops", {}),
                "ai_result": result.get("ai_result"),
                "result": result.get("result"),
                "ext": result.get("ext"),
                "upload_success": result.get("upload_success", False)
            }

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(card_data, f, ensure_ascii=False, indent=2)

            logger.info(f"[牌面] 局{game_number}: AI={result.get('ai_result')}, result={result.get('result')}|{result.get('ext')}, upload={result.get('upload_success')}")

            if not capture_success:
                logger.warning(f"[截图] 局{game_number}: 处理失败({result.get('error', '未知')}), 1秒后触发路单同步")
                if self.on_card_capture_failed:
                    asyncio.create_task(self._delayed_capture_failed_callback(game_number))

            self.captured_games.add(game_number)
            self.stats["screenshots"] += 1

            self._write_log("dom", "cards_captured", {
                "game": game_number,
                "xue": self.current_xue,
                "pu": self.current_pu,
                "cards": cards_info.get("data"),
                "ai": result.get("ai_result"),
                "result": f"{result.get('result')}|{result.get('ext')}",
                "upload": result.get("upload_success")
            })

            if self.on_cards_captured:
                screenshot_path = result.get("screenshot_path", "")
                logger.info(f"[回调] 调用 on_cards_captured: screenshot={screenshot_path}, crops={list(card_data.get('card_crops', {}).keys())}")
                self.on_cards_captured(screenshot_path, card_data)
            else:
                logger.warning(f"[回调] on_cards_captured 未设置!")

        except Exception as e:
            logger.error(f"截图保存失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if self.on_card_capture_failed:
                asyncio.create_task(self._delayed_capture_failed_callback(game_number))

    async def _delayed_capture_failed_callback(self, game_number: str):
        """延迟1秒后触发截图失败回调"""
        await asyncio.sleep(1.0)
        logger.info(f"[同步] 触发路单同步 (局{game_number}牌面获取失败)")
        if self.on_card_capture_failed:
            self.on_card_capture_failed(game_number)

    def _forward_http_request(self, info: Dict):
        """转发HTTP请求回调到外部"""
        if self.on_http_request:
            self.on_http_request(info)

    def _handle_game_api(self, data: Dict):
        """处理游戏API数据"""
        result = data.get("result", "")
        oldwin = data.get("oldwin", "")
        game_id = data.get("GameID", "")
        game_status = data.get("gameStatus", "")
        game_type = data.get("gameType", "")
        xztime = data.get("xztime", "")
        xue = data.get("xue", "")

        # 更新靴号
        if xue:
            try:
                new_xue = int(xue)
                if new_xue != self.current_xue:
                    old_xue = self.current_xue
                    self.current_xue = new_xue
                    logger.info(f"[靴号] {old_xue} -> {new_xue}")
                    if self.on_xue_change:
                        self.on_xue_change(new_xue)
            except (ValueError, TypeError):
                pass

        # 解析路单数据
        results = [r for r in result.split('#') if r] if result else []
        pu_count = len(results)

        # ========== 换靴检测 ==========
        # 检测条件:
        # 1. result 为空 (新靴开始)
        # 2. 铺数大幅下降 (例如从30+变成0-5)
        if self._last_pu_count is not None:
            # 条件1: 之前有数据，现在为空
            if self._last_pu_count > 0 and pu_count == 0:
                logger.warning(f"[换靴检测] 路单清空: {self._last_pu_count} -> 0 (新靴开始)")
                self._trigger_shoe_change()

            # 条件2: 铺数大幅下降 (下降超过10铺，且当前铺数<5)
            elif self._last_pu_count > 10 and pu_count < 5 and (self._last_pu_count - pu_count) > 10:
                logger.warning(f"[换靴检测] 铺数骤降: {self._last_pu_count} -> {pu_count} (新靴开始)")
                self._trigger_shoe_change()

        # 更新上次铺数记录
        self._last_pu_count = pu_count

        # 路单数据处理 (有数据时)
        if result:
            expected_pu = pu_count + 1
            if expected_pu != self.current_pu:
                old_pu = self.current_pu
                self.current_pu = expected_pu
                logger.info(f"[铺号校准] {old_pu} -> {expected_pu} (路单已完成{pu_count}铺)")
                if self.on_pu_change:
                    self.on_pu_change(expected_pu)

            roadmap_record = {
                "game_id": game_id,
                "game_status": game_status,
                "game_type": game_type,
                "xztime": xztime,
                "xue": xue,
                "pu": expected_pu,
                "result": result,
                "result_list": results,
                "count": pu_count,
                "parsed": self._parse_roadmap_results(results)
            }

            self._write_log("http", "roadmap", roadmap_record)
            self._write_roadmap_log(roadmap_record)

        if oldwin:
            self._write_log("http", "card_info", {
                "game_id": game_id,
                "oldwin": oldwin,
                "status": game_status
            })

    def _trigger_shoe_change(self):
        """
        触发换靴处理

        当检测到源站点换靴时:
        1. 重置铺号为1
        2. 调用换靴回调 (外部执行路单同步清空数据库)
        """
        logger.info("[换靴] 触发换靴处理...")

        # 重置铺号
        old_pu = self.current_pu
        self.current_pu = 1
        logger.info(f"[换靴] 铺号重置: {old_pu} -> 1")

        # 通知铺号变化
        if self.on_pu_change:
            self.on_pu_change(1)

        # 触发换靴回调 (外部执行路单同步)
        if self.on_shoe_change:
            logger.info("[换靴] 调用换靴回调，执行路单同步...")
            self.on_shoe_change()
        else:
            logger.warning("[换靴] 未设置换靴回调，无法自动同步")

    def _parse_roadmap_results(self, results: list) -> Dict:
        """解析路单结果列表 (龙虎版本)"""
        stats = {
            "dragon": 0,   # 龙赢
            "tiger": 0,    # 虎赢
            "tie": 0,      # 和局
        }

        for r in results:
            if not r:
                continue
            first = r[0] if len(r) > 0 else '0'

            # 龙虎结果: 1=龙, 2=虎, 3=和
            if first == '1':
                stats["dragon"] += 1
            elif first == '2':
                stats["tiger"] += 1
            elif first == '3':
                stats["tie"] += 1

        return stats

    def _write_roadmap_log(self, data: Dict):
        """写入单独的 roadmap 日志文件"""
        try:
            record = {
                "timestamp": datetime.now().isoformat(),
                "table": self.current_table,
                **data
            }

            with open(self.roadmap_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            parsed = data.get('parsed', {})
            logger.info(f"[Roadmap] GameID={data.get('game_id')} 共{data.get('count')}局 | "
                       f"龙={parsed.get('dragon', 0)} 虎={parsed.get('tiger', 0)} 和={parsed.get('tie', 0)}")

        except Exception as e:
            logger.error(f"写入roadmap日志失败: {e}")

    async def take_screenshot(self, name: str = None) -> Optional[str]:
        """截图"""
        try:
            if not self._page:
                return None

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            table = self.current_table or "unknown"
            filename = f"{table}_{name}_{timestamp}.png" if name else f"{table}_{timestamp}.png"

            filepath = self.screenshot_dir / filename

            await self._page.screenshot(path=str(filepath))
            self.stats["screenshots"] += 1

            self._write_log("dom", "screenshot", {"path": str(filepath)})
            return str(filepath)

        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            "current_table": self.current_table,
            "is_running": self.is_running,
            "log_dir": str(self.log_dir)
        }

    def search_logs(self, log_type: str = None, keyword: str = None,
                    minutes: int = 20, limit: int = 100) -> List[Dict]:
        """搜索日志"""
        results = []
        cutoff = datetime.now() - timedelta(minutes=minutes)

        try:
            for log_file in sorted(self.log_dir.glob("*.jsonl"), reverse=True):
                if len(results) >= limit:
                    break

                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if len(results) >= limit:
                            break

                        try:
                            record = json.loads(line.strip())

                            ts = datetime.fromisoformat(record.get("timestamp", ""))
                            if ts < cutoff:
                                continue

                            if log_type and record.get("type") != log_type:
                                continue

                            if keyword:
                                record_str = json.dumps(record)
                                if keyword.lower() not in record_str.lower():
                                    continue

                            results.append(record)

                        except:
                            continue

        except Exception as e:
            logger.error(f"搜索日志失败: {e}")

        return results

    def get_latest_roadmap(self) -> Optional[Dict]:
        """从日志中获取最新的路单数据"""
        try:
            records = self.search_logs(log_type="roadmap_data", minutes=5, limit=1)
            if records:
                return records[0].get("data", {})

            records = self.search_logs(keyword="oldwin", minutes=5, limit=10)
            for record in records:
                data = record.get("data", {})
                if data.get("oldwin"):
                    return {
                        "desk": data.get("desk", ""),
                        "xue": data.get("xue", ""),
                        "pu": data.get("pu", ""),
                        "oldwin": data.get("oldwin", ""),
                    }

            return None

        except Exception as e:
            logger.error(f"获取路单数据失败: {e}")
            return None

    def get_all_roadmap_history(self, minutes: int = 20) -> List[Dict]:
        """获取历史路单数据"""
        results = []
        try:
            records = self.search_logs(keyword="oldwin", minutes=minutes, limit=1000)
            for record in records:
                data = record.get("data", {})
                if data.get("oldwin"):
                    results.append({
                        "timestamp": record.get("timestamp"),
                        "desk": data.get("desk", ""),
                        "xue": data.get("xue", ""),
                        "pu": data.get("pu", ""),
                        "oldwin": data.get("oldwin", ""),
                        "count": len(data.get("oldwin", "").split(",")) if data.get("oldwin") else 0
                    })

        except Exception as e:
            logger.error(f"获取路单历史失败: {e}")

        return results


# 全局单例
_monitor_instance: Optional[BrowserMonitor] = None


def get_browser_monitor() -> BrowserMonitor:
    """获取浏览器监控器单例"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = BrowserMonitor()
    return _monitor_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    monitor = BrowserMonitor()
    print(f"日志目录: {monitor.log_dir}")
    print(f"保留时间: {monitor.retention_minutes}分钟")
