# -*- coding: utf-8 -*-
"""
台桌信息统计面板 (龙虎版本)
"""
import tkinter as tk


class InfoPanel:
    """台桌信息统计面板"""

    def __init__(self, parent):
        """
        初始化台桌信息面板

        Args:
            parent: 父容器
        """
        self.parent = parent

        # 创建面板
        self._create_widgets()

    def _create_widgets(self):
        """创建界面组件"""
        # 台桌信息显示区域
        info_frame = tk.LabelFrame(
            self.parent,
            text="台桌信息",
            font=("Arial", 11, "bold"),
            bg="#ecf0f1",
            fg="#2c3e50"
        )
        info_frame.pack(fill=tk.X, pady=(0, 10))

        info_inner = tk.Frame(info_frame, bg="#ecf0f1")
        info_inner.pack(fill=tk.X, padx=10, pady=8)

        label_style = {"font": ("Arial", 10), "bg": "#ecf0f1", "anchor": "w"}
        value_style = {"font": ("Arial", 10, "bold"), "bg": "#ecf0f1", "fg": "#2980b9", "anchor": "w"}

        # 第一行: 台桌ID、靴号、铺号、倒计时
        tk.Label(info_inner, text="台桌ID:", **label_style).grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.lbl_desk_id = tk.Label(info_inner, text="--", width=6, **value_style)
        self.lbl_desk_id.grid(row=0, column=1, sticky="w", padx=(0, 15))

        tk.Label(info_inner, text="靴号:", **label_style).grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.lbl_shoe_num = tk.Label(info_inner, text="1", width=6, **value_style)
        self.lbl_shoe_num.grid(row=0, column=3, sticky="w", padx=(0, 15))

        tk.Label(info_inner, text="铺号:", **label_style).grid(row=0, column=4, sticky="w", padx=(0, 5))
        self.lbl_round_num = tk.Label(info_inner, text="1", width=10, **value_style)
        self.lbl_round_num.grid(row=0, column=5, sticky="w", padx=(0, 15))

        tk.Label(info_inner, text="倒计时:", **label_style).grid(row=0, column=6, sticky="w", padx=(0, 5))
        self.lbl_countdown = tk.Label(info_inner, text="--", width=6, font=("Arial", 12, "bold"), bg="#ecf0f1", fg="#e74c3c", anchor="w")
        self.lbl_countdown.grid(row=0, column=7, sticky="w")

        # 第二行: 投注状态、结果
        tk.Label(info_inner, text="投注状态:", **label_style).grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_bet_status = tk.Label(info_inner, text="--", width=12, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#27ae60", anchor="w")
        self.lbl_bet_status.grid(row=1, column=1, columnspan=2, sticky="w", padx=(0, 15), pady=(8, 0))

        tk.Label(info_inner, text="结果:", **label_style).grid(row=1, column=3, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_result = tk.Label(info_inner, text="--", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#e74c3c", anchor="w")
        self.lbl_result.grid(row=1, column=4, columnspan=4, sticky="w", pady=(8, 0))

        # 第三行: 龙牌、虎牌 (龙虎版本)
        tk.Label(info_inner, text="龙牌:", **label_style).grid(row=2, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_dragon_card = tk.Label(info_inner, text="--", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#e74c3c", anchor="w")
        self.lbl_dragon_card.grid(row=2, column=1, columnspan=2, sticky="w", pady=(8, 0))

        tk.Label(info_inner, text="虎牌:", **label_style).grid(row=2, column=3, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_tiger_card = tk.Label(info_inner, text="--", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#3498db", anchor="w")
        self.lbl_tiger_card.grid(row=2, column=4, columnspan=2, sticky="w", pady=(8, 0))

        # 第四行: 数据库连接状态
        tk.Label(info_inner, text="数据库:", **label_style).grid(row=3, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_db_status = tk.Label(info_inner, text="未连接", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#e74c3c", anchor="w")
        self.lbl_db_status.grid(row=3, column=1, sticky="w", padx=(0, 15), pady=(8, 0))

        tk.Label(info_inner, text="主机:", **label_style).grid(row=3, column=2, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_db_host = tk.Label(info_inner, text="--", width=15, **value_style)
        self.lbl_db_host.grid(row=3, column=3, columnspan=2, sticky="w", padx=(0, 15), pady=(8, 0))

        tk.Label(info_inner, text="数据库名:", **label_style).grid(row=3, column=5, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_db_name = tk.Label(info_inner, text="--", width=15, **value_style)
        self.lbl_db_name.grid(row=3, column=6, columnspan=2, sticky="w", pady=(8, 0))

        # 第五行: 同步状态
        tk.Label(info_inner, text="同步状态:", **label_style).grid(row=4, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_sync_status = tk.Label(info_inner, text="未启动", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#95a5a6", anchor="w")
        self.lbl_sync_status.grid(row=4, column=1, sticky="w", padx=(0, 15), pady=(8, 0))

        tk.Label(info_inner, text="下次同步:", **label_style).grid(row=4, column=2, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_sync_countdown = tk.Label(info_inner, text="--", width=8, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#3498db", anchor="w")
        self.lbl_sync_countdown.grid(row=4, column=3, sticky="w", padx=(0, 15), pady=(8, 0))

        tk.Label(info_inner, text="同步次数:", **label_style).grid(row=4, column=4, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_sync_count = tk.Label(info_inner, text="0", width=6, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#27ae60", anchor="w")
        self.lbl_sync_count.grid(row=4, column=5, sticky="w", padx=(0, 15), pady=(8, 0))

        # 第六行: 铺号对比
        tk.Label(info_inner, text="线上铺号:", **label_style).grid(row=5, column=0, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_online_pu = tk.Label(info_inner, text="0", width=6, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#9b59b6", anchor="w")
        self.lbl_online_pu.grid(row=5, column=1, sticky="w", padx=(0, 15), pady=(8, 0))

        tk.Label(info_inner, text="采集铺号:", **label_style).grid(row=5, column=2, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_local_pu = tk.Label(info_inner, text="0", width=6, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#3498db", anchor="w")
        self.lbl_local_pu.grid(row=5, column=3, sticky="w", padx=(0, 15), pady=(8, 0))

        tk.Label(info_inner, text="检测次数:", **label_style).grid(row=5, column=4, sticky="w", padx=(0, 5), pady=(8, 0))
        self.lbl_check_count = tk.Label(info_inner, text="0", width=6, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#f39c12", anchor="w")
        self.lbl_check_count.grid(row=5, column=5, sticky="w", padx=(0, 15), pady=(8, 0))

        # 分隔线
        separator = tk.Frame(info_inner, height=2, bg="#bdc3c7")
        separator.grid(row=6, column=0, columnspan=8, sticky="ew", pady=(12, 8))

        # 第七行: 路单采集状态
        tk.Label(info_inner, text="路单采集:", **label_style).grid(row=7, column=0, sticky="w", padx=(0, 5), pady=(4, 0))
        self.lbl_roadmap_status = tk.Label(info_inner, text="未启动", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#95a5a6", anchor="w")
        self.lbl_roadmap_status.grid(row=7, column=1, sticky="w", padx=(0, 15), pady=(4, 0))

        tk.Label(info_inner, text="账号:", **label_style).grid(row=7, column=2, sticky="w", padx=(0, 5), pady=(4, 0))
        self.lbl_roadmap_user = tk.Label(info_inner, text="--", width=12, **value_style)
        self.lbl_roadmap_user.grid(row=7, column=3, sticky="w", padx=(0, 15), pady=(4, 0))

        tk.Label(info_inner, text="运行时长:", **label_style).grid(row=7, column=4, sticky="w", padx=(0, 5), pady=(4, 0))
        self.lbl_roadmap_duration = tk.Label(info_inner, text="--", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#3498db", anchor="w")
        self.lbl_roadmap_duration.grid(row=7, column=5, sticky="w", padx=(0, 15), pady=(4, 0))

        # 第八行: FLV推流状态
        tk.Label(info_inner, text="FLV推流:", **label_style).grid(row=8, column=0, sticky="w", padx=(0, 5), pady=(4, 0))
        self.lbl_flv_status = tk.Label(info_inner, text="未启动", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#95a5a6", anchor="w")
        self.lbl_flv_status.grid(row=8, column=1, sticky="w", padx=(0, 15), pady=(4, 0))

        tk.Label(info_inner, text="账号:", **label_style).grid(row=8, column=2, sticky="w", padx=(0, 5), pady=(4, 0))
        self.lbl_flv_user = tk.Label(info_inner, text="--", width=12, **value_style)
        self.lbl_flv_user.grid(row=8, column=3, sticky="w", padx=(0, 15), pady=(4, 0))

        tk.Label(info_inner, text="速度:", **label_style).grid(row=8, column=4, sticky="w", padx=(0, 5), pady=(4, 0))
        self.lbl_flv_speed = tk.Label(info_inner, text="--", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#27ae60", anchor="w")
        self.lbl_flv_speed.grid(row=8, column=5, sticky="w", padx=(0, 15), pady=(4, 0))

        tk.Label(info_inner, text="已推送:", **label_style).grid(row=8, column=6, sticky="w", padx=(0, 5), pady=(4, 0))
        self.lbl_flv_total = tk.Label(info_inner, text="--", width=10, font=("Arial", 10, "bold"), bg="#ecf0f1", fg="#3498db", anchor="w")
        self.lbl_flv_total.grid(row=8, column=7, sticky="w", pady=(4, 0))

    # ========== 更新方法 ==========

    def update_desk_id(self, value):
        self.lbl_desk_id.config(text=str(value))

    def update_shoe_num(self, value):
        self.lbl_shoe_num.config(text=str(value))

    def update_round_num(self, value):
        self.lbl_round_num.config(text=str(value))

    def update_countdown(self, value, color=None):
        self.lbl_countdown.config(text=f"{value}秒" if isinstance(value, int) else str(value))
        if color:
            self.lbl_countdown.config(fg=color)

    def update_bet_status(self, value, color=None):
        self.lbl_bet_status.config(text=str(value))
        if color:
            self.lbl_bet_status.config(fg=color)

    def update_result(self, value, color=None):
        self.lbl_result.config(text=str(value))
        if color:
            self.lbl_result.config(fg=color)

    def update_dragon_card(self, value):
        """更新龙牌显示 (龙虎版本)"""
        self.lbl_dragon_card.config(text=str(value))

    def update_tiger_card(self, value):
        """更新虎牌显示 (龙虎版本)"""
        self.lbl_tiger_card.config(text=str(value))

    # 保留旧方法名的兼容性，映射到龙虎方法
    def update_player_cards(self, value):
        """兼容方法 - 实际更新龙牌"""
        self.update_dragon_card(value)

    def update_banker_cards(self, value):
        """兼容方法 - 实际更新虎牌"""
        self.update_tiger_card(value)

    def update_db_status(self, connected: bool, host: str = "--", database: str = "--"):
        if connected:
            self.lbl_db_status.config(text="已连接", fg="#27ae60")
        else:
            self.lbl_db_status.config(text="未连接", fg="#e74c3c")
        self.lbl_db_host.config(text=host)
        self.lbl_db_name.config(text=database)

    def update_sync_status(self, status: str, color: str):
        self.lbl_sync_status.config(text=status, fg=color)

    def update_sync_countdown(self, value):
        self.lbl_sync_countdown.config(text=f"{value}秒" if isinstance(value, int) else str(value))

    def update_sync_count(self, value):
        self.lbl_sync_count.config(text=str(value))

    def update_online_pu(self, value, color=None):
        self.lbl_online_pu.config(text=str(value))
        if color:
            self.lbl_online_pu.config(fg=color)

    def update_local_pu(self, value, color=None):
        self.lbl_local_pu.config(text=str(value))
        if color:
            self.lbl_local_pu.config(fg=color)

    def update_check_count(self, value):
        self.lbl_check_count.config(text=str(value))

    # ========== 采集状态更新方法 ==========

    def update_roadmap_status(self, status: str, color: str = None):
        """更新路单采集状态"""
        self.lbl_roadmap_status.config(text=status)
        if color:
            self.lbl_roadmap_status.config(fg=color)

    def update_roadmap_user(self, username: str):
        """更新路单采集账号"""
        self.lbl_roadmap_user.config(text=username if username else "--")

    def update_roadmap_duration(self, seconds: int):
        """更新路单采集运行时长"""
        if isinstance(seconds, int) and seconds >= 0:
            if seconds < 60:
                text = f"{seconds}秒"
            elif seconds < 3600:
                text = f"{seconds // 60}分{seconds % 60}秒"
            else:
                text = f"{seconds // 3600}时{(seconds % 3600) // 60}分"
            self.lbl_roadmap_duration.config(text=text)
        else:
            self.lbl_roadmap_duration.config(text="--")

    def update_flv_status(self, status: str, color: str = None):
        """更新FLV推流状态"""
        self.lbl_flv_status.config(text=status)
        if color:
            self.lbl_flv_status.config(fg=color)

    def update_flv_user(self, username: str):
        """更新FLV推流账号"""
        self.lbl_flv_user.config(text=username if username else "--")

    def update_flv_speed(self, speed_kbps: float):
        """更新FLV推流速度 (KB/s)"""
        if isinstance(speed_kbps, (int, float)) and speed_kbps >= 0:
            self.lbl_flv_speed.config(text=f"{speed_kbps:.1f} KB/s")
        else:
            self.lbl_flv_speed.config(text="--")

    def update_flv_total(self, total_bytes: int):
        """更新FLV已推送数据量"""
        if isinstance(total_bytes, int) and total_bytes >= 0:
            if total_bytes < 1024:
                text = f"{total_bytes} B"
            elif total_bytes < 1024 * 1024:
                text = f"{total_bytes / 1024:.1f} KB"
            else:
                text = f"{total_bytes / 1024 / 1024:.1f} MB"
            self.lbl_flv_total.config(text=text)
        else:
            self.lbl_flv_total.config(text="--")
