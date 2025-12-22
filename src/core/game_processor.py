# -*- coding: utf-8 -*-
"""
游戏处理器模块 - 统一处理开牌流程 (龙虎版本)

流程:
1. 截图 (大图)
2. 裁剪2张扑克小图 (龙牌、虎牌)
3. AI识别
4. 计算结果 (result, ext, result_pai)
5. 发送 post_data 到后端API

调用方式:
    from core.game_processor import game_processor
    result = await game_processor.process(page, game_number, desk_id, xue, pu)
"""
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any, Callable

logger = logging.getLogger("game_processor")


class GameProcessor:
    """游戏处理器 - 处理开牌截图、识别、上报"""

    def __init__(self):
        # 截图工具 (延迟初始化)
        self._card_capture = None

        # AI识别器 (延迟初始化)
        self._card_ai = None

        # 后端API (延迟初始化)
        self._backend_api = None

        # 回调函数
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_capture_complete: Optional[Callable[[Dict], None]] = None
        self.on_recognition_complete: Optional[Callable[[Dict], None]] = None
        self.on_upload_complete: Optional[Callable[[bool, str], None]] = None

    def _init_capture(self):
        """初始化截图工具"""
        if self._card_capture is not None:
            return True

        try:
            from capture import get_card_capture
            self._card_capture = get_card_capture()
            self.log("[截图] 工具初始化成功")
            return True
        except Exception as e:
            self.log(f"[截图] 工具初始化失败: {e}")
            return False

    @property
    def screenshot_dir(self) -> Path:
        """获取截图目录 (使用实例专属目录)"""
        if self._card_capture:
            return self._card_capture.screenshot_dir
        # 使用实例专属的截图目录 (支持多开)
        from core.config import config
        return config.instance_screenshots_dir

    def log(self, message: str):
        """输出日志"""
        logger.info(message)
        # 同时输出到控制台，便于调试
        print(f"[GameProcessor] {message}")
        if self.on_log:
            self.on_log(message)

    def _init_ai(self):
        """初始化AI识别器"""
        if self._card_ai is not None:
            return True

        try:
            from ai.recognizer import CardAIRecognizer
            self._card_ai = CardAIRecognizer()
            self.log(f"[AI] 模型加载成功, 设备: {self._card_ai.recognizer.device}")
            return True
        except Exception as e:
            self.log(f"[AI] 模型加载失败: {e}")
            return False

    def _init_backend_api(self):
        """初始化后端API"""
        if self._backend_api is not None:
            return True

        try:
            from api.backend import BackendAPI
            self._backend_api = BackendAPI()
            self.log("[Backend] API初始化成功")
            return True
        except Exception as e:
            self.log(f"[Backend] API初始化失败: {e}")
            return False

    async def process(
        self,
        page,
        game_number: str,
        desk_id: int,
        xue_number: int,
        pu_number: int,
        card_positions: list = None
    ) -> Dict[str, Any]:
        """
        处理一局游戏的开牌流程

        Args:
            page: Playwright page 对象
            game_number: 局号
            desk_id: 桌号 (1-6)
            xue_number: 靴号
            pu_number: 铺号
            card_positions: 牌面坐标列表 (用于备用裁剪)

        Returns:
            {
                "success": bool,
                "screenshot_path": str,
                "card_crops": {"1": "xxx.png", ...},
                "ai_result": {"1": "3|h", ...},
                "result": str,  # 1=龙, 2=虎, 3=和
                "ext": str,     # 固定为0 (龙虎无对子)
                "result_pai": {"1": "3|h", ...},
                "upload_success": bool,
                "error": str (可选)
            }
        """
        result = {
            "success": False,
            "screenshot_path": None,
            "card_crops": {},
            "ai_result": None,
            "result": None,
            "ext": None,
            "result_pai": None,
            "upload_success": False,
            "is_simulated": 0  # 0=真实数据, 1=模拟数据
        }

        try:
            # 初始化截图工具
            if not self._init_capture():
                result["error"] = "截图工具初始化失败"
                return result

            # 获取台号名称 (如 F1)
            desk_name = self._get_desk_name(desk_id)
            filename_base = f"{desk_name}_game{game_number}"

            # === 步骤1+2: 截取大图和2张小图 (龙牌、虎牌) ===
            self.log(f"[处理] 开始处理局号 {game_number}")
            capture_result = await self._card_capture.capture_all(page, filename_base, card_positions)

            if not capture_result.get("success"):
                result["error"] = capture_result.get("error", "截图失败")
                return result

            screenshot_path = capture_result["screenshot_path"]
            card_crops = capture_result["card_crops"]

            result["screenshot_path"] = screenshot_path
            result["card_crops"] = card_crops

            self.log(f"[处理] 截图完成: 大图 + {len(card_crops)} 张扑克")

            # === 步骤3: AI识别 ===
            ai_result = self._recognize_cards(card_crops)
            result["ai_result"] = ai_result
            if not ai_result:
                result["error"] = "AI识别失败"
                return result

            self.log(f"[处理] AI识别完成: {ai_result}")

            # 回调通知
            if self.on_recognition_complete:
                self.on_recognition_complete(ai_result)

            # === 步骤4: 计算结果 ===
            calc_result = self._calculate_result(ai_result)
            if not calc_result:
                result["error"] = "计算结果失败"
                return result

            result["result"] = calc_result["result"]
            result["ext"] = calc_result["ext"]
            result["result_pai"] = ai_result  # AI识别结果就是 result_pai

            self.log(f"[处理] 计算结果: result={result['result']}, ext={result['ext']}")

            # === 步骤5: 发送到后端API ===
            upload_success = await self._send_to_backend(
                desk_id=desk_id,
                xue_number=xue_number,
                pu_number=pu_number,
                result=result["result"],
                ext=result["ext"],
                pai_result=ai_result,
                is_simulated=0
            )
            result["upload_success"] = upload_success
            result["success"] = True
            result["is_simulated"] = 0

            if self.on_upload_complete:
                self.on_upload_complete(upload_success, "" if upload_success else "上传失败")

            return result

        except Exception as e:
            self.log(f"[处理] 异常: {e}")
            result["error"] = str(e)

            # ========== 降级方案: 识别失败时仍然发送数据 ==========
            self.log(f"[降级] 尝试使用降级方案发送数据...")
            try:
                fallback = await self._get_fallback_data(desk_id)
                if fallback:
                    result["result"] = fallback["result"]
                    result["ext"] = fallback["ext"]
                    result["result_pai"] = fallback["result_pai"]
                    result["is_simulated"] = 1

                    upload_success = await self._send_to_backend(
                        desk_id=desk_id,
                        xue_number=xue_number,
                        pu_number=pu_number,
                        result=fallback["result"],
                        ext=fallback["ext"],
                        pai_result=fallback["result_pai"],
                        is_simulated=1
                    )
                    result["upload_success"] = upload_success
                    self.log(f"[降级] ✓ 降级数据发送{'成功' if upload_success else '失败'}: result={fallback['result']}, is_simulated=1")
                else:
                    # 连降级方案都失败，使用默认值
                    default_pai = self._get_default_pai()
                    result["result"] = "1"  # 默认龙赢
                    result["ext"] = "0"
                    result["result_pai"] = default_pai
                    result["is_simulated"] = 1

                    upload_success = await self._send_to_backend(
                        desk_id=desk_id,
                        xue_number=xue_number,
                        pu_number=pu_number,
                        result="1",
                        ext="0",
                        pai_result=default_pai,
                        is_simulated=1
                    )
                    result["upload_success"] = upload_success
                    self.log(f"[降级] ✓ 默认数据发送{'成功' if upload_success else '失败'}: is_simulated=1")
            except Exception as fallback_err:
                self.log(f"[降级] ✗ 降级方案失败: {fallback_err}")

            return result

    def _recognize_cards(self, card_crops: Dict[str, str]) -> Optional[Dict[str, str]]:
        """
        使用AI识别扑克牌

        Args:
            card_crops: {"1": "F1_game123_card1.png", ...}

        Returns:
            {"1": "3|h", "2": "10|r", ...}
        """
        if not card_crops:
            return None

        # 初始化AI
        if not self._init_ai():
            return None

        try:
            from PIL import Image

            result = {}
            for index, crop_filename in card_crops.items():
                crop_path = self.screenshot_dir / crop_filename

                if not crop_path.exists():
                    result[index] = "0|0"
                    continue

                try:
                    # 加载图片
                    img = Image.open(crop_path)

                    # 如果是横牌(宽>高)，旋转90度
                    if img.width > img.height:
                        img = img.rotate(90, expand=True)

                    # AI识别
                    prediction = self._card_ai.recognizer.predict_card(img)

                    if prediction and prediction.get('confidence', 0) > 0.2:
                        rank = prediction['rank']
                        suit = prediction['suit']
                        result[index] = f"{rank}|{suit}"
                        self.log(f"[AI] 牌{index}: {rank}|{suit} ({prediction['confidence']:.1%})")
                    else:
                        result[index] = "0|0"
                        self.log(f"[AI] 牌{index}: 识别失败")

                except Exception as e:
                    self.log(f"[AI] 牌{index}: 异常 - {e}")
                    result[index] = "0|0"

            return result

        except Exception as e:
            self.log(f"[AI] 识别异常: {e}")
            return None

    def _calculate_result(self, ai_result: Dict[str, str]) -> Optional[Dict[str, str]]:
        """
        根据AI识别结果计算龙虎结果

        龙虎比大小规则:
        - 只比较2张牌的点数大小
        - 点数大小: K(13) > Q(12) > J(11) > 10 > 9 > 8 > 7 > 6 > 5 > 4 > 3 > 2 > A(1)
        - 龙虎无对子概念

        Args:
            ai_result: {"1": "7|h", "2": "1|r"}
                       1: 龙牌, 2: 虎牌

        Returns:
            {"result": "1", "ext": "0"}
            result: 1=龙赢, 2=虎赢, 3=和局
            ext: 固定为0 (龙虎无对子)
        """
        def parse_rank(card_str):
            """解析牌点数"""
            if not card_str or card_str == "0|0":
                return None
            try:
                rank_str = card_str.split("|")[0]
                return int(rank_str)
            except:
                return None

        # 龙虎只有2张牌: 1=龙牌, 2=虎牌
        dragon_rank = parse_rank(ai_result.get("1", "0|0"))
        tiger_rank = parse_rank(ai_result.get("2", "0|0"))

        # 检查是否有足够的牌
        if dragon_rank is None or tiger_rank is None:
            self.log(f"[计算] 龙虎牌数不足: 龙={dragon_rank}, 虎={tiger_rank}")
            return None

        # 龙虎比大小 (直接比牌面点数)
        if dragon_rank > tiger_rank:
            result = "1"  # 龙赢
        elif tiger_rank > dragon_rank:
            result = "2"  # 虎赢
        else:
            result = "3"  # 和局

        self.log(f"[计算] 龙{dragon_rank}点 vs 虎{tiger_rank}点 -> result={result}")

        return {"result": result, "ext": "0"}  # 龙虎无对子，ext固定为0

    async def _get_fallback_data(self, desk_id: int) -> Optional[Dict]:
        """
        获取降级数据 - 从利博路单获取真实结果 + 生成模拟牌型

        Args:
            desk_id: 桌号

        Returns:
            {"result": "1", "ext": "0", "result_pai": {...}} 或 None
        """
        try:
            # 尝试从利博API获取最新路单
            from api.libo_fetcher import LiboFetcher

            fetcher = LiboFetcher()
            roadmap_data = await fetcher.fetch_roadmap(desk_id)

            if not roadmap_data or not roadmap_data.get("results"):
                self.log(f"[降级] 无法获取路单数据")
                return None

            # 获取最新一条结果
            latest = roadmap_data["results"][-1] if roadmap_data["results"] else None
            if not latest:
                return None

            # 转换利博格式到马总格式
            result, ext = self._convert_libo_result(latest)

            # 生成模拟牌型
            result_pai = self._generate_simulated_pai(result, ext)

            self.log(f"[降级] 从路单获取: result={result}, ext={ext}")
            return {
                "result": result,
                "ext": ext,
                "result_pai": result_pai
            }
        except Exception as e:
            self.log(f"[降级] 获取降级数据失败: {e}")
            return None

    def _convert_libo_result(self, libo_code: str) -> tuple:
        """
        转换利博路单格式到马总格式 (龙虎版本)

        龙虎利博格式: a(龙), b(虎), c(和)
        马总格式: result(1=龙,2=虎,3=和), ext(固定为0)
        """
        code = libo_code.lower() if libo_code else "a"

        result_map = {
            'a': ('1', '0'),  # 龙赢
            'b': ('2', '0'),  # 虎赢
            'c': ('3', '0'),  # 和
        }

        return result_map.get(code, ('1', '0'))

    def _generate_simulated_pai(self, result: str, ext: str) -> Dict[str, str]:
        """
        根据开牌结果生成模拟牌型数据 (龙虎版本)

        龙虎只需要2张牌，无对子概念

        Args:
            result: "1"=龙赢, "2"=虎赢, "3"=和
            ext: 固定为"0" (龙虎无对子)

        Returns:
            {"1": "13|h", "2": "10|r"}  龙牌和虎牌
        """
        # 龙虎模拟牌型 - 只需2张牌
        base_pai = {
            "1": {  # 龙赢 (K > 10)
                "dragon": "13|h",  # 龙: K黑桃
                "tiger": "10|r",   # 虎: 10红桃
            },
            "2": {  # 虎赢 (8 < Q)
                "dragon": "8|h",   # 龙: 8黑桃
                "tiger": "12|r",   # 虎: Q红桃
            },
            "3": {  # 和局 (7 = 7)
                "dragon": "7|h",   # 龙: 7黑桃
                "tiger": "7|r",    # 虎: 7红桃
            }
        }

        base = base_pai.get(result, base_pai["1"])

        return {
            "1": base["dragon"],
            "2": base["tiger"]
        }

    def _get_default_pai(self) -> Dict[str, str]:
        """获取默认牌型数据 (龙虎版本 - 当所有方案都失败时使用)"""
        return {
            "1": "0|0", "2": "0|0"  # 龙虎只需2张牌
        }

    async def _send_to_backend(
        self,
        desk_id: int,
        xue_number: int,
        pu_number: int,
        result: str,
        ext: str,
        pai_result: Dict[str, str],
        is_simulated: int = 0
    ) -> bool:
        """
        发送开牌数据到后端API

        Args:
            desk_id: 桌号
            xue_number: 靴号
            pu_number: 铺号
            result: 结果 (1=龙, 2=虎, 3=和)
            ext: 固定为0 (龙虎无对子)
            pai_result: 牌面数据
            is_simulated: 是否模拟数据 (0=真实, 1=模拟)

        Returns:
            是否成功
        """
        # 初始化API
        if not self._init_backend_api():
            self.log("[Backend] API初始化失败，无法发送数据")
            return False

        # 补全 pai_result 的默认值（龙虎只需2张牌: 1=龙牌, 2=虎牌）
        default_pai = {
            "1": "0|0",  # 龙牌
            "2": "0|0"   # 虎牌
        }
        # 用实际识别结果覆盖默认值
        complete_pai = {**default_pai, **pai_result}

        sim_tag = "[模拟]" if is_simulated else ""
        self.log(f"[Backend] {sim_tag}准备发送: 桌{desk_id}, 靴{xue_number}, 铺{pu_number}, 结果{result}|{ext}, 牌={complete_pai}")

        try:
            response = await self._backend_api.send_open_card(
                desk_id=desk_id,
                xue_number=xue_number,
                pu_number=pu_number,
                result=result,
                ext=ext,
                pai_result=complete_pai,
                is_simulated=is_simulated
            )

            if response.success:
                self.log(f"[Backend] ✓ 发送成功: 桌{desk_id}, 靴{xue_number}, 铺{pu_number}, 结果{result}|{ext}")
                self.log(f"[Backend] 响应: {response.data[:100] if response.data else 'empty'}")
                return True
            else:
                self.log(f"[Backend] ✗ 发送失败: {response.error}")
                return False

        except Exception as e:
            self.log(f"[Backend] ✗ 发送异常: {e}")
            import traceback
            self.log(f"[Backend] 堆栈: {traceback.format_exc()}")
            return False

    def _get_desk_name(self, desk_id: int) -> str:
        """获取台号名称 (如 1 -> F1)"""
        from core.config import config
        desk_names = config.get("desk_names", {})
        return desk_names.get(str(desk_id), f"T{desk_id}")


# 全局单例
game_processor = GameProcessor()
