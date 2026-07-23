"""
Exness FIX Protocol - Direct Real Trading
"""

import socket
import logging
import time
import threading

logger = logging.getLogger("exness_fix")

class ExnessFIX:
    def __init__(self, username, password, host, port):
        self.username = username
        self.password = password
        self.host = host
        self.port = int(port)
        self.socket = None
        self.msg_seq = 1
        self.prices = {}
        self.connected = False
        self.connect()
    
    def connect(self):
        """اتصل بـ FIX Server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            logger.info(f"✅ Connected to {self.host}:{self.port}")
            
            # أرسل Logon
            self.send_logon()
            
            # شغّل receiver في background
            threading.Thread(target=self.receive_messages, daemon=True).start()
            
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            self.connected = False
    
    def send_logon(self):
        """أرسل رسالة Logon"""
        try:
            msg = f"35=A|49=CLIENT|56={self.username}|34={self.msg_seq}|52={self._get_timestamp()}|108=30|141=Y|553={self.username}|554={self.password}|"
            self.send_fix_message(msg)
            self.msg_seq += 1
            logger.info("✅ Logon sent")
        except Exception as e:
            logger.error(f"Logon error: {e}")
    
    def send_fix_message(self, msg):
        """أرسل رسالة FIX"""
        try:
            body = msg.replace("|", "\x01")
            header = f"8=FIX.4.4\x019={len(body)}\x01"
            full_msg = header + body
            checksum = sum(ord(c) for c in full_msg) % 256
            final_msg = full_msg + f"10={checksum:03d}\x01"
            self.socket.send(final_msg.encode())
        except Exception as e:
            logger.error(f"Send error: {e}")
    
    def receive_messages(self):
        """استقبل الرسائل الحقيقية"""
        try:
            buffer = b""
            while self.connected:
                data = self.socket.recv(4096)
                if not data:
                    break
                buffer += data
                
                # معالجة الرسائل
                messages = buffer.split(b"\x01")
                for msg in messages:
                    if msg:
                        self.parse_fix_message(msg.decode('utf-8', errors='ignore'))
        except Exception as e:
            logger.error(f"Receive error: {e}")
    
    def parse_fix_message(self, msg):
        """فسّر رسالة FIX"""
        try:
            parts = msg.split("|")
            for part in parts:
                if "=" in part:
                    tag, value = part.split("=", 1)
                    # استخراج الأسعار من رسائل MarketData
                    if tag == "55":  # Symbol
                        symbol = value
                    elif tag == "270":  # BidPrice
                        bid = float(value)
                    elif tag == "271":  # AskPrice
                        ask = float(value)
                        if symbol and bid and ask:
                            self.prices[symbol] = {'bid': bid, 'ask': ask}
                            logger.info(f"✅ [REAL] {symbol} BID:{bid:.5f} ASK:{ask:.5f}")
        except:
            pass
    
    def _get_timestamp(self):
        """احصل على timestamp"""
        return time.strftime("%Y%m%d-%H:%M:%S")
    
    def get_price(self, symbol):
        """احصل على السعر الحالي"""
        return self.prices.get(symbol, {'bid': 0, 'ask': 0})
    
    def get_all_prices(self, symbols):
        """احصل على جميع الأسعار"""
        return {s: self.get_price(s) for s in symbols}
