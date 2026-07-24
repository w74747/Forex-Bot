"""
telegram_notify.py - Telegram Notifications
"""

import requests
import logging
from config import TelegramConfig

logger = logging.getLogger("telegram")

class TelegramNotifier:
    def __init__(self):
        self.enabled = TelegramConfig.ENABLED
        self.bot_token = TelegramConfig.BOT_TOKEN
        self.chat_id = TelegramConfig.CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
    
    def send_message(self, message):
        """أرسل رسالة"""
        if not self.enabled:
            return False
        
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(self.api_url, json=payload, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False
    
    def notify_trade_open(self, symbol, direction, entry_price):
        msg = f"🔵 <b>Trade Opened</b>\n{symbol} {direction}\nEntry: {entry_price:.5f}"
        self.send_message(msg)
    
    def notify_trade_close(self, symbol, pnl):
        emoji = "🟢" if pnl > 0 else "🔴"
        msg = f"{emoji} <b>Trade Closed</b>\n{symbol}\nP&L: ${pnl:.2f}"
        self.send_message(msg)
    
    def notify_error(self, error):
        msg = f"🚨 <b>Error</b>\n{error}"
        self.send_message(msg)
