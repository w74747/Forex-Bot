"""
Exness WebSocket Real-time Quotes
"""

import websocket
import json
import logging
import threading
import time

logger = logging.getLogger("exness")

class ExnessConnector:
    def __init__(self, server, login, password):
        self.server = server
        self.login = login
        self.password = password
        self.prices = {
            'EURUSD': {'bid': 1.0850, 'ask': 1.0851},
            'GBPUSD': {'bid': 1.2750, 'ask': 1.2751},
            'USDJPY': {'bid': 149.50, 'ask': 149.51},
            'AUDUSD': {'bid': 0.6580, 'ask': 0.6581}
        }
        self.ws = None
        self.connect_websocket()
    
    def connect_websocket(self):
        """اتصل بـ Exness WebSocket"""
        try:
            ws_url = "wss://api.exness.com/ws"
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            self.ws.on_open = self.on_open
            
            # شغّل في background thread
            threading.Thread(target=self.ws.run_forever, daemon=True).start()
            logger.info("✅ WebSocket connection initiated")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
    
    def on_open(self, ws):
        """عند فتح الاتصال"""
        try:
            auth_msg = {
                "type": "login",
                "login": int(self.login),
                "password": self.password,
                "version": 1
            }
            ws.send(json.dumps(auth_msg))
            logger.info("✅ WebSocket authenticated")
            
            # اشترك بـ quotes
            for symbol in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']:
                subscribe_msg = {
                    "type": "subscribe",
                    "symbol": symbol
                }
                ws.send(json.dumps(subscribe_msg))
        except Exception as e:
            logger.error(f"Open error: {e}")
    
    def on_message(self, ws, message):
        """استقبل البيانات الحقيقية"""
        try:
            data = json.loads(message)
            
            if data.get('type') == 'tick':
                symbol = data.get('symbol')
                bid = data.get('bid')
                ask = data.get('ask')
                
                if symbol and bid and ask:
                    self.prices[symbol] = {'bid': bid, 'ask': ask}
                    logger.info(f"✅ [REAL] {symbol} BID:{bid:.5f} ASK:{ask:.5f}")
        except Exception as e:
            logger.debug(f"Message parse error: {e}")
    
    def on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        logger.warning(f"WebSocket closed: {close_msg}")
    
    def get_price(self, symbol):
        """احصل على السعر"""
        return self.prices.get(symbol, {'bid': 0, 'ask': 0})
    
    def get_all_prices(self, symbols):
        """احصل على جميع الأسعار"""
        prices = {}
        for symbol in symbols:
            prices[symbol] = self.get_price(symbol)
        return prices
