# -*- coding: utf-8 -*-
"""
龙虎监控系统 v5.1 - 程序入口

支持多开：python main.py --desk 1 --port 9223
"""
import tkinter as tk
from tkinter import messagebox
import sys
import argparse
import logging
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='龙虎监控系统 v5.1')
    parser.add_argument(
        '--desk',
        type=int,
        default=1,
        help='桌号 (1-28)，默认为 1'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=9223,
        help='浏览器调试端口，默认为 9223。多开时每个实例需要不同端口 (建议: 桌1=9223, 桌2=9224, ...)'
    )
    return parser.parse_args()


def setup_logging(desk_id: int):
    """配置日志，输出到实例专属目录"""
    # 创建实例目录
    base_dir = Path(__file__).parent
    log_dir = base_dir / "temp" / f"desk_{desk_id}" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(),  # 控制台输出
            logging.FileHandler(log_dir / "app.log", encoding='utf-8')  # 文件输出
        ]
    )


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()

    # 配置日志
    setup_logging(args.desk)

    logger = logging.getLogger(__name__)
    logger.info(f"启动监控系统: 桌号={args.desk}, 调试端口={args.port}")

    # 初始化进程管理器（清理旧进程、注册退出处理）
    from core.process_manager import init_process_manager
    process_manager = init_process_manager(args.desk)
    logger.info(f"进程管理器已初始化: 主进程PID={process_manager.main_pid}")

    # 设置全局运行时配置
    from core.config import config
    config.set_runtime_config(desk_id=args.desk, debug_port=args.port)

    # 创建 GUI
    root = tk.Tk()

    # 导入UI模块 (从 src 目录)
    from ui.windows_ui import MainGUI
    app = MainGUI(root, desk_id=args.desk, debug_port=args.port)

    # 将 app 的清理方法注册到进程管理器
    process_manager.add_cleanup_callback(app.emergency_cleanup)

    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        messagebox.showerror("错误", f"程序运行错误: {e}")
        sys.exit(1)
