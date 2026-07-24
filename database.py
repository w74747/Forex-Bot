"""
database.py - Database Operations
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from config import DatabaseConfig

logger = logging.getLogger("db")

class Database:
    def __init__(self):
        self.conn_string = DatabaseConfig.DATABASE_URL
    
    def get_connection(self):
        """احصل على اتصال جديد"""
        try:
            return psycopg2.connect(self.conn_string, connect_timeout=5)
        except Exception as e:
            logger.error(f"DB Connection error: {e}")
            return None
    
    def record_trade(self, symbol, direction, entry_price, sl, tp, lot_size, strategy):
        """سجل صفقة جديدة"""
        try:
            conn = self.get_connection()
            if not conn:
                return None
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO live_paper_trades 
                    (symbol, direction, entry_price, sl_price, tp_price, status, strategy, opened_at)
                    VALUES (%s, %s, %s, %s, %s, 'OPEN', %s, NOW())
                    RETURNING id
                """, (symbol, direction, entry_price, sl, tp, strategy))
                trade_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"✅ Trade recorded: #{trade_id} {symbol}")
                return trade_id
        except Exception as e:
            logger.error(f"Record error: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def close_trade(self, trade_id, exit_price, exit_reason, pnl):
        """أغلق صفقة"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
            
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE live_paper_trades 
                    SET status='CLOSED', exit_price=%s, exit_reason=%s, net_pnl=%s, closed_at=NOW()
                    WHERE id=%s
                """, (exit_price, exit_reason, pnl, trade_id))
                conn.commit()
                logger.info(f"✅ Trade closed: #{trade_id} {exit_reason}")
                return True
        except Exception as e:
            logger.error(f"Close error: {e}")
            return False
        finally:
            if conn:
                conn.close()
