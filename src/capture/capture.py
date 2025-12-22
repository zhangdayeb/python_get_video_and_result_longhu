# -*- coding: utf-8 -*-
"""
截图和牌面裁剪模块 (龙虎版本)

功能:
1. capture_full_page() - 截取页面大图
2. capture_card_elements() - 截取2张扑克小图 (龙牌、虎牌)
3. capture_all() - 一次性完成大图+小图截取
4. crop_cards_from_positions() - 根据坐标从大图裁剪小图 (备用方案)
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CardCapture:
    """牌面截图和裁剪工具"""

    # 扑克牌选择器（备用方案）- 龙虎版本
    # 龙牌: .dragon-result-group .card1 (index 1)
    # 虎牌: .tiger-result-group .card1 (index 2)
    CARD_SELECTORS = [
        (1, ".d-card-result-root.card-result .dragon-result-group .card1"),
        (2, ".d-card-result-root.card-result .tiger-result-group .card1"),
    ]

    def __init__(self, screenshot_dir: str = None):
        """
        初始化

        Args:
            screenshot_dir: 截图保存目录，如果不指定则使用实例专属目录
        """
        if screenshot_dir:
            self.screenshot_dir = Path(screenshot_dir)
        else:
            # 使用实例专属的截图目录 (支持多开)
            from core.config import config
            self.screenshot_dir = config.instance_screenshots_dir

        # 从配置文件加载固定坐标
        self._load_card_positions()

        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def _load_card_positions(self):
        """从配置文件加载固定坐标"""
        try:
            from core.config import config
            positions = config.get("screenshot.card_positions", [])
            if positions:
                self.card_positions = positions
                logger.info(f"[截图] 从配置加载 {len(positions)} 个牌位坐标")
            else:
                # 默认坐标（兜底）- 龙虎只需2张牌，基于1280x720分辨率
                self.card_positions = [
                    {"index": 1, "name": "龙", "x": 296, "y": 577, "width": 87, "height": 123, "direction": "v"},
                    {"index": 2, "name": "虎", "x": 897, "y": 577, "width": 87, "height": 123, "direction": "v"},
                ]
                logger.info("[截图] 使用默认牌位坐标 (龙虎2张牌)")
        except Exception as e:
            logger.error(f"[截图] 加载配置失败: {e}，使用默认坐标")
            self.card_positions = [
                {"index": 1, "name": "龙", "x": 296, "y": 577, "width": 87, "height": 123, "direction": "v"},
                {"index": 2, "name": "虎", "x": 897, "y": 577, "width": 87, "height": 123, "direction": "v"},
            ]

    async def capture_full_page(self, page, filename: str = None) -> Optional[str]:
        """
        截取页面大图

        Args:
            page: Playwright page 对象
            filename: 文件名 (不含路径和扩展名)

        Returns:
            截图文件完整路径，失败返回 None
        """
        try:
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}"

            screenshot_path = self.screenshot_dir / f"{filename}.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)

            logger.info(f"[截图] 大图保存: {screenshot_path.name}")
            return str(screenshot_path)

        except Exception as e:
            logger.error(f"[截图] 大图失败: {e}")
            return None

    async def capture_card_elements(self, page, filename_base: str) -> Dict[str, str]:
        """
        直接对每张扑克元素截图

        Args:
            page: Playwright page 对象
            filename_base: 文件名基础部分 (如 "F1_game123")

        Returns:
            {"1": "F1_game123_card1.png", "2": "F1_game123_card2.png", ...}
        """
        card_crops = {}

        for index, selector in self.CARD_SELECTORS:
            try:
                element = page.locator(selector)
                count = await element.count()

                if count == 0:
                    continue

                is_visible = await element.is_visible()
                if not is_visible:
                    continue

                # 对元素截图
                crop_filename = f"{filename_base}_card{index}.png"
                crop_path = self.screenshot_dir / crop_filename

                await element.screenshot(path=str(crop_path))
                card_crops[str(index)] = crop_filename
                logger.debug(f"[截图] 牌{index}: {crop_filename}")

            except Exception as e:
                logger.warning(f"[截图] 牌{index}: 失败 - {e}")
                continue

        logger.info(f"[截图] 完成裁剪 {len(card_crops)} 张扑克")
        return card_crops

    async def capture_all(self, page, filename_base: str, card_positions: List[Dict] = None) -> Dict[str, Any]:
        """
        一次性完成大图和2张小图的截取 (龙虎版本)

        使用固定坐标裁剪（最可靠），根据DOM数据判断哪些牌存在

        Args:
            page: Playwright page 对象
            filename_base: 文件名基础部分 (如 "F1_game123")
            card_positions: 牌面数据列表 (用于判断哪些牌存在)

        Returns:
            {
                "success": bool,
                "screenshot_path": str,  # 大图路径
                "card_crops": {"1": "xxx.png", ...},  # 小图文件名
                "error": str (可选)
            }
        """
        result = {
            "success": False,
            "screenshot_path": None,
            "card_crops": {},
        }

        # 1. 截取大图
        screenshot_path = await self.capture_full_page(page, filename_base)
        if not screenshot_path:
            result["error"] = "截取大图失败"
            return result
        result["screenshot_path"] = screenshot_path

        # 2. 判断哪些牌存在（根据DOM数据的class属性）
        # class 为 "h_" 或 "v_"（后面没有数字）表示该位置没有牌
        existing_cards = set()
        if card_positions:
            for pos in card_positions:
                card_class = pos.get("class", "")
                index = pos.get("index")
                # 有牌面数据：class 如 "v_3126" 或 "h_2125"（后面有4位hex）
                if card_class and card_class not in ["h_", "v_", ""]:
                    existing_cards.add(index)

        # 如果没有DOM数据，默认裁剪龙虎2张牌 (1=龙牌, 2=虎牌)
        if not existing_cards:
            existing_cards = {1, 2}
            logger.info(f"[截图] 无DOM数据，使用默认牌位: {existing_cards} (龙虎)")
        else:
            logger.info(f"[截图] 根据DOM数据，存在的牌位: {existing_cards}")

        # 3. 使用固定坐标裁剪存在的牌
        card_crops = self.crop_cards_with_fixed_positions(screenshot_path, filename_base, existing_cards)
        logger.info(f"[截图] 固定坐标裁剪完成: {len(card_crops)} 张")

        # 4. 如果固定坐标裁剪不足，尝试元素截图补充 (龙虎需要2张牌)
        if len(card_crops) < min(2, len(existing_cards)):
            logger.info(f"[截图] 固定坐标裁剪只有{len(card_crops)}张，尝试元素截图补充")
            element_crops = await self.capture_card_elements(page, filename_base)

            for idx, filename in element_crops.items():
                if idx not in card_crops and int(idx) in existing_cards:
                    card_crops[idx] = filename
                    logger.info(f"[截图] 牌{idx}: 使用元素截图补充")

        if not card_crops:
            result["error"] = "截取小图失败"
            return result
        result["card_crops"] = card_crops

        result["success"] = True
        return result

    def crop_cards_with_fixed_positions(
        self,
        screenshot_path: str,
        filename_base: str,
        existing_cards: set
    ) -> Dict[str, str]:
        """
        使用固定坐标从截图中裁剪扑克牌

        Args:
            screenshot_path: 截图文件路径
            filename_base: 文件名基础部分 (如 "F1_game123")
            existing_cards: 存在的牌位集合 {1, 2, 4, 5} 等

        Returns:
            {"1": "F1_game123_card1.png", ...}
        """
        try:
            # 读取截图
            with open(screenshot_path, 'rb') as f:
                img_data = np.frombuffer(f.read(), np.uint8)
                image = cv2.imdecode(img_data, cv2.IMREAD_COLOR)

            if image is None:
                logger.error(f"无法读取截图: {screenshot_path}")
                return {}

            crops = {}
            img_height, img_width = image.shape[:2]

            for pos in self.card_positions:
                index = pos["index"]

                # 只裁剪存在的牌
                if index not in existing_cards:
                    continue

                x = pos["x"]
                y = pos["y"]
                w = pos["width"]
                h = pos["height"]
                direction = pos["direction"]

                # 检查坐标是否在图片范围内
                if x < 0 or y < 0 or x + w > img_width or y + h > img_height:
                    logger.warning(f"牌{index}: 坐标超出图片范围 (img={img_width}x{img_height}, crop=({x},{y},{w},{h}))")
                    continue

                # 裁剪
                card_img = image[y:y+h, x:x+w]

                if card_img.size == 0:
                    logger.warning(f"牌{index}: 裁剪区域为空")
                    continue

                # 横牌旋转成竖的
                if direction == 'h':
                    card_img = cv2.rotate(card_img, cv2.ROTATE_90_COUNTERCLOCKWISE)

                # 保存 (使用 imencode 避免中文路径问题)
                filename = f"{filename_base}_card{index}.png"
                filepath = self.screenshot_dir / filename

                # cv2.imwrite 在 Windows 中文路径下会失败，使用 imencode + 手动写入
                success, encoded = cv2.imencode('.png', card_img)
                if success:
                    filepath.write_bytes(encoded.tobytes())
                    crops[str(index)] = filename
                    logger.debug(f"牌{index}: 固定坐标裁剪成功 {filename}")
                else:
                    logger.warning(f"牌{index}: 图片编码失败")

            return crops

        except Exception as e:
            logger.error(f"固定坐标裁剪失败: {e}")
            return {}

    def crop_cards_from_positions(
        self,
        screenshot_path: str,
        card_positions: List[Dict],
        filename_base: str = None
    ) -> Dict[str, str]:
        """
        根据坐标从截图中裁剪扑克牌

        Args:
            screenshot_path: 截图文件路径
            card_positions: 牌面坐标列表
                [{"index": 1, "x": 100, "y": 200, "width": 50, "height": 70, "direction": "v", "class": "v_3126"}, ...]
            filename_base: 文件名基础部分 (如 "F1_game123")

        Returns:
            {"1": "F1_game123_card1.png", ...}
        """
        try:
            # 读取截图
            with open(screenshot_path, 'rb') as f:
                img_data = np.frombuffer(f.read(), np.uint8)
                image = cv2.imdecode(img_data, cv2.IMREAD_COLOR)

            if image is None:
                logger.error(f"无法读取截图: {screenshot_path}")
                return {}

            crops = {}

            # 从截图路径提取文件名基础部分
            if not filename_base:
                filename_base = Path(screenshot_path).stem

            for pos in card_positions:
                index = str(pos.get('index', 0))
                x = int(pos.get('x', 0))
                y = int(pos.get('y', 0))
                w = int(pos.get('width', 0))
                h = int(pos.get('height', 0))
                direction = pos.get('direction', 'v')
                card_class = pos.get('class', '')

                # 检查是否有牌面数据（class 不为空且不是 "h_" 或 "v_"）
                # h_ 或 v_ 后面没有数字表示该位置没有牌
                if card_class in ['h_', 'v_', '']:
                    logger.debug(f"牌{index}: 跳过（无牌面数据 class={card_class}）")
                    continue

                # 检查坐标是否有效（负数坐标表示元素在视口外）
                if x < 0 or y < 0:
                    logger.warning(f"牌{index}: 跳过（坐标无效 x={x}, y={y}）")
                    continue

                # 检查坐标是否超出图片范围
                img_height, img_width = image.shape[:2]
                if x + w > img_width or y + h > img_height:
                    logger.warning(f"牌{index}: 跳过（坐标超出图片范围 x={x}+{w}>{img_width} or y={y}+{h}>{img_height}）")
                    continue

                # 裁剪
                card_img = image[y:y+h, x:x+w]

                if card_img.size == 0:
                    logger.warning(f"牌{index}: 裁剪区域为空")
                    continue

                # 横牌旋转
                if direction == 'h':
                    card_img = cv2.rotate(card_img, cv2.ROTATE_90_COUNTERCLOCKWISE)

                # 保存 (使用 imencode 避免中文路径问题)
                filename = f"{filename_base}_card{index}.png"
                filepath = self.screenshot_dir / filename

                success, encoded = cv2.imencode('.png', card_img)
                if success:
                    filepath.write_bytes(encoded.tobytes())
                    crops[index] = filename
                    logger.debug(f"牌{index}: 已裁剪保存 {filename} (class={card_class})")
                else:
                    logger.warning(f"牌{index}: 图片编码失败")

            return crops

        except Exception as e:
            logger.error(f"裁剪牌面失败: {e}")
            return {}

    def save_screenshot(self, image_bytes: bytes, prefix: str = "screenshot") -> Optional[str]:
        """
        保存截图 (从bytes数据保存)

        Args:
            image_bytes: 图片数据
            prefix: 文件名前缀

        Returns:
            文件路径
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}.png"
            filepath = self.screenshot_dir / filename

            with open(filepath, 'wb') as f:
                f.write(image_bytes)

            logger.info(f"截图已保存: {filename}")
            return str(filepath)

        except Exception as e:
            logger.error(f"保存截图失败: {e}")
            return None

    def clean_old_screenshots(self, keep_hours: int = 24):
        """
        清理旧截图

        Args:
            keep_hours: 保留小时数
        """
        import time

        now = time.time()
        cutoff = now - (keep_hours * 3600)

        count = 0
        for f in self.screenshot_dir.glob("*.png"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                count += 1

        if count > 0:
            logger.info(f"已清理 {count} 个旧截图")


# 全局单例
_capture_instance: Optional[CardCapture] = None


def get_card_capture() -> CardCapture:
    """获取截图工具单例"""
    global _capture_instance
    if _capture_instance is None:
        _capture_instance = CardCapture()
    return _capture_instance
