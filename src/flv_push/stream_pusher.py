# -*- coding: utf-8 -*-
"""
FLV 推流模块

功能:
1. 使用 requests 从 FLV URL 拉取视频流
2. 通过管道传给 FFmpeg
3. FFmpeg 推送到 RTMP 服务器

这种方式比直接让 FFmpeg 拉流更稳定

使用方式:
    from flv_push import FLVStreamPusher

    pusher = FLVStreamPusher(desk_id=1)
    pusher.on_stats_update = lambda stats: print(f"速度: {stats['speed_kbps']:.1f} KB/s")
    pusher.start(flv_url, rtmp_url)
    # ...
    pusher.stop()
"""
import subprocess
import threading
import requests
import logging
from typing import Optional, Callable, Dict
from datetime import datetime

logger = logging.getLogger("flv_stream_pusher")


class FLVStreamPusher:
    """FLV 推流器 - 负责将 FLV 流推送到 RTMP 服务器"""

    # 默认 RTMP 服务器配置
    DEFAULT_RTMP_BASE = "rtmp://14.128.63.23/xm/bjl_y"

    # HTTP 请求头
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.559156667.com/',
        'Accept': '*/*',
        'Connection': 'keep-alive',
    }

    def __init__(self, desk_id: int):
        """
        初始化

        Args:
            desk_id: 桌台ID
        """
        self.desk_id = desk_id

        # 推流状态
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.total_bytes: int = 0

        # 进程和线程
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._response: Optional[requests.Response] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = False

        # 回调
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_started: Optional[Callable[[], None]] = None
        self.on_stopped: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_stats_update: Optional[Callable[[Dict], None]] = None

    def log(self, message: str):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] [FLV推流] {message}"
        logger.info(log_msg)
        if self.on_log:
            self.on_log(log_msg)

    def get_rtmp_url(self, rtmp_base: str = None) -> str:
        """获取 RTMP 推流地址"""
        base = rtmp_base or self.DEFAULT_RTMP_BASE
        return f"{base}{self.desk_id}"

    def start(self, flv_url: str, rtmp_url: str = None) -> bool:
        """
        启动推流

        Args:
            flv_url: FLV 源地址
            rtmp_url: RTMP 目标地址（可选，默认根据 desk_id 生成）

        Returns:
            是否启动成功
        """
        if self.is_running:
            self.log("推流已在运行")
            return False

        if not flv_url:
            self.log("FLV URL 为空")
            return False

        rtmp_url = rtmp_url or self.get_rtmp_url()

        self.log(f"源: {flv_url[:60]}...")
        self.log(f"目标: {rtmp_url}")

        # 重置状态
        self._stop_flag = False
        self.total_bytes = 0
        self.start_time = None

        # 启动后台线程
        self._thread = threading.Thread(
            target=self._stream_worker,
            args=(flv_url, rtmp_url),
            daemon=True
        )
        self._thread.start()

        return True

    def _stream_worker(self, flv_url: str, rtmp_url: str):
        """后台推流工作线程"""
        ffmpeg_process = None

        try:
            # 连接视频源
            self.log("连接视频源...")
            response = requests.get(
                flv_url,
                headers=self.DEFAULT_HEADERS,
                stream=True,
                timeout=15
            )

            if response.status_code != 200:
                self.log(f"连接失败: HTTP {response.status_code}")
                if self.on_error:
                    self.on_error(f"HTTP {response.status_code}")
                return

            self.log(f"连接成功 (HTTP {response.status_code})")
            self._response = response

            # 启动 FFmpeg
            ffmpeg_cmd = [
                'ffmpeg',
                '-f', 'flv',
                '-i', 'pipe:0',
                '-c', 'copy',
                '-f', 'flv',
                rtmp_url
            ]

            self.log("启动 FFmpeg...")
            ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )

            self._ffmpeg_process = ffmpeg_process
            self.log(f"FFmpeg 已启动 (PID: {ffmpeg_process.pid})")

            # 标记运行状态
            self.is_running = True
            self.start_time = datetime.now()
            self.total_bytes = 0

            if self.on_started:
                self.on_started()

            # 流式读取并推送
            chunk_count = 0
            for chunk in response.iter_content(chunk_size=8192):
                if self._stop_flag:
                    break

                if chunk:
                    self.total_bytes += len(chunk)
                    chunk_count += 1

                    # 写入 FFmpeg 管道
                    if ffmpeg_process and ffmpeg_process.stdin:
                        try:
                            ffmpeg_process.stdin.write(chunk)
                        except BrokenPipeError:
                            self.log("FFmpeg 管道断开")
                            break
                        except Exception as e:
                            self.log(f"写入错误: {e}")
                            break

                    # 每 100 个 chunk 更新统计（约 800KB）
                    if chunk_count % 100 == 0:
                        self._update_stats()

            self.log("流结束")

        except requests.exceptions.Timeout:
            self.log("连接超时")
            if self.on_error:
                self.on_error("连接超时")
        except requests.exceptions.ConnectionError as e:
            self.log(f"连接失败: {e}")
            if self.on_error:
                self.on_error(str(e))
        except Exception as e:
            self.log(f"异常: {e}")
            if self.on_error:
                self.on_error(str(e))
            import traceback
            traceback.print_exc()
        finally:
            # 清理资源
            self._cleanup(ffmpeg_process)

    def _update_stats(self):
        """更新统计信息"""
        if self.start_time and self.on_stats_update:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            if elapsed > 0:
                speed = self.total_bytes / elapsed / 1024  # KB/s
                self.on_stats_update({
                    'total_bytes': self.total_bytes,
                    'elapsed_seconds': elapsed,
                    'speed_kbps': speed
                })

    def _cleanup(self, ffmpeg_process):
        """清理资源"""
        # 关闭 FFmpeg
        if ffmpeg_process:
            try:
                if ffmpeg_process.stdin:
                    ffmpeg_process.stdin.close()
                ffmpeg_process.wait(timeout=5)
            except:
                try:
                    ffmpeg_process.terminate()
                except:
                    pass

        # 关闭 HTTP 连接
        if self._response:
            try:
                self._response.close()
            except:
                pass

        self._ffmpeg_process = None
        self._response = None
        self.is_running = False

        self.log("已停止")
        if self.on_stopped:
            self.on_stopped()

    def stop(self):
        """停止推流"""
        if not self.is_running:
            return

        self.log("正在停止...")
        self._stop_flag = True

        # 终止 FFmpeg
        if self._ffmpeg_process:
            try:
                self._ffmpeg_process.terminate()
                self._ffmpeg_process.wait(timeout=3)
            except:
                try:
                    self._ffmpeg_process.kill()
                except:
                    pass

        # 关闭 HTTP 连接
        if self._response:
            try:
                self._response.close()
            except:
                pass

    def get_stats(self) -> Dict:
        """获取当前统计信息"""
        if not self.start_time:
            return {
                'total_bytes': 0,
                'elapsed_seconds': 0,
                'speed_kbps': 0
            }

        elapsed = (datetime.now() - self.start_time).total_seconds()
        speed = self.total_bytes / elapsed / 1024 if elapsed > 0 else 0

        return {
            'total_bytes': self.total_bytes,
            'elapsed_seconds': elapsed,
            'speed_kbps': speed
        }

    @property
    def ffmpeg_pid(self) -> Optional[int]:
        """获取 FFmpeg 进程 ID"""
        if self._ffmpeg_process:
            return self._ffmpeg_process.pid
        return None
