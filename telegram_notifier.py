"""
telegram_notifier.py - Enhanced Telegram Notifications
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger("telegram")

class TelegramNotifier:
    def __init__(self, config):
        self.bot_token = config.bot_token
        self.chat_id = config.chat_id
        self.enabled = config.enabled
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def send_message(self, text):
        """إرسال رسالة نصية"""
        if not self.enabled:
            logger.warning("[Telegram] Notifications disabled")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=data, timeout=10)
            if response.status_code == 200:
                logger.info("[Telegram] Message sent")
                return True
            else:
                logger.error(f"[Telegram] Error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"[Telegram] Send error: {e}")
            return False
    
    def notify_trade_open(self, trade_id, strategy, symbol, direction, entry_price, lot_size, sl_price, tp_price):
        """إخطار عند فتح صفقة"""
        direction_emoji = "🟢" if direction == "BUY" else "🔴"
        
        text = f"""
<b>📊 صفقة جديدة - فتح</b>

<b>ID:</b> #{trade_id}
<b>استراتيجية:</b> {strategy}
<b>الزوج:</b> {symbol}
<b>الاتجاه:</b> {direction_emoji} {direction}
<b>الحجم:</b> {lot_size} لوت
<b>نقطة الدخول:</b> {entry_price:.5f}
<b>🎯 TP:</b> {tp_price:.5f}
<b>🛑 SL:</b> {sl_price:.5f}

<b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_trade_close(self, trade_id, strategy, symbol, direction, entry_price, exit_price, exit_reason, net_pnl):
        """إخطار عند إغلاق صفقة"""
        direction_emoji = "🟢" if direction == "BUY" else "🔴"
        profit_emoji = "✅" if net_pnl > 0 else "❌"
        pnl_color = "52B788" if net_pnl > 0 else "D62828"
        
        text = f"""
<b>📊 صفقة مُغلقة</b>

<b>ID:</b> #{trade_id}
<b>استراتيجية:</b> {strategy}
<b>الزوج:</b> {symbol}
<b>الاتجاه:</b> {direction_emoji} {direction}
<b>نقطة الدخول:</b> {entry_price:.5f}
<b>نقطة الخروج:</b> {exit_price:.5f}
<b>السبب:</b> {exit_reason}

<b>الربح/الخسارة:</b> <u>{profit_emoji} ${net_pnl:+.2f}</u>

<b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_daily_summary(self, total_trades, winning_trades, losing_trades, total_pnl, win_rate, balance):
        """إخطار بملخص اليومي"""
        win_pct = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        pnl_emoji = "📈" if total_pnl > 0 else "📉"
        
        text = f"""
<b>📈 ملخص اليومي</b>

<b>إجمالي الصفقات:</b> {total_trades}
<b>✅ صفقات رابحة:</b> {winning_trades} ({win_pct:.1f}%)
<b>❌ صفقات خاسرة:</b> {losing_trades}

<b>الربح/الخسارة اليومي:</b> {pnl_emoji} <u>${total_pnl:+.2f}</u>
<b>💰 الرصيد:</b> ${balance:.2f}

<b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_monthly_summary(self, month, total_trades, winning_trades, losing_trades, total_pnl, win_rate, balance):
        """إخطار بملخص شهري"""
        win_pct = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        pnl_emoji = "📈" if total_pnl > 0 else "📉"
        
        text = f"""
<b>🎯 ملخص شهري - {month}</b>

<b>إجمالي الصفقات:</b> {total_trades}
<b>✅ صفقات رابحة:</b> {winning_trades} ({win_pct:.1f}%)
<b>❌ صفقات خاسرة:</b> {losing_trades}

<b>الربح/الخسارة الشهري:</b> {pnl_emoji} <u>${total_pnl:+.2f}</u>
<b>معدل النجاح:</b> {win_rate:.2f}%
<b>💰 الرصيد النهائي:</b> ${balance:.2f}

<b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_system_event(self, message):
        """إخطار بحدث نظام"""
        text = f"""
<b>⚙️ حدث نظام</b>

{message}

<b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_emergency_halt(self, reason):
        """إخطار بإيقاف طارئ"""
        text = f"""
<b>🚨 إيقاف طارئ</b>

<b>السبب:</b> {reason}

<b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_capital_update(self, current_balance, strategy_balances):
        """إخطار بتحديث رأس المال"""
        text = f"""
<b>💰 تحديث رأس المال</b>

<b>الرصيد الكلي:</b> ${current_balance:.2f}

<b>توزيع الاستراتيجيات:</b>
- RSI + EMA + MACD: ${strategy_balances.get('RSI_EMA_MACD', 0):.2f}
- Bollinger + Stochastic: ${strategy_balances.get('BB_STOCH', 0):.2f}
- EMA + ATR: ${strategy_balances.get('EMA_ATR', 0):.2f}

<b>الوقت:</b> {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(text)
