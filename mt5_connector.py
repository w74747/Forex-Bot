"""
mt5_connector.py - MetaTrader 5 Real Connection
"""

import MetaTrader5 as mt5
import logging
from config import ExnessConfig

logger = logging.getLogger("mt5")

class MT5Connector:
    def __init__(self):
        self.connected = False
        self.connect()
    
    def connect(self):
        """اتصل بـ MetaTrader 5"""
        try:
            if not mt5.initialize():
                logger.error(f"❌ MT5 Init failed: {mt5.last_error()}")
                return False
            
            if not mt5.login(ExnessConfig.MT5_LOGIN, ExnessConfig.MT5_PASSWORD, ExnessConfig.MT5_SERVER):
                logger.error(f"❌ Login failed: {mt5.last_error()}")
                return False
            
            self.connected = True
            logger.info("✅ Connected to Exness MT5")
            return True
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            return False
    
    def get_price(self, symbol):
        """احصل على السعر الحالي"""
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                return {'bid': tick.bid, 'ask': tick.ask}
            return {'bid': 0, 'ask': 0}
        except Exception as e:
            logger.error(f"Error getting price: {e}")
            return {'bid': 0, 'ask': 0}
    
    def get_all_prices(self, symbols):
        """احصل على جميع الأسعار"""
        prices = {}
        for symbol in symbols:
            prices[symbol] = self.get_price(symbol)
        return prices
    
    def open_trade(self, symbol, order_type, volume, sl, tp):
        """فتح صفقة حقيقية"""
        try:
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                logger.error(f"Cannot get price for {symbol}")
                return None
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL,
                "price": tick.ask if order_type == "BUY" else tick.bid,
                "sl": sl,
                "tp": tp,
                "comment": "Automated Bot Trade",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Trade opened: {symbol} {order_type} {volume} lots")
                return result
            else:
                logger.error(f"Trade failed: {result.comment}")
                return None
        except Exception as e:
            logger.error(f"Error opening trade: {e}")
            return None
    
    def close_trade(self, ticket):
        """إغلاق صفقة"""
        try:
            position = mt5.positions_get(ticket=ticket)
            if not position:
                return False
            
            pos = position[0]
            order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": ticket,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": order_type,
                "price": mt5.symbol_info_tick(pos.symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).bid,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Trade closed: {ticket}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error closing trade: {e}")
            return False
    
    def get_positions(self):
        """احصل على الصفقات المفتوحة"""
        try:
            positions = mt5.positions_get()
            return positions if positions else []
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def shutdown(self):
        """إغلاق الاتصال"""
        try:
            mt5.shutdown()
            logger.info("MT5 shutdown")
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
