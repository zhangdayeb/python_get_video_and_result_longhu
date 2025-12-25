# -*- coding: utf-8 -*-
"""
数据库管理器 - 统一管理MySQL数据库连接和操作

注：路单同步已统一通过 PHP API (Luzhu::syncIncremental) 处理
Python端仅保留数据库读取功能用于数据比对和FLV更新
"""
import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
import logging

from .config import config

logger = logging.getLogger("database")


class DBManager:
    """数据库管理器 - 单例模式"""

    _instance = None
    _pool: List[pymysql.Connection] = []
    _pool_size = 5

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._pool:
            self._init_pool()

    def _init_pool(self):
        """初始化连接池"""
        mysql_config = config.mysql_config
        self._pool_size = mysql_config.get('pool_size', 5)

        logger.info(f"初始化数据库连接池，大小: {self._pool_size}")

        for i in range(self._pool_size):
            try:
                conn = pymysql.connect(
                    host=mysql_config['host'],
                    port=mysql_config['port'],
                    user=mysql_config['user'],
                    password=mysql_config['password'],
                    database=mysql_config['database'],
                    charset=mysql_config.get('charset', 'utf8mb4'),
                    cursorclass=DictCursor
                )
                self._pool.append(conn)
            except Exception as e:
                logger.error(f"创建数据库连接失败 [{i+1}/{self._pool_size}]: {e}")

        logger.info(f"连接池初始化完成，成功创建 {len(self._pool)} 个连接")

    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = None
        try:
            if self._pool:
                conn = self._pool.pop(0)
                conn.ping(reconnect=True)
            else:
                mysql_config = config.mysql_config
                conn = pymysql.connect(
                    host=mysql_config['host'],
                    port=mysql_config['port'],
                    user=mysql_config['user'],
                    password=mysql_config['password'],
                    database=mysql_config['database'],
                    charset=mysql_config.get('charset', 'utf8mb4'),
                    cursorclass=DictCursor
                )

            yield conn

        except Exception as e:
            logger.error(f"数据库操作错误: {e}")
            raise

        finally:
            if conn:
                if len(self._pool) < self._pool_size:
                    self._pool.append(conn)
                else:
                    conn.close()

    def test_connection(self) -> bool:
        """测试数据库连接是否正常"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                return True
        except Exception as e:
            logger.error(f"数据库连接测试失败: {e}")
            return False

    # ========== 台桌状态表操作 ==========

    def update_desk_status(
        self,
        desk_id: int,
        shoe_num: int,
        round_num: int,
        desk_name: str = None,
        game_state: str = None,
        countdown: int = None
    ) -> bool:
        """更新台桌状态"""
        try:
            table_id = config.get_table_id(desk_id)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                sql = """
                    INSERT INTO ntp_desk_status
                    (desk_id, table_id, desk_name, shoe_num, round_num, game_state, countdown)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        table_id = VALUES(table_id),
                        desk_name = VALUES(desk_name),
                        shoe_num = VALUES(shoe_num),
                        round_num = VALUES(round_num),
                        game_state = VALUES(game_state),
                        countdown = VALUES(countdown),
                        updated_at = CURRENT_TIMESTAMP
                """

                cursor.execute(sql, (desk_id, table_id, desk_name, shoe_num, round_num, game_state, countdown))
                conn.commit()

                return True

        except Exception as e:
            logger.error(f"更新台桌状态失败 [桌{desk_id}]: {e}")
            return False

    def get_desk_status(self, desk_id: int) -> Optional[Dict[str, Any]]:
        """获取台桌状态"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                sql = "SELECT * FROM ntp_desk_status WHERE desk_id = %s"
                cursor.execute(sql, (desk_id,))
                return cursor.fetchone()

        except Exception as e:
            logger.error(f"获取台桌状态失败 [桌{desk_id}]: {e}")
            return None

    # ========== FLV更新 ==========

    def update_table_flv(self, desk_id: int, flv_url: str) -> bool:
        """更新ntp_dianji_table表的FLV地址"""
        try:
            table_id = config.get_table_id(desk_id)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                sql = """
                    UPDATE ntp_dianji_table
                    SET video_near = %s,
                        video_far = %s,
                        update_time = %s
                    WHERE id = %s
                """

                cursor.execute(sql, (flv_url, flv_url, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), table_id))
                conn.commit()

                logger.info(f"[桌{desk_id}] FLV地址已更新 (table_id={table_id})")
                return True

        except Exception as e:
            logger.error(f"更新FLV地址失败 [桌{desk_id}]: {e}")
            return False

    # ========== 识别结果表操作 ==========

    def save_recognition_result(
        self,
        desk_id: int,
        shoe_num: int,
        round_num: int,
        cards: Dict[str, str],
        confidence_avg: float = None,
        recognition_method: str = "AI",
        screenshot_path: str = None,
        debug_images: str = None
    ) -> bool:
        """保存识别结果"""
        try:
            table_id = config.get_table_id(desk_id)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                sql = """
                    INSERT INTO ntp_recognition_results
                    (desk_id, table_id, shoe_num, round_num,
                     card_1, card_2, card_3, card_4, card_5, card_6,
                     confidence_avg, recognition_method, screenshot_path, debug_images)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        card_1 = VALUES(card_1),
                        card_2 = VALUES(card_2),
                        card_3 = VALUES(card_3),
                        card_4 = VALUES(card_4),
                        card_5 = VALUES(card_5),
                        card_6 = VALUES(card_6),
                        confidence_avg = VALUES(confidence_avg),
                        recognition_method = VALUES(recognition_method),
                        screenshot_path = VALUES(screenshot_path),
                        debug_images = VALUES(debug_images)
                """

                cursor.execute(sql, (
                    desk_id, table_id, shoe_num, round_num,
                    cards.get("1"), cards.get("2"), cards.get("3"),
                    cards.get("4"), cards.get("5"), cards.get("6"),
                    confidence_avg, recognition_method, screenshot_path, debug_images
                ))
                conn.commit()

                return True

        except Exception as e:
            logger.error(f"保存识别结果失败 [桌{desk_id}]: {e}")
            return False

    # ========== 远程数据读取（用于同步对比） ==========
    # 注：路单同步已统一通过 PHP API (Luzhu::syncIncremental) 处理
    # Python端仅保留读取功能用于数据比对

    def get_remote_flv(self, desk_id: int) -> Optional[str]:
        """读取远程数据库中的FLV地址"""
        try:
            table_id = config.get_table_id(desk_id)

            with self.get_connection() as conn:
                cursor = conn.cursor()
                sql = "SELECT video_near FROM ntp_dianji_table WHERE id = %s"
                cursor.execute(sql, (table_id,))
                row = cursor.fetchone()

                if row:
                    return row.get('video_near', '')
                return None

        except Exception as e:
            logger.error(f"[桌{desk_id}] 读取远程FLV失败: {e}")
            return None

    def get_remote_roadmap(self, desk_id: int) -> List[Dict]:
        """读取远程数据库中的所有路单记录"""
        try:
            table_id = config.get_table_id(desk_id)

            with self.get_connection() as conn:
                cursor = conn.cursor()
                sql = """
                    SELECT id, xue_number, pu_number, result, result_pai, create_time
                    FROM ntp_dianji_lu_zhu
                    WHERE table_id = %s AND status = 1
                    ORDER BY pu_number ASC
                """
                cursor.execute(sql, (table_id,))
                return cursor.fetchall()

        except Exception as e:
            logger.error(f"[桌{desk_id}] 读取远程路单失败: {e}")
            return []

    def get_remote_record_count(self, desk_id: int) -> int:
        """获取远程数据库中的路单记录数（用于计算线上铺号）"""
        try:
            table_id = config.get_table_id(desk_id)

            with self.get_connection() as conn:
                cursor = conn.cursor()
                sql = """
                    SELECT COUNT(id) as record_count
                    FROM ntp_dianji_lu_zhu
                    WHERE table_id = %s AND status = 1
                """
                cursor.execute(sql, (table_id,))
                row = cursor.fetchone()

                if row and row.get('record_count'):
                    return int(row['record_count'])
                return 0

        except Exception as e:
            logger.error(f"[桌{desk_id}] 获取线上记录数失败: {e}")
            return 0

    def get_last_n_results(self, desk_id: int, n: int = 2) -> List[str]:
        """
        获取最后N条记录的result值（用于同步比对）

        Args:
            desk_id: 桌号
            n: 获取数量，默认2条

        Returns:
            result值列表，按铺号降序 ["2|0", "1|0"]
        """
        try:
            table_id = config.get_table_id(desk_id)

            with self.get_connection() as conn:
                cursor = conn.cursor()
                sql = """
                    SELECT result
                    FROM ntp_dianji_lu_zhu
                    WHERE table_id = %s AND status = 1
                    ORDER BY pu_number DESC
                    LIMIT %s
                """
                cursor.execute(sql, (table_id, n))
                rows = cursor.fetchall()

                return [row['result'] for row in rows if row.get('result')]

        except Exception as e:
            logger.error(f"[桌{desk_id}] 获取最后{n}条结果失败: {e}")
            return []

    def sync_flv_if_changed(self, desk_id: int, local_flv: str) -> Dict[str, Any]:
        """
        检查并同步FLV地址（如果有变化）

        Returns:
            {"changed": bool, "old": str, "new": str}
        """
        try:
            remote_flv = self.get_remote_flv(desk_id)

            if remote_flv == local_flv:
                return {"changed": False, "old": remote_flv, "new": local_flv}

            # 有变化，更新远程
            self.update_table_flv(desk_id, local_flv)

            return {"changed": True, "old": remote_flv, "new": local_flv}

        except Exception as e:
            logger.error(f"[桌{desk_id}] FLV同步检查失败: {e}")
            return {"changed": False, "error": str(e)}

    # ========== 采集配置读取 ==========

    def get_caiji_config(self, desk_id: int) -> Optional[Dict[str, Any]]:
        """
        获取采集配置（用户名、密码、台桌URL、FLV账号）

        Args:
            desk_id: 桌号

        Returns:
            {
                "caiji_username": "aw0795",
                "caiji_password": "3377",
                "caiji_desk_url": "https://www.559156667.com/game?desk=1&gameType=2&xian=1",
                "caiji_flv_username": "aw0796",
                "caiji_flv_password": "123456"
            }
            如果未配置则返回 None
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                sql = """
                    SELECT caiji_username, caiji_password, caiji_desk_url,
                           caiji_flv_username, caiji_flv_password
                    FROM ntp_dianji_table
                    WHERE id = %s
                """
                cursor.execute(sql, (desk_id,))
                row = cursor.fetchone()

                if row and row.get('caiji_username') and row.get('caiji_password'):
                    flv_user = row.get('caiji_flv_username') or row.get('caiji_username')
                    flv_pass = row.get('caiji_flv_password') or row.get('caiji_password')
                    logger.info(f"[桌{desk_id}] 获取采集配置: roadmap_user={row.get('caiji_username')}, flv_user={flv_user}")
                    return {
                        "caiji_username": row.get('caiji_username'),
                        "caiji_password": row.get('caiji_password'),
                        "caiji_desk_url": row.get('caiji_desk_url'),
                        "caiji_flv_username": flv_user,
                        "caiji_flv_password": flv_pass
                    }
                else:
                    logger.warning(f"[桌{desk_id}] 采集配置未设置或不完整")
                    return None

        except Exception as e:
            logger.error(f"[桌{desk_id}] 获取采集配置失败: {e}")
            return None

    def close(self):
        """关闭所有连接"""
        logger.info("关闭数据库连接池")
        for conn in self._pool:
            try:
                conn.close()
            except:
                pass
        self._pool.clear()


# 全局单例
db = DBManager()
