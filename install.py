# -*- coding: utf-8 -*-
"""
龙虎监控系统 - 环境安装脚本

功能：
1. 检查 Python 版本（建议 3.10+）
2. 安装所有依赖包
3. 安装 Playwright 浏览器
4. 验证环境配置
5. 测试数据库连接

使用方法：
    python install.py          # 完整安装
    python install.py --check  # 仅检查环境
    python install.py --deps   # 仅安装依赖
"""

import subprocess
import sys
import os
import platform
import json
from pathlib import Path


# 颜色输出（Windows 支持）
class Colors:
    """控制台颜色"""

    @staticmethod
    def init():
        """Windows 启用 ANSI 颜色"""
        if platform.system() == 'Windows':
            os.system('color')

    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """打印标题"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}{Colors.RESET}\n")


def print_success(text):
    """打印成功信息"""
    print(f"{Colors.GREEN}[OK] {text}{Colors.RESET}")


def print_warning(text):
    """打印警告信息"""
    print(f"{Colors.YELLOW}[!] {text}{Colors.RESET}")


def print_error(text):
    """打印错误信息"""
    print(f"{Colors.RED}[X] {text}{Colors.RESET}")


def print_info(text):
    """打印信息"""
    print(f"{Colors.CYAN}[*] {text}{Colors.RESET}")


def run_command(cmd, description=None, capture=False):
    """运行命令"""
    if description:
        print_info(description)

    try:
        if capture:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            return result.returncode == 0, result.stdout, result.stderr
        else:
            result = subprocess.run(cmd, shell=True)
            return result.returncode == 0, "", ""
    except Exception as e:
        return False, "", str(e)


def check_python_version():
    """检查 Python 版本"""
    print_header("检查 Python 版本")

    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    print_info(f"当前 Python 版本: {version_str}")
    print_info(f"Python 路径: {sys.executable}")

    # 检查版本要求
    if version.major < 3:
        print_error("需要 Python 3.x，当前版本太旧")
        return False

    if version.minor < 9:
        print_warning(f"Python {version_str} 版本较低，建议升级到 3.10+")
        print_warning("某些功能可能不兼容")

        # 提供升级建议
        print("\n升级方法：")
        print("  1. 访问 https://www.python.org/downloads/")
        print("  2. 下载 Python 3.11 或 3.12")
        print("  3. 安装时勾选 'Add Python to PATH'")
        print("  4. 重新运行此脚本")

        response = input("\n是否继续安装？(y/n): ").strip().lower()
        if response != 'y':
            return False
    else:
        print_success(f"Python 版本 {version_str} 满足要求")

    return True


def check_pip():
    """检查 pip"""
    print_header("检查 pip")

    success, stdout, _ = run_command(
        f'"{sys.executable}" -m pip --version',
        "检查 pip 版本",
        capture=True
    )

    if success:
        print_success(f"pip 可用: {stdout.strip()}")

        # 升级 pip
        print_info("升级 pip 到最新版本...")
        run_command(f'"{sys.executable}" -m pip install --upgrade pip')
        return True
    else:
        print_error("pip 不可用")
        return False


def install_dependencies():
    """安装依赖包"""
    print_header("安装依赖包")

    requirements_file = Path(__file__).parent / "requirements.txt"

    if not requirements_file.exists():
        print_error(f"找不到 requirements.txt: {requirements_file}")
        return False

    print_info(f"依赖文件: {requirements_file}")

    # 读取并显示依赖
    with open(requirements_file, 'r', encoding='utf-8') as f:
        content = f.read()

    print("\n依赖包列表：")
    for line in content.strip().split('\n'):
        if line.strip() and not line.startswith('#'):
            print(f"  - {line.strip()}")

    print()

    # 安装 PyTorch（特殊处理，优先使用 CPU 版本以减小体积）
    print_info("检查 PyTorch...")
    success, stdout, _ = run_command(
        f'"{sys.executable}" -c "import torch; print(torch.__version__)"',
        capture=True
    )

    if not success:
        print_info("安装 PyTorch (CPU 版本)...")
        # 使用官方推荐的 CPU 版本安装方式
        torch_cmd = f'"{sys.executable}" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu'
        success, _, stderr = run_command(torch_cmd)

        if not success:
            print_warning("PyTorch CPU 版本安装失败，尝试默认安装...")
            run_command(f'"{sys.executable}" -m pip install torch torchvision')
    else:
        print_success(f"PyTorch 已安装: {stdout.strip()}")

    # 安装其他依赖
    print_info("安装其他依赖包...")

    # 逐个安装以便显示进度
    packages = [
        ("aiohttp", "HTTP 异步请求"),
        ("requests", "HTTP 同步请求"),
        ("playwright", "浏览器自动化"),
        ("pymysql", "MySQL 数据库"),
        ("aiomysql", "MySQL 异步"),
        ("aiosqlite", "SQLite 异步"),
        ("opencv-python", "图像处理 (OpenCV)"),
        ("Pillow", "图像处理 (PIL)"),
        ("psutil", "系统进程监控"),
        ("python-dateutil", "日期时间工具"),
    ]

    failed = []
    for package, desc in packages:
        print_info(f"安装 {package} ({desc})...")
        success, _, _ = run_command(
            f'"{sys.executable}" -m pip install {package}',
            capture=True
        )
        if success:
            print_success(f"  {package} 安装成功")
        else:
            print_error(f"  {package} 安装失败")
            failed.append(package)

    if failed:
        print_warning(f"以下包安装失败: {', '.join(failed)}")
        return False

    print_success("所有依赖包安装完成")
    return True


def install_playwright_browser():
    """安装 Playwright 浏览器"""
    print_header("安装 Playwright 浏览器")

    print_info("安装 Chromium 浏览器（约 200MB）...")

    success, _, stderr = run_command(
        f'"{sys.executable}" -m playwright install chromium',
        capture=True
    )

    if success:
        print_success("Chromium 浏览器安装成功")
        return True
    else:
        print_error(f"Chromium 安装失败: {stderr}")
        print_info("可以手动运行: python -m playwright install chromium")
        return False


def verify_imports():
    """验证所有模块可以导入"""
    print_header("验证模块导入")

    # 必需模块（安装失败会导致系统无法运行）
    required_modules = [
        ("aiohttp", "HTTP 异步"),
        ("requests", "HTTP 同步"),
        ("playwright.async_api", "Playwright"),
        ("pymysql", "MySQL"),
        ("cv2", "OpenCV"),
        ("PIL", "Pillow"),
        ("psutil", "系统监控"),
    ]

    # 可选模块（AI识别功能需要，但系统可以在没有AI的情况下运行）
    optional_modules = [
        ("torch", "PyTorch"),
        ("torchvision", "TorchVision"),
    ]

    required_success = 0
    optional_success = 0

    print_info("检查必需模块：")
    for module, desc in required_modules:
        try:
            __import__(module)
            print_success(f"  {module} ({desc})")
            required_success += 1
        except ImportError as e:
            print_error(f"  {module} ({desc}) - {e}")

    print_info("\n检查可选模块（AI识别）：")
    for module, desc in optional_modules:
        try:
            __import__(module)
            print_success(f"  {module} ({desc})")
            optional_success += 1
        except ImportError as e:
            print_warning(f"  {module} ({desc}) - 未安装（AI识别功能将不可用）")

    # 只要必需模块都成功就算通过
    if required_success == len(required_modules):
        if optional_success == len(optional_modules):
            print_success("所有模块导入成功")
        else:
            print_warning(f"必需模块导入成功，但 {len(optional_modules) - optional_success} 个可选模块未安装")
            print_info("提示：如需AI识别功能，请手动安装 PyTorch:")
            print_info("  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu")
        return True
    else:
        print_error(f"{len(required_modules) - required_success} 个必需模块导入失败")
        return False


def verify_project_structure():
    """验证项目结构"""
    print_header("验证项目结构")

    project_root = Path(__file__).parent

    required_files = [
        "config.json",
        "main.py",
        "requirements.txt",
        # 核心模块
        "src/core/__init__.py",
        "src/core/config.py",
        "src/core/database.py",
        "src/core/logger.py",
        "src/core/game_processor.py",
        # API模块
        "src/api/__init__.py",
        "src/api/backend.py",
        # 监控模块
        "src/monitor/__init__.py",
        "src/monitor/browser_monitor.py",
        "src/monitor/http_monitor.py",
        "src/monitor/storage_monitor.py",
        # 截图模块
        "src/capture/__init__.py",
        "src/capture/capture.py",
        # AI识别模块
        "src/ai/__init__.py",
        "src/ai/recognizer.py",
        # UI模块
        "src/ui/__init__.py",
        "src/ui/windows_ui.py",
        # 自动登录模块
        "src/auto_login_roadmap/__init__.py",
        "src/auto_login_roadmap/login.py",
        "src/auto_login_flv/__init__.py",
        "src/auto_login_flv/login.py",
        # FLV推流模块
        "src/flv_push/__init__.py",
        "src/flv_push/stream_pusher.py",
    ]

    required_dirs = [
        "models",
        "temp",
    ]

    # 检查文件
    missing_files = []
    for file in required_files:
        file_path = project_root / file
        if file_path.exists():
            print_success(f"  {file}")
        else:
            print_error(f"  {file} (缺失)")
            missing_files.append(file)

    # 检查并创建目录
    print("\n检查目录：")
    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print_success(f"  {dir_name}/")
        else:
            dir_path.mkdir(parents=True, exist_ok=True)
            print_warning(f"  {dir_name}/ (已创建)")

    # 检查 AI 模型
    model_path = project_root / "models" / "best_resnet101_model.pth"
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        print_success(f"  AI 模型: {size_mb:.1f} MB")
    else:
        print_warning(f"  AI 模型不存在 (需要手动放置)")

    if missing_files:
        print_error(f"\n缺失 {len(missing_files)} 个必要文件")
        return False

    print_success("项目结构完整")
    return True


def test_database_connection():
    """测试数据库连接"""
    print_header("测试数据库连接")

    project_root = Path(__file__).parent
    config_file = project_root / "config.json"

    if not config_file.exists():
        print_error("config.json 不存在")
        return False

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        mysql_config = config_data.get('mysql', {})
        host = mysql_config.get('host', '')
        port = mysql_config.get('port', 3306)
        database = mysql_config.get('database', '')

        print_info(f"数据库: {host}:{port}/{database}")

        import pymysql

        conn = pymysql.connect(
            host=mysql_config['host'],
            port=mysql_config['port'],
            user=mysql_config['user'],
            password=mysql_config['password'],
            database=mysql_config['database'],
            charset=mysql_config.get('charset', 'utf8mb4'),
            connect_timeout=5
        )

        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()

        print_success("数据库连接成功")
        return True

    except ImportError:
        print_warning("pymysql 未安装，跳过数据库测试")
        return True
    except Exception as e:
        print_error(f"数据库连接失败: {e}")
        return False


def create_start_script():
    """创建启动脚本"""
    print_header("创建启动脚本")

    project_root = Path(__file__).parent
    bat_dir = project_root / "bat"

    # 创建 bat 目录
    bat_dir.mkdir(parents=True, exist_ok=True)

    # 定义要创建的桌台 (1-6, 10, 12-13, 23-28)
    desk_configs = [
        (1, 9223), (2, 9224), (3, 9225), (4, 9226), (5, 9227), (6, 9228),
        (7, 9229), (8, 9230), (9, 9231), (10, 9232), (11, 9233), (12, 9234),
        (13, 9235), (14, 9236), (15, 9237), (16, 9238), (17, 9239), (18, 9240),
        (19, 9241), (20, 9242), (21, 9243), (22, 9244), (23, 9245), (24, 9246),
        (25, 9247), (26, 9248), (27, 9249), (28, 9250),
    ]

    created_count = 0
    skipped_count = 0

    for desk_id, port in desk_configs:
        bat_file = bat_dir / f"start_desk{desk_id}.bat"
        if bat_file.exists():
            skipped_count += 1
            continue

        bat_content = f'''@echo off
chcp 65001 >nul
cd /d "%~dp0.."
setlocal EnableDelayedExpansion

REM ========================================
REM   龙虎监控系统 v5.1
REM ========================================
REM   桌台{desk_id} - 自动采集路单 + FLV推流
REM   端口: {port}
REM ========================================

set DESK_ID={desk_id}
set DEBUG_PORT={port}

echo ========================================
echo   龙虎监控系统 v5.1
echo   桌台: %DESK_ID%  端口: %DEBUG_PORT%
echo ========================================
echo.

echo [1/2] 清理临时文件...
set TEMP_DIR=temp\\desk_%DESK_ID%
if exist "%TEMP_DIR%\\logs\\monitor\\*" del /q "%TEMP_DIR%\\logs\\monitor\\*" 2>nul
if exist "%TEMP_DIR%\\screenshots\\*.png" del /q "%TEMP_DIR%\\screenshots\\*.png" 2>nul
if exist "%TEMP_DIR%\\screenshots\\*.json" del /q "%TEMP_DIR%\\screenshots\\*.json" 2>nul

echo [2/2] 启动程序...
echo.

python main.py --desk %DESK_ID% --port %DEBUG_PORT%

pause
'''
        with open(bat_file, 'w', encoding='utf-8') as f:
            f.write(bat_content)
        created_count += 1

    if created_count > 0:
        print_success(f"创建 {created_count} 个启动脚本到 bat/ 目录")
    if skipped_count > 0:
        print_info(f"跳过 {skipped_count} 个已存在的脚本")

    print_info(f"启动脚本位置: bat/start_desk{{N}}.bat")

    return True


def main():
    """主函数"""
    Colors.init()

    print(f"""
{Colors.CYAN}{Colors.BOLD}
╔═══════════════════════════════════════════════════════════╗
║         龙虎监控系统 - 环境安装程序                       ║
║                                                           ║
║  本程序将自动安装所需的依赖包和环境                       ║
╚═══════════════════════════════════════════════════════════╝
{Colors.RESET}""")

    # 解析命令行参数
    args = sys.argv[1:]
    check_only = '--check' in args
    deps_only = '--deps' in args

    if check_only:
        print_info("仅检查模式")
        verify_imports()
        verify_project_structure()
        test_database_connection()
        return

    if deps_only:
        print_info("仅安装依赖模式")
        if check_pip():
            install_dependencies()
        return

    # 完整安装流程
    steps = [
        ("检查 Python 版本", check_python_version),
        ("检查 pip", check_pip),
        ("安装依赖包", install_dependencies),
        ("安装 Playwright 浏览器", install_playwright_browser),
        ("验证模块导入", verify_imports),
        ("验证项目结构", verify_project_structure),
        ("测试数据库连接", test_database_connection),
        ("创建启动脚本", create_start_script),
    ]

    results = []
    for step_name, step_func in steps:
        try:
            result = step_func()
            results.append((step_name, result))
        except Exception as e:
            print_error(f"步骤失败: {e}")
            results.append((step_name, False))

    # 显示总结
    print_header("安装总结")

    success_count = sum(1 for _, r in results if r)
    total_count = len(results)

    for step_name, result in results:
        if result:
            print_success(f"  {step_name}")
        else:
            print_error(f"  {step_name}")

    print()
    if success_count == total_count:
        print(f"""
{Colors.GREEN}{Colors.BOLD}
╔═══════════════════════════════════════════════════════════╗
║                    安装成功！                             ║
╠═══════════════════════════════════════════════════════════╣
║  启动方式：                                               ║
║    方式1: 双击 bat/start_desk1.bat (桌台1)                ║
║    方式2: python main.py --desk 1 --port 9223             ║
║                                                           ║
║  多开方式：                                               ║
║    直接双击对应的 bat/start_deskN.bat                     ║
║    例如: bat/start_desk2.bat (桌台2, 端口9224)            ║
╚═══════════════════════════════════════════════════════════╝
{Colors.RESET}""")
    else:
        print(f"""
{Colors.YELLOW}{Colors.BOLD}
╔═══════════════════════════════════════════════════════════╗
║              安装完成，但有 {total_count - success_count} 个步骤失败                   ║
╠═══════════════════════════════════════════════════════════╣
║  请检查上述失败的步骤，手动解决问题后重新运行             ║
╚═══════════════════════════════════════════════════════════╝
{Colors.RESET}""")


if __name__ == "__main__":
    main()
