# -*- coding: utf-8 -*-
"""
截图预览面板 (大截图 + 2张小牌) - 龙虎版本
"""
import tkinter as tk
from pathlib import Path


class PreviewPanel:
    """截图预览面板"""

    # 扑克预览尺寸 (宽x高) - 保持扑克牌比例约 2:3
    CARD_PREVIEW_WIDTH = 50
    CARD_PREVIEW_HEIGHT = 70

    def __init__(self, parent, log_callback=None):
        """
        初始化预览面板

        Args:
            parent: 父容器 (右侧区域, width=420)
            log_callback: 日志回调函数
        """
        self.parent = parent
        self.log_callback = log_callback
        self._current_screenshot_path = None
        self._card_images = {}  # 保持图片引用

        # 创建面板
        self._create_widgets()

    def _log(self, message: str):
        """输出日志"""
        if self.log_callback:
            self.log_callback(message)

    def _create_widgets(self):
        """创建界面组件"""
        # 截图预览区域
        preview_frame = tk.LabelFrame(
            self.parent,
            text="截图预览",
            font=("Arial", 11, "bold"),
            bg="#ecf0f1",
            fg="#2c3e50"
        )
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # 大截图预览（开牌牌型）- 宽度100%自适应
        big_preview_frame = tk.Frame(preview_frame, bg="#ecf0f1")
        big_preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.big_preview = tk.Label(
            big_preview_frame,
            text="开牌截图预览\n(等待截图...)",
            bg="white",
            fg="#7f8c8d",
            relief=tk.SOLID,
            bd=1,
            anchor="center"
        )
        self.big_preview.pack(fill=tk.BOTH, expand=True)

        # 绑定resize事件，用于自适应显示
        self.big_preview.bind("<Configure>", self._on_preview_resize)

        # 2个小截图预览（扑克位置）- 龙虎版本只显示2张牌
        small_preview_frame = tk.Frame(preview_frame, bg="#ecf0f1")
        small_preview_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        # 龙牌标签
        dragon_label = tk.Label(small_preview_frame, text="龙牌:", font=("Arial", 9), bg="#ecf0f1", fg="#e74c3c")
        dragon_label.grid(row=0, column=0, sticky="w", pady=(0, 3))

        # 龙牌预览 (对应 index 1)
        self.dragon_preview = tk.Canvas(
            small_preview_frame,
            width=self.CARD_PREVIEW_WIDTH,
            height=self.CARD_PREVIEW_HEIGHT,
            bg="white",
            highlightthickness=1,
            highlightbackground="#bdc3c7"
        )
        self.dragon_preview.grid(row=1, column=0, padx=4, pady=2)
        self.dragon_preview.create_text(
            self.CARD_PREVIEW_WIDTH // 2, self.CARD_PREVIEW_HEIGHT // 2,
            text="龙", fill="#7f8c8d", font=("Arial", 9),
            tags="default_text"
        )

        # 虎牌标签
        tiger_label = tk.Label(small_preview_frame, text="虎牌:", font=("Arial", 9), bg="#ecf0f1", fg="#3498db")
        tiger_label.grid(row=0, column=1, sticky="w", padx=(20, 0), pady=(0, 3))

        # 虎牌预览 (对应 index 2)
        self.tiger_preview = tk.Canvas(
            small_preview_frame,
            width=self.CARD_PREVIEW_WIDTH,
            height=self.CARD_PREVIEW_HEIGHT,
            bg="white",
            highlightthickness=1,
            highlightbackground="#bdc3c7"
        )
        self.tiger_preview.grid(row=1, column=1, padx=(24, 4), pady=2)
        self.tiger_preview.create_text(
            self.CARD_PREVIEW_WIDTH // 2, self.CARD_PREVIEW_HEIGHT // 2,
            text="虎", fill="#7f8c8d", font=("Arial", 9),
            tags="default_text"
        )

    def _on_preview_resize(self, event):
        """预览区域大小变化时重新加载图片"""
        if self._current_screenshot_path and Path(self._current_screenshot_path).exists():
            self.parent.after(100, lambda: self._reload_screenshot())

    def _reload_screenshot(self):
        """重新加载截图"""
        try:
            if self._current_screenshot_path:
                self.update_screenshot(self._current_screenshot_path)
        except:
            pass

    def update_screenshot(self, screenshot_path: str, card_data: dict = None):
        """
        更新截图预览

        Args:
            screenshot_path: 截图路径
            card_data: 牌面数据 (包含 card_crops, ai_result 等)
        """
        try:
            from PIL import Image, ImageTk

            if not screenshot_path or not Path(screenshot_path).exists():
                return

            self._current_screenshot_path = screenshot_path

            img = Image.open(screenshot_path)
            preview_width = self.big_preview.winfo_width()
            preview_height = self.big_preview.winfo_height()

            if preview_width > 1 and preview_height > 1:
                img_ratio = img.width / img.height
                preview_ratio = preview_width / preview_height

                if img_ratio > preview_ratio:
                    new_width = preview_width
                    new_height = int(preview_width / img_ratio)
                else:
                    new_height = preview_height
                    new_width = int(preview_height * img_ratio)

                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            photo = ImageTk.PhotoImage(img)
            self.big_preview.config(image=photo, text="")
            self.big_preview.image = photo

            if card_data:
                self._update_card_previews(card_data)

        except Exception as e:
            self._log(f"[预览] 更新失败: {e}")

    def _update_card_previews(self, card_data: dict):
        """更新2张扑克牌小图预览 (龙虎版本)"""
        try:
            from PIL import Image, ImageTk
            from core.config import config

            card_crops = card_data.get("card_crops", {})
            screenshot_dir = config.instance_screenshots_dir

            self._log(f"[预览] _update_card_previews: crops={list(card_crops.keys())}, dir={screenshot_dir}")

            # 龙牌 (index 1)
            dragon_filename = card_crops.get("1")
            if dragon_filename:
                crop_path = screenshot_dir / dragon_filename
                if crop_path.exists():
                    try:
                        img = Image.open(crop_path)
                        # 检查是否为横牌(宽>高)，如果是则旋转
                        if img.width > img.height:
                            img = img.rotate(90, expand=True)
                        img = img.resize((self.CARD_PREVIEW_WIDTH, self.CARD_PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        self.dragon_preview.delete("all")
                        self.dragon_preview.create_image(0, 0, anchor="nw", image=photo)
                        self._card_images["dragon"] = photo
                    except:
                        pass

            # 虎牌 (index 2)
            tiger_filename = card_crops.get("2")
            if tiger_filename:
                crop_path = screenshot_dir / tiger_filename
                if crop_path.exists():
                    try:
                        img = Image.open(crop_path)
                        # 检查是否为横牌(宽>高)，如果是则旋转
                        if img.width > img.height:
                            img = img.rotate(90, expand=True)
                        img = img.resize((self.CARD_PREVIEW_WIDTH, self.CARD_PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        self.tiger_preview.delete("all")
                        self.tiger_preview.create_image(0, 0, anchor="nw", image=photo)
                        self._card_images["tiger"] = photo
                    except:
                        pass

            self._log(f"[预览] 已加载 {len(card_crops)} 张扑克图片")

        except ImportError:
            pass
        except Exception as e:
            self._log(f"[预览] 小图更新失败: {e}")

    def display_ai_result(self, ai_result: dict):
        """
        计算AI识别结果 (龙虎版本)

        Args:
            ai_result: AI识别结果 {"1": "7|h", "2": "5|r"}
                       1=龙牌, 2=虎牌

        Returns:
            (result_text, result_color, dragon_str, tiger_str)
        """
        try:
            suit_symbols = {"h": "♠", "r": "♥", "m": "♣", "f": "♦"}
            rank_display = {"1": "A", "11": "J", "12": "Q", "13": "K"}

            def parse_card(card_str):
                if not card_str or card_str == "0|0":
                    return None, None
                parts = card_str.split("|")
                if len(parts) == 2:
                    rank, suit = parts
                    return rank, suit
                return None, None

            # 龙虎只有2张牌
            dragon_rank, dragon_suit = parse_card(ai_result.get("1", "0|0"))
            tiger_rank, tiger_suit = parse_card(ai_result.get("2", "0|0"))

            # 龙牌字符串
            dragon_str = ""
            if dragon_rank and dragon_suit:
                s = suit_symbols.get(dragon_suit, dragon_suit)
                r = rank_display.get(dragon_rank, dragon_rank)
                dragon_str = f"{s}{r}"

            # 虎牌字符串
            tiger_str = ""
            if tiger_rank and tiger_suit:
                s = suit_symbols.get(tiger_suit, tiger_suit)
                r = rank_display.get(tiger_rank, tiger_rank)
                tiger_str = f"{s}{r}"

            # 龙虎比大小 (直接比牌面点数，K>Q>J>10>...>A)
            if dragon_rank and tiger_rank:
                dragon_val = int(dragon_rank)
                tiger_val = int(tiger_rank)

                if dragon_val > tiger_val:
                    result_text = f"龙赢 {dragon_val}:{tiger_val}"
                    result_color = "#e74c3c"  # 红色
                elif tiger_val > dragon_val:
                    result_text = f"虎赢 {tiger_val}:{dragon_val}"
                    result_color = "#3498db"  # 蓝色
                else:
                    result_text = f"和局 {dragon_val}:{tiger_val}"
                    result_color = "#27ae60"  # 绿色
            else:
                result_text = "识别失败"
                result_color = "#7f8c8d"

            return result_text, result_color, dragon_str.strip(), tiger_str.strip()

        except Exception as e:
            self._log(f"[AI结果] 计算失败: {e}")
            return None, None, None, None

    def clear(self):
        """清空预览 (龙虎版本)"""
        self._current_screenshot_path = None
        self.big_preview.config(image="", text="开牌截图预览\n(等待截图...)")

        # 清空龙牌预览
        self.dragon_preview.delete("all")
        self.dragon_preview.create_text(
            self.CARD_PREVIEW_WIDTH // 2, self.CARD_PREVIEW_HEIGHT // 2,
            text="龙", fill="#7f8c8d", font=("Arial", 9),
            tags="default_text"
        )

        # 清空虎牌预览
        self.tiger_preview.delete("all")
        self.tiger_preview.create_text(
            self.CARD_PREVIEW_WIDTH // 2, self.CARD_PREVIEW_HEIGHT // 2,
            text="虎", fill="#7f8c8d", font=("Arial", 9),
            tags="default_text"
        )

        self._card_images.clear()
