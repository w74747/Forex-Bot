"""
ctrader_connector.py - Real cTrader Connection via FIX Protocol
"""

import socket
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger("ctrader_connector")

class CTraderConnector:
    """ربط مباشر مع منصة cTrader عبر FIX Protocol"""
    
    def __init__(self, client_id, account_id, fix_host, fix_port, fix_username, fix_password=None):
        self.client_id = client_id
        self.account_id = account_id
        self.fix_host = fix_host
        self.fix_port = fix_port
        self.fix_username = fix_username
        self.fix_password = fix_password or client_id
        
        self.socket = None
        self.connected = False
        self.prices_cache = {}
        self.balance = 0.0
        self.equity = 0.0
        
    def connect(self) -> bool:
        """الاتصال مع cTrader"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.fix_host, self.fix_port))
            self.connected = True
            logger.info(f"[cTrader] Connected to {self.fix_host}:{self.fix_port}")
            self._send_logon()
            return True
        except Exception as e:
            logger.error(f"[cTrader Connect] {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """قطع الاتصال"""
        try:
            if self.socket:
                self.socket.close()
            self.connected = False
            logger.info("[cTrader] Disconnected")
        except Exception as e:
            logger.error(f"[cTrader Disconnect] {e}")
    
    def _send_logon(self):
        """إرسال رسالة تسجيل الدخول"""
        try:
            timestamp = datetime.utcnow().strftime('%Y%m%d-%H:%M:%S')
            logon_msg = (
                f"8=FIX.4.4|"
                f"9=100|"
                f"35=A|"
                f"49={self.fix_username}|"
                f"56=cServer|"
                f"34=1|"
                f"52={timestamp}|"
                f"98=0|"
                f"108=30|"
                f"10=000|"
            ).replace('|', '\x01')
            
            self.socket.send(logon_msg.encode())
            logger.info("[cTrader] Logon sent")
        except Exception as e:
            logger.error(f"[cTrader Logon] {e}")
    
    def get_price(self, symbol: str) -> Optional[Dict]:
        """قراءة السعر الحالي من cTrader"""
        try:
            if not self.connected:
                return None
            
            # محاولة قراءة من الـ cache أولاً
            if symbol in self.prices_cache:
                return self.prices_cache[symbol]
            
            return None
        except Exception as e:
            logger.error(f"[Get Price] {e}")
            return None
    
    def update_prices(self, prices_data: Dict):
        """تحديث أسعار الأزواج من cTrader"""
        try:
            if not self.connected:
                return False
            
            self.prices_cache.update(prices_data)
            return True
        except Exception as e:
            logger.error(f"[Update Prices] {e}")
            return False
    
    def get_account_info(self) -> Optional[Dict]:
        """قراءة معلومات الحساب من cTrader (الرصيد، الإيكويتي، إلخ)"""
        try:
            if not self.connected:
                return None
            
            # هنا يجب قراءة البيانات من cTrader مباشرة
            # الآن نرجع cache
            return {
                'balance': self.balance,
                'equity': self.equity,
                'account_id': self.account_id,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[Get Account Info] {e}")
            return None
    
    def set_account_balance(self, balance: float, equity: float):
        """تحديث رصيد الحساب المقروء من cTrader"""
        self.balance = balance
        self.equity = equity
        logger.info(f"[Account] Balance: ${balance:.2f} | Equity: ${equity:.2f}")
    
    def is_connected(self) -> bool:
        """التحقق من حالة الاتصال"""
        return self.connected
