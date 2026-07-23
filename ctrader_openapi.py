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
        self.symbol_ids = {}
        self._load_symbols()
    
    def _load_symbols(self):
        """احصل على معرفات الرموز"""
        try:
            url = f"{self.base_url}/v1/accounts/{self.account_id}/symbols"
            response = requests.get(url, headers=self.headers, timeout=10)
            logger.debug(f"Symbols endpoint: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                symbols = data.get('data', [])
                
                for sym in symbols:
                    name = sym.get('name', '')
                    sid = sym.get('symbolId', '')
                    if name and sid:
                        self.symbol_ids[name] = sid
                        logger.info(f"[cTrader] Found {name} = {sid}")
                        
            else:
                logger.warning(f"Failed to load symbols: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error loading symbols: {e}")
    
    def get_price(self, symbol):
        """احصل على السعر باستخدام معرف الرمز"""
        try:
            if symbol not in self.symbol_ids:
                logger.warning(f"Symbol {symbol} not found in IDs")
                return {'bid': 0, 'ask': 0}
            
            symbol_id = self.symbol_ids[symbol]
            url = f"{self.base_url}/v1/accounts/{self.account_id}/symbols/{symbol_id}/current"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            logger.debug(f"Price {symbol}: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    tick = data['data']
                    bid = float(tick.get('bid', 0))
                    ask = float(tick.get('ask', 0))
                    
                    if bid > 0 and ask > 0:
                        self.last_prices[symbol] = {'bid': bid, 'ask': ask}
                        logger.info(f"✅ [cTrader] {symbol} BID:{bid:.5f} ASK:{ask:.5f}")
                        return {'bid': bid, 'ask': ask}
            else:
                logger.warning(f"Price error for {symbol}: {response.status_code}")
                
            return self.last_prices.get(symbol, {'bid': 0, 'ask': 0})
        except Exception as e:
            logger.error(f"Exception getting price for {symbol}: {e}")
            return self.last_prices.get(symbol, {'bid': 0, 'ask': 0})
    
    def get_all_prices(self, symbols):
        """احصل على أسعار متعددة"""
        prices = {}
        for symbol in symbols:
            prices[symbol] = self.get_price(symbol)
            time.sleep(0.3)
        return prices
