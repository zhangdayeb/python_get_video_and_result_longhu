# -*- coding: utf-8 -*-
"""
HTTP请求/响应监控器
"""
import zlib
import json
import urllib.parse
import logging
from typing import Optional, Dict, Callable

logger = logging.getLogger("http_monitor")


class HttpMonitor:
    """HTTP请求/响应监控器"""

    def __init__(self, write_log_callback: Callable = None):
        """
        初始化HTTP监控器

        Args:
            write_log_callback: 日志写入回调函数
        """
        self._write_log = write_log_callback
        self.on_http_request: Optional[Callable[[Dict], None]] = None
        self.on_game_api: Optional[Callable[[Dict], None]] = None

        # 统计
        self.stats = {
            "http_requests": 0,
            "http_responses": 0,
        }

    def setup_listeners(self, page):
        """
        设置HTTP请求/响应监听

        Args:
            page: Playwright page
        """
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        logger.info("[HTTP] 监听器已设置")

    def _on_request(self, request):
        """HTTP请求处理"""
        try:
            url = request.url
            self.stats["http_requests"] += 1

            # 捕获FLV请求
            if '.flv' in url:
                if self._write_log:
                    self._write_log("flv_request", {"url": url})
                logger.info(f"[FLV] {url[:80]}...")

            # 捕获API请求
            if any(k in url.lower() for k in ['api', '.aspx', 'ajax']):
                if self._write_log:
                    self._write_log("http_request", {
                        "url": url,
                        "method": request.method,
                        "resource_type": request.resource_type
                    })

            if self.on_http_request:
                self.on_http_request({"type": "request", "url": url})

        except Exception as e:
            logger.error(f"请求处理失败: {e}")

    async def _on_response(self, response):
        """HTTP响应处理"""
        try:
            url = response.url
            status = response.status
            self.stats["http_responses"] += 1

            # 只处理成功的API响应
            if status != 200:
                return

            is_api = any(k in url.lower() for k in [
                'httpapi.aspx', 'api', '.aspx', 'ajax', 'json'
            ])

            if not is_api:
                return

            # 获取响应体
            try:
                body = await response.body()
                if not body:
                    return

                # 解压
                text = self.decompress(body)
                if not text:
                    return

                # 解析
                data = self.parse_response(text)

                # 记录日志
                if self._write_log:
                    self._write_log("http_response", {
                        "url": url,
                        "status": status,
                        "data": data,
                        "raw_text": text[:2000] if len(text) > 2000 else text,
                        "raw_length": len(text)
                    })

                # 游戏API: httpapi.aspx
                if 'httpapi.aspx' in url and data:
                    if self.on_game_api:
                        self.on_game_api(data)

                if self.on_http_request:
                    self.on_http_request({"type": "response", "url": url, "data": data})

            except Exception as e:
                pass

        except Exception as e:
            logger.error(f"响应处理失败: {e}")

    def decompress(self, body: bytes) -> Optional[str]:
        """
        解压响应体

        尝试: gzip -> zlib -> deflate -> 直接解码
        """
        if not body:
            return None

        # 尝试 1: gzip
        try:
            return zlib.decompress(body, 16 + zlib.MAX_WBITS).decode('utf-8')
        except:
            pass

        # 尝试 2: zlib
        try:
            return zlib.decompress(body).decode('utf-8')
        except:
            pass

        # 尝试 3: raw deflate
        try:
            return zlib.decompress(body, -zlib.MAX_WBITS).decode('utf-8')
        except:
            pass

        # 尝试 4: 直接解码
        try:
            return body.decode('utf-8')
        except:
            pass

        # 尝试 5: GBK编码
        try:
            return body.decode('gbk')
        except:
            pass

        return None

    def parse_response(self, text: str) -> Dict:
        """解析响应数据"""
        # 尝试 query string
        if '=' in text and '&' in text:
            try:
                data = dict(urllib.parse.parse_qsl(text))
                if data:
                    return data
            except:
                pass

        # 尝试 JSON
        if text.strip().startswith('{') or text.strip().startswith('['):
            try:
                return json.loads(text)
            except:
                pass

        return {"_raw": text[:500]}
