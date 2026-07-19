"""
ctrader_openapi.py - Real cTrader OpenAPI Connection
"""

import logging
import requests
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger("ctrader_openapi")

class CTraderOpenAPI:
    """ربط مباشر مع cTrader عبر OpenAPI"""
    
    def __init__(self, client_id, account_id, username, password):
        self.client_id = client_id
        self.account_id = account_id
        self.username = username
        self.password = password
        
        self.access_token = None
        self.connected = False
        self.api_url = "https://openapi.ctrader.com/v1"
        self.auth_url = "https://openapi.ctrader.com/auth/oauth/token"
        
        self.balance = 0.0
        self.equity = 0.0
    
    def connect(self) -> bool:
        """الاتصال والحصول على access token"""
        try:
            auth_data = {
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
                "client_id": self.client_id
            }
            
            response = requests.post(self.auth_url, json=auth_data, timeout=10)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                self.connected = True
                logger.info("[cTrader OpenAPI] ✅ Connected successfully")
                self._update_account_info()
                return True
            else:
                logger.error(f"[cTrader Auth] Failed: {response.status_code}")
                self.connected = False
                return False
        except Exception as e:
            logger.error(f"[cTrader Connect] {e}")
            self.connected = False
            return False
    
    def get_headers(self) -> Dict:
        """رؤوس الطلب"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def _update_account_info(self):
        """تحديث معلومات الحساب"""
        try:
            if not self.connected or not self.access_token:
                return False
            
            url = f"{self.api_url}/accounts/{self.account_id}"
            response = requests.get(url, headers=self.get_headers(), timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.balance = data.get('balance', 0) / 100
                self.equity = data.get('equity', 0) / 100
                logger.info(f"[Account] Balance: ${self.balance:.2f} | Equity: ${self.equity:.2f}")
                return True
            else:
                logger.error(f"[Account Info] Status: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[Account Update] {e}")
            return False
    
    def get_account_info(self) -> Optional[Dict]:
        """قراءة معلومات الحساب"""
        try:
            self._update_account_info()
            return {
                'balance': self.balance,
                'equity': self.equity,
                'account_id': self.account_id,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[Get Account] {e}")
            return None
    
    def get_price(self, symbol: str) -> Optional[Dict]:
        """قراءة السعر الحالي"""
        try:
            if not self.connected:
                return None
            
            url = f"{self.api_url}/symbols/{symbol}/current-quotes"
            response = requests.get(url, headers=self.get_headers(), timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                quote = data.get('quote', {})
                return {
                    'bid': quote.get('bid', 0) / 100000,
                    'ask': quote.get('ask', 0) / 100000
                }
            return None
        except Exception as e:
            logger.error(f"[Get Price {symbol}] {e}")
            return None
    
    def is_connected(self) -> bool:
        return self.connected
    
    def disconnect(self):
        self.connected = False
        self.access_token = None
