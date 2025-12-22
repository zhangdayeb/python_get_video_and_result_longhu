# -*- coding: utf-8 -*-
"""
日志输出面板
"""
import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime


class LogPanel:
    """日志输出面板"""

    def __init__(self, parent):
        """
        初始化日志面板

        Args:
            parent: 父容器
        """
        self.parent = parent

        # 创建面板
        self._create_widgets()

    def _create_widgets(self):
        """创建界面组件"""
        # 日志标签
        log_label = tk.Label(
            self.parent,
            text="日志输出:",
            font=("Arial", 11, "bold"),
            bg="#ecf0f1",
            anchor="w"
        )
        log_label.pack(fill=tk.X, pady=(5, 3))

        # 日志文本框（可滚动）
        self.log_text = scrolledtext.ScrolledText(
            self.parent,
            font=("Consolas", 9),
            bg="#2c3e50",
            fg="#ecf0f1",
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=15
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message: str):
        """
        输出日志

        Args:
            message: 日志消息
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def clear(self):
        """清空日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
