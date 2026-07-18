"""
balance_reader.py - Read Actual Balance from Database
"""

import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

logger = logging.getLogger("balance_reader")

class BalanceReader:
    def __init__(self, database_url, starting_balance=200):
        self.database_url = database_url
        self.starting_balance = starting_balance
    
    def get_db(self):
        try:
            return psycopg2.connect(self.database_url, connect_timeout=5)
        except Exception as e:
            logger.error(f"[DB] Connection error: {e}")
            return None
    
    def get_current_balance(self):
        """حساب الرصيد الحقيقي = رصيد البداية + الأرباح المتراكمة"""
        conn = self.get_db()
        if not conn:
            return self.starting_balance
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT COALESCE(SUM(net_pnl), 0) as total_pnl
                    FROM live_paper_trades 
                    WHERE status = 'CLOSED'
                """)
                
                result = cur.fetchone()
                total_pnl = float(result['total_pnl']) if result else 0
                current_balance = self.starting_balance + total_pnl
                
                return current_balance
        except Exception as e:
            logger.error(f"[Balance Error] {e}")
            return self.starting_balance
        finally:
            conn.close()
    
    def get_monthly_pnl(self):
        """الأرباح الشهرية الحالية"""
        conn = self.get_db()
        if not conn:
            return 0
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT COALESCE(SUM(net_pnl), 0) as total_pnl
                    FROM live_paper_trades 
                    WHERE status = 'CLOSED'
                    AND DATE_TRUNC('month', closed_at) = DATE_TRUNC('month', NOW())
                """)
                
                result = cur.fetchone()
                return float(result['total_pnl']) if result else 0
        except Exception as e:
            logger.error(f"[Monthly PnL Error] {e}")
            return 0
        finally:
            conn.close()
    
    def get_open_trades_pnl(self):
        """ربح/خسارة الصفقات المفتوحة (unrealized)"""
        conn = self.get_db()
        if not conn:
            return 0
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT COALESCE(SUM(
                        CASE 
                            WHEN direction = 'BUY' THEN (entry_price - entry_price) 
                            ELSE 0 
                        END
                    ), 0) as unrealized
                    FROM live_paper_trades 
                    WHERE status = 'OPEN'
                """)
                
                result = cur.fetchone()
                return float(result['unrealized']) if result else 0
        except Exception as e:
            logger.error(f"[Open Trades PnL Error] {e}")
            return 0
        finally:
            conn.close()
