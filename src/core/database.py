# -*- coding: utf-8 -*-
"""
数据库管理器 - 统一管理MySQL数据库连接和操作
"""
import json
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

    # ========== 路单同步相关操作 ==========

    def convert_libo_to_mazong(self, libo_result: str) -> dict:
        """
        利博结果编码 转换为 马总格式 (龙虎版本)

        龙虎利博编码:
        - 10: 龙赢
        - 20: 和局
        - 30: 虎赢

        马总格式:
        - result: 1=龙, 2=虎, 3=和
        - ext: 固定为0 (龙虎无对子)
        """
        result_convert = config.get("result_convert", {})
        converted = result_convert.get(str(libo_result), {"result": "0", "ext": "0"})

        result_code = converted.get("result", "0")
        ext_code = converted.get("ext", "0")

        winner_map = {"1": "龙", "2": "虎", "3": "和", "0": "未知"}

        return {
            "result": result_code,
            "ext": ext_code,
            "winner": winner_map.get(result_code, "未知"),
            "pairs": ""  # 龙虎无对子
        }

    def get_default_result_pai(self, result_combined: str) -> str:
        """
        根据 result 获取默认牌面数据

        Args:
            result_combined: 组合结果如 "1|0", "2|1", "3|0" 等

        Returns:
            JSON字符串格式的牌面数据
        """
        # 从配置获取默认牌面映射
        default_pai_map = config.get("default_result_pai", {})

        # 查找匹配的牌面
        if result_combined in default_pai_map:
            pai_data = default_pai_map[result_combined]
            return json.dumps(pai_data, ensure_ascii=False)

        # 未找到则返回全0默认值 (龙虎只需2张牌)
        return '{"1": "0|0", "2": "0|0"}'

    def sync_roadmap_record(
        self,
        desk_id: int,
        shoe_num: int,
        round_num: int,
        libo_result: str,
        pai_result: dict = None
    ) -> bool:
        """同步单条路单记录到 ntp_dianji_lu_zhu 表"""
        try:
            table_id = config.get_table_id(desk_id)

            converted = self.convert_libo_to_mazong(libo_result)
            result = converted["result"]
            ext = converted["ext"]
            # result字段存储组合格式: "result|ext" (如 "1|0", "2|1")
            result_combined = f"{result}|{ext}"

            # 如果传入了牌面数据则使用，否则根据result获取默认牌面
            if pai_result:
                result_pai_json = json.dumps(pai_result, ensure_ascii=False)
            else:
                result_pai_json = self.get_default_result_pai(result_combined)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                sql = """
                    INSERT INTO ntp_dianji_lu_zhu
                    (status, create_time, update_time, table_id, game_type,
                     result, result_pai, xue_number, pu_number)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        result = VALUES(result),
                        result_pai = VALUES(result_pai),
                        update_time = VALUES(update_time)
                """

                now = datetime.now()
                cursor.execute(sql, (
                    1, now, now, table_id, 2,  # game_type: 2=龙虎
                    result_combined, result_pai_json, shoe_num, round_num
                ))
                conn.commit()

                logger.info(f"[桌{desk_id}] 路单同步成功: 靴{shoe_num} 铺{round_num} -> result={result_combined}")
                return True

        except Exception as e:
            logger.error(f"[桌{desk_id}] 路单同步失败: {e}")
            return False

    def sync_roadmap_batch(
        self,
        desk_id: int,
        shoe_num: int,
        records: list
    ) -> dict:
        """批量同步路单记录"""
        success_count = 0
        failed_count = 0

        for record in records:
            round_num = record.get("round", record.get("pu", 0))
            libo_result = str(record.get("result", ""))

            if round_num > 0 and libo_result:
                if self.sync_roadmap_record(desk_id, shoe_num, round_num, libo_result):
                    success_count += 1
                else:
                    failed_count += 1

        logger.info(f"[桌{desk_id}] 批量同步完成: 成功{success_count}, 失败{failed_count}, 总计{len(records)}")

        return {
            "success": success_count,
            "failed": failed_count,
            "total": len(records)
        }

    def get_current_roadmap(self, desk_id: int, shoe_num: int = None, limit: int = 100) -> list:
        """获取当前路单记录"""
        try:
            table_id = config.get_table_id(desk_id)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                if shoe_num:
                    sql = """
                        SELECT id, xue_number, pu_number, result, result_pai, create_time
                        FROM ntp_dianji_lu_zhu
                        WHERE table_id = %s AND xue_number = %s AND status = 1
                        ORDER BY pu_number DESC
                        LIMIT %s
                    """
                    cursor.execute(sql, (table_id, shoe_num, limit))
                else:
                    sql = """
                        SELECT id, xue_number, pu_number, result, result_pai, create_time
                        FROM ntp_dianji_lu_zhu
                        WHERE table_id = %s AND status = 1
                        ORDER BY xue_number DESC, pu_number DESC
                        LIMIT %s
                    """
                    cursor.execute(sql, (table_id, limit))

                return cursor.fetchall()

        except Exception as e:
            logger.error(f"[桌{desk_id}] 获取路单失败: {e}")
            return []

    # ========== 远程数据读取（用于同步对比） ==========

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

    def sync_roadmap_full(self, desk_id: int, local_records: List[Dict]) -> Dict[str, Any]:
        """
        全量同步路单 - 删除远程所有数据后重新写入

        Args:
            desk_id: 桌号
            local_records: 本地路单数据 [{"round": 1, "result": "30"}, ...]

        Returns:
            {"deleted": int, "inserted": int, "details": [...]}
        """
        try:
            table_id = config.get_table_id(desk_id)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                # 1. 删除该桌台所有路单数据
                delete_sql = "DELETE FROM ntp_dianji_lu_zhu WHERE table_id = %s"
                cursor.execute(delete_sql, (table_id,))
                deleted_count = cursor.rowcount

                # 2. 插入所有本地数据
                inserted_count = 0
                now = datetime.now()

                for record in local_records:
                    round_num = record.get("round", record.get("pu", 0))
                    libo_result = str(record.get("result", ""))

                    if round_num > 0 and libo_result:
                        converted = self.convert_libo_to_mazong(libo_result)
                        # result字段存储组合格式: "result|ext" (如 "1|0", "2|1")
                        result_combined = f"{converted['result']}|{converted['ext']}"
                        # 根据result获取对应的默认牌面
                        result_pai_json = self.get_default_result_pai(result_combined)

                        insert_sql = """
                            INSERT INTO ntp_dianji_lu_zhu
                            (status, create_time, update_time, table_id, game_type,
                             result, result_pai, xue_number, pu_number)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(insert_sql, (
                            1, now, now, table_id, 2,  # game_type: 2=龙虎
                            result_combined, result_pai_json, 1, round_num
                        ))
                        inserted_count += 1

                conn.commit()

                logger.info(f"[桌{desk_id}] 全量同步完成: 删除{deleted_count}条, 插入{inserted_count}条")

                return {
                    "deleted": deleted_count,
                    "inserted": inserted_count
                }

        except Exception as e:
            logger.error(f"[桌{desk_id}] 全量同步失败: {e}")
            return {"deleted": 0, "inserted": 0, "error": str(e)}

    def sync_roadmap_incremental(self, desk_id: int, local_records: List[Dict]) -> Dict[str, Any]:
        """
        同步路单 - 只比对数量，不同则全量同步

        策略:
        1. 比对本地和远程的数据条数
        2. 数量相同则跳过
        3. 数量不同则全量同步：删除全部 → 重新插入全部

        Args:
            desk_id: 桌号
            local_records: 本地路单数据 [{"round": 1, "result": "30"}, ...]

        Returns:
            {"mode": "consistent" | "full", "deleted": int, "inserted": int, "local_count": int}
        """
        try:
            local_count = len(local_records)

            # 1. 获取远程数据条数
            remote_records = self.get_remote_roadmap(desk_id)
            remote_count = len(remote_records)

            # 2. 数量相同则跳过
            if local_count == remote_count:
                logger.info(f"[桌{desk_id}] 数量一致({local_count}条)，跳过同步")
                return {
                    "mode": "consistent",
                    "deleted": 0,
                    "inserted": 0,
                    "local_count": local_count
                }

            # 3. 数量不同则全量同步
            logger.info(f"[桌{desk_id}] 数量不同(本地{local_count} vs 远程{remote_count})，执行全量同步")
            result = self.sync_roadmap_full(desk_id, local_records)
            result["mode"] = "full"
            result["local_count"] = local_count
            return result

        except Exception as e:
            logger.error(f"[桌{desk_id}] 同步失败: {e}")
            return {"mode": "error", "deleted": 0, "inserted": 0, "local_count": 0, "error": str(e)}

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
