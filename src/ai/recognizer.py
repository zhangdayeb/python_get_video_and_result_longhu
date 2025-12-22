# -*- coding: utf-8 -*-
"""
AI扑克牌识别器 (龙虎版本)

使用 PyTorch ResNet101 模型识别扑克牌
龙虎只需识别2张牌: 1=龙牌, 2=虎牌
"""
import logging
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Tuple
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

logger = logging.getLogger(__name__)


class PokerRecognizer:
    """扑克牌AI识别器"""

    def __init__(self, model_path: str):
        """
        初始化识别器

        Args:
            model_path: 模型文件路径
        """
        self.model_path = model_path
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # 类别标签
        self.class_names = None

        # 图像预处理
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

        # 加载模型
        self.model = self._load_model()

        if self.class_names is None:
            self.class_names = self._get_class_names()

        logger.info(f"AI模型已加载: {model_path} (设备: {self.device})")

    def _load_model(self) -> nn.Module:
        """加载PyTorch模型"""
        try:
            checkpoint = torch.load(self.model_path, map_location=self.device)

            if 'class_names' in checkpoint:
                self.class_names = checkpoint['class_names']
                num_classes = len(self.class_names)
            else:
                num_classes = 52

            model = models.resnet101(pretrained=False)
            num_features = model.fc.in_features
            model.fc = nn.Linear(num_features, num_classes)

            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                model.load_state_dict(checkpoint['model_state_dict'])
            else:
                model.load_state_dict(checkpoint)

            model.to(self.device)
            model.eval()

            logger.info(f"模型加载成功! 类别数: {num_classes}")
            return model
        except Exception as e:
            logger.error(f"加载模型失败: {e}")
            raise

    def _get_class_names(self) -> list:
        """获取52张扑克牌的类别名称"""
        suits = ['spades', 'hearts', 'clubs', 'diamonds']
        ranks = ['ace', 'two', 'three', 'four', 'five', 'six', 'seven',
                'eight', 'nine', 'ten', 'jack', 'queen', 'king']

        class_names = []
        for suit in suits:
            for rank in ranks:
                class_names.append(f"{rank} of {suit}")

        return class_names

    def predict_card(self, image_input) -> Dict[str, any]:
        """
        识别单张扑克牌

        Args:
            image_input: 图像路径(str)或PIL.Image或numpy数组

        Returns:
            {"rank": "1-13", "suit": "h/r/m/f", "confidence": 0.95, "class": "..."}
        """
        try:
            # 加载图像
            if isinstance(image_input, str):
                image = Image.open(image_input).convert('RGB')
            elif isinstance(image_input, np.ndarray):
                image = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB))
            elif isinstance(image_input, Image.Image):
                image = image_input.convert('RGB')
            else:
                raise ValueError(f"不支持的图像输入类型: {type(image_input)}")

            # 预处理
            img_tensor = self.transform(image).unsqueeze(0).to(self.device)

            # 推理
            with torch.no_grad():
                outputs = self.model(img_tensor)
                probabilities = torch.nn.functional.softmax(outputs, dim=1)
                confidence, predicted = torch.max(probabilities, 1)

            # 解析结果
            class_idx = predicted.item()
            confidence_value = confidence.item()
            class_name = self.class_names[class_idx]

            rank, suit = self._parse_class_name(class_name)

            return {
                "rank": rank,
                "suit": suit,
                "confidence": confidence_value,
                "class": class_name
            }

        except Exception as e:
            logger.error(f"AI识别失败: {e}")
            return None

    def _parse_class_name(self, class_name: str) -> Tuple[str, str]:
        """
        解析类别名称为马总格式

        Args:
            class_name: "two of spades"

        Returns:
            (rank, suit): ("2", "h")
        """
        parts = class_name.split(' of ')
        if len(parts) != 2:
            return ("0", "0")

        rank_name, suit_name = parts

        # 花色映射 (转为马总格式)
        suit_mapping = {
            'hearts': 'r',    # 红桃
            'clubs': 'm',     # 梅花
            'spades': 'h',    # 黑桃
            'diamonds': 'f'   # 方块
        }

        # 点数映射
        rank_mapping = {
            'ace': '1', 'two': '2', 'three': '3', 'four': '4',
            'five': '5', 'six': '6', 'seven': '7', 'eight': '8',
            'nine': '9', 'ten': '10', 'jack': '11', 'queen': '12', 'king': '13'
        }

        rank = rank_mapping.get(rank_name, '0')
        suit = suit_mapping.get(suit_name, '0')

        return (rank, suit)


class CardAIRecognizer:
    """卡牌AI识别接口 (兼容原OCR接口)"""

    def __init__(self, model_path: str = None):
        """
        初始化识别器

        Args:
            model_path: 模型文件路径，如果为None则自动查找
        """
        if model_path is None:
            # models 在项目根目录 (src 的上一级)
            model_path = Path(__file__).parent.parent.parent / "models" / "best_resnet101_model.pth"

        self.model_path = str(model_path)
        self.recognizer = PokerRecognizer(self.model_path)

        logger.info(f"CardAIRecognizer 已初始化")

    def recognize_from_positions(
        self,
        screenshot_path: str,
        card_positions: list,
        desk_id: int = None,
        shoe_num: int = None,
        round_num: int = None
    ) -> Optional[Dict[str, str]]:
        """
        根据 DOM 坐标从截图中识别扑克牌

        Args:
            screenshot_path: 截图文件路径
            card_positions: DOM 坐标列表

        Returns:
            {"1": "2|h", "2": "10|r", ...}
        """
        try:
            # 读取截图
            with open(screenshot_path, 'rb') as f:
                img_data = np.frombuffer(f.read(), np.uint8)
                image = cv2.imdecode(img_data, cv2.IMREAD_COLOR)

            if image is None:
                logger.error(f"无法读取截图: {screenshot_path}")
                return None

            logger.info(f"读取截图: {image.shape[1]}x{image.shape[0]}")

            # 初始化结果 (龙虎只需2张牌: 1=龙牌, 2=虎牌)
            result = {"1": "0|0", "2": "0|0"}

            # 逐张识别
            for card_pos in card_positions:
                index = str(card_pos['index'])
                x = card_pos['x']
                y = card_pos['y']
                w = card_pos['width']
                h = card_pos['height']
                direction = card_pos.get('direction', 'v')

                # 裁剪单张牌
                card_img = image[y:y+h, x:x+w]

                if card_img.size == 0:
                    logger.warning(f"牌{index}: 裁剪区域为空")
                    continue

                # 处理横牌
                if direction == 'h':
                    card_img = cv2.rotate(card_img, cv2.ROTATE_90_COUNTERCLOCKWISE)

                # AI 识别
                prediction = self.recognizer.predict_card(card_img)
                if prediction and prediction['confidence'] > 0.2:
                    result[index] = f"{prediction['rank']}|{prediction['suit']}"
                    logger.info(f"牌{index}: {result[index]} (置信度: {prediction['confidence']:.1%})")
                else:
                    logger.warning(f"牌{index}: 识别失败或置信度过低")

            logger.info(f"识别完成: 龙[{result['1']}] 虎[{result['2']}]")
            return result

        except Exception as e:
            logger.error(f"AI识别过程出错: {e}", exc_info=True)
            return None

    def recognize_from_screenshot(self, screenshot_path: str) -> Optional[Dict[str, str]]:
        """从完整截图识别2张牌 (龙虎版本)"""
        try:
            with open(screenshot_path, 'rb') as f:
                img_data = np.frombuffer(f.read(), np.uint8)
                image = cv2.imdecode(img_data, cv2.IMREAD_COLOR)

            if image is None:
                logger.error(f"无法读取截图: {screenshot_path}")
                return None

            card_images = self._extract_card_images(image)
            if not card_images:
                logger.error("未能提取到扑克牌图像")
                return None

            result = {}
            for card_idx, card_img in card_images.items():
                if card_img is None:
                    result[card_idx] = "0|0"
                    continue

                prediction = self.recognizer.predict_card(card_img)
                if prediction and prediction['confidence'] > 0.5:
                    result[card_idx] = f"{prediction['rank']}|{prediction['suit']}"
                else:
                    result[card_idx] = "0|0"

            # 龙虎只需2张牌
            for i in ['1', '2']:
                if i not in result:
                    result[i] = "0|0"

            return result

        except Exception as e:
            logger.error(f"AI识别过程出错: {e}", exc_info=True)
            return None

    def _extract_card_images(self, image: np.ndarray) -> Dict[str, Optional[np.ndarray]]:
        """从完整截图中提取2张牌的图像 (龙虎版本: 1=龙牌, 2=虎牌)"""
        height, width = image.shape[:2]

        # 龙牌位置 (左侧)
        dragon_x = int(width * 0.12)
        dragon_y = int(height * 0.80)
        dragon_w = int(width * 0.08)
        dragon_h = int(height * 0.18)

        # 虎牌位置 (右侧)
        tiger_x = int(width * 0.72)
        tiger_y = int(height * 0.80)
        tiger_w = int(width * 0.08)
        tiger_h = int(height * 0.18)

        result = {}

        # 提取龙牌
        dragon_card = image[dragon_y:dragon_y+dragon_h, dragon_x:dragon_x+dragon_w]
        if dragon_card.size > 0:
            result["1"] = dragon_card
        else:
            result["1"] = None

        # 提取虎牌
        tiger_card = image[tiger_y:tiger_y+tiger_h, tiger_x:tiger_x+tiger_w]
        if tiger_card.size > 0:
            result["2"] = tiger_card
        else:
            result["2"] = None

        return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    recognizer = CardAIRecognizer()

    screenshot = "screenshots/1.png"
    if Path(screenshot).exists():
        result = recognizer.recognize_from_screenshot(screenshot)
        print(f"\n识别结果: {result}")
    else:
        print(f"测试截图不存在: {screenshot}")
