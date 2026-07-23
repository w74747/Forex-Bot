"""
Exness MT5 Connection - Real Trading
"""

import MetaTrader5 as mt5
import logging

logger = logging.getLogger("exness")

class ExnessMT5:
    def __init__(self, server, login, password):
        self.server = server
        self.login = int(login)
        self.password = password
        self.connect()
    
    def connect(self):
        """اتصل بـ MT5"""
        if not mt5.initialize():
            logger.error(f"MT5 init failed: {mt5.last_error()}")
            return False
        
        if not mt5.login(self.login, self.password, self.server):
            logger.error(f"Login failed: {mt5.last_error()}")
            return False
        
        logger.info("✅ Connected to Exness MT5")
        return True
    
    def get_price(self, symbol):
        """احصل على السعر الحالي"""
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                logger.info(f"✅ {symbol} BID:{tick.bid:.5f} ASK:{tick.ask:.5f}")
                return {'bid': tick.bid, 'ask': tick.ask}
            else:
                logger.error(f"Failed to get price for {symbol}")
                return {'bid': 0, 'ask': 0}
        except Exception as e:
            logger.error(f"Error: {e}")
            return {'bid': 0, 'ask': 0}
    
    def open_trade(self, symbol, direction, volume):
        """فتح صفقة حقيقية"""
        try:
            point = mt5.symbol_info(symbol).point
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
                "price": mt5.symbol_info_tick(symbol).ask if direction == "BUY" else mt5.symbol_info_tick(symbol).bid,
                "sl": mt5.symbol_info_tick(symbol).ask - 50 * point if direction == "BUY" else mt5.symbol_info_tick(symbol).bid + 50 * point,
                "tp": mt5.symbol_info_tick(symbol).ask + 100 * point if direction == "BUY" else mt5.symbol_info_tick(symbol).bid - 100 * point,
                "comment": "Bot Trade",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Trade opened: {symbol} {direction}")
                return result
            else:
                logger.error(f"Trade failed: {result.comment}")
                return None
        except Exception as e:
            logger.error(f"Exception: {e}")
            return None
    
    def close_trade(self, ticket):
        """إغلاق صفقة"""
        try:
            position = mt5.positions_get(ticket=ticket)
            if position:
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": ticket,
                    "symbol": position[0].symbol,
                    "volume": position[0].volume,
                    "type": mt5.ORDER_TYPE_SELL if position[0].type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                    "price": mt5.symbol_info_tick(position[0].symbol).ask if position[0].type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position[0].symbol).bid,
                }
                result = mt5.order_send(request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(f"✅ Trade closed: {ticket}")
                    return True
        except Exception as e:
            logger.error(f"Exception: {e}")
        return False
