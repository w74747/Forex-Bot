"""
telegram_notifier.py - Telegram Notifications with TelegramNotifierV3
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger("telegram")

class TelegramNotifierV3:
    """التيليغرام - إرسال الرسائل والتنبيهات"""
    
    def __init__(self, config):
        self.bot_token = config.bot_token
        self.chat_id = config.chat_id
        self.enabled = config.enabled
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def send_message(self, text):
        """إرسال رسالة نصية"""
        if not self.enabled:
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"[Telegram] {e}")
            return False
    
    def notify_trade_opened(self, symbol, direction, entry_price, sl, tp, lot_size, strategy):
        """إشعار فتح صفقة"""
        emoji = "🟢" if direction == "BUY" else "🔴"
        text = f"""
{emoji} <b>صفقة جديدة</b>

<b>💱 الزوج:</b> {symbol}
<b>📊 الاتجاه:</b> {direction}
<b>📈 السعر:</b> {entry_price:.5f}
<b>🎯 TP:</b> {tp:.5f}
<b>⛔ SL:</b> {sl:.5f}
<b>📦 الحجم:</b> {lot_size}
<b>🤖 الاستراتيجية:</b> {strategy}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_trade_closed(self, symbol, direction, entry_price, exit_price, pnl, reason, strategy):
        """إشعار إغلاق صفقة"""
        pnl_emoji = "✅" if pnl > 0 else "❌"
        pnl_sign = "+" if pnl > 0 else ""
        
        text = f"""
{pnl_emoji} <b>صفقة مغلقة</b>

<b>💱 الزوج:</b> {symbol}
<b>📊 الاتجاه:</b> {direction}
<b>📊 الدخول:</b> {entry_price:.5f}
<b>📊 الخروج:</b> {exit_price:.5f}
<b>💰 الربح/الخسارة:</b> <b>${pnl_sign}{pnl:.2f}</b>
<b>📌 السبب:</b> {reason}
<b>🤖 الاستراتيجية:</b> {strategy}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_system_event(self, message):
        """إشعار حدث نظام"""
        text = f"""
⚙️ <b>تنبيه النظام</b>

{message}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_daily_summary(self, total_trades, wins, losses, daily_pnl, win_rate):
        """تقرير يومي"""
        emoji = "📈" if daily_pnl > 0 else "📉"
        text = f"""
{emoji} <b>التقرير اليومي</b>

<b>📊 الصفقات:</b> {total_trades}
<b>✅ رابحة:</b> {wins}
<b>❌ خاسرة:</b> {losses}
<b>💰 الإجمالي:</b> ${daily_pnl:+.2f}
<b>📈 نسبة النجاح:</b> {win_rate:.1f}%

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_error(self, error_msg):
        """إشعار خطأ"""
        text = f"""
💥 <b>خطأ</b>

{error_msg}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(text)
