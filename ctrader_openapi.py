"""
ctrader_openapi.py - Real cTrader OpenAPI Connection
"""

import requests
import logging
import time

logger = logging.getLogger("ctrader")

class CTraderOpenAPI:
    def __init__(self, client_id, access_token, account_id):
        self.client_id = client_id
        self.access_token = access_token
        self.account_id = account_id
        self.base_url = "https://openapi.ctrader.com"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        self.last_prices = {}
    
    def get_price(self, symbol):
        """احصل على السعر الحالي"""
        try:
            url = f"{self.base_url}/v1/accounts/{self.account_id}/symbols/{symbol}/current"
            response = requests.get(url, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    tick = data['data']
                    bid = float(tick.get('bid', 0))
                    ask = float(tick.get('ask', 0))
                    
                    if bid > 0 and ask > 0:
                        self.last_prices[symbol] = {'bid': bid, 'ask': ask}
                        logger.info(f"[cTrader REAL] {symbol} BID:{bid:.5f} ASK:{ask:.5f}")
                        return {'bid': bid, 'ask': ask}
            
            return self.last_prices.get(symbol, {'bid': 0, 'ask': 0})
        except Exception as e:
            logger.error(f"cTrader error: {e}")
            return self.last_prices.get(symbol, {'bid': 0, 'ask': 0})
    
    def get_all_prices(self, symbols):
        """احصل على أسعار جميع الرموز"""
        prices = {}
        for symbol in symbols:
            prices[symbol] = self.get_price(symbol)
            time.sleep(0.2)  # تجنب throttling
        return prices
