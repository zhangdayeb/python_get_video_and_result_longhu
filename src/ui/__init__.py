# -*- coding: utf-8 -*-
"""
UI模块

包含以下组件:
- MainGUI: 主界面
- InfoPanel: 台桌信息统计面板
- LogPanel: 日志输出面板
- PreviewPanel: 截图预览面板
"""
from .windows_ui import MainGUI
from .info_panel import InfoPanel
from .log_panel import LogPanel
from .preview_panel import PreviewPanel

__all__ = ['MainGUI', 'InfoPanel', 'LogPanel', 'PreviewPanel']
