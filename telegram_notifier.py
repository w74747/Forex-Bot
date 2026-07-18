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
        """إرسال رسالة"""
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
            logger.error(f"[Telegram] Send error: {e}")
            return False
    
    def notify_trade_open(self, trade_id, strategy, symbol, direction, entry_price, lot_size, sl_price, tp_price):
        """إخطار فتح صفقة"""
        direction_emoji = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
        
        text = f"""
<b>📊 صفقة جديدة</b>

<b>ID:</b> #{trade_id}
<b>الاستراتيجية:</b> {strategy}
<b>الزوج:</b> {symbol}
<b>الاتجاه:</b> {direction_emoji}
<b>الحجم:</b> <u>{lot_size} لوت</u>
<b>نقطة الدخول:</b> {entry_price:.5f}
<b>🎯 TP:</b> {tp_price:.5f}
<b>🛑 SL:</b> {sl_price:.5f}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_trade_close(self, trade_id, strategy, symbol, direction, entry_price, exit_price, 
                          exit_reason, gross_pnl, net_pnl, current_balance, monthly_pnl):
        """إخطار إغلاق صفقة مع الأرباح"""
        direction_emoji = "🟢" if direction == "BUY" else "🔴"
        profit_emoji = "✅" if net_pnl > 0 else "❌"
        pnl_indicator = "📈" if net_pnl > 0 else "📉"
        
        text = f"""
<b>📊 صفقة مُغلقة</b>

<b>ID:</b> #{trade_id}
<b>الاستراتيجية:</b> {strategy}
<b>الزوج:</b> {symbol} {direction_emoji}
━━━━━━━━━━━━━━━━━━━━━━
<b>نقطة الدخول:</b> {entry_price:.5f}
<b>نقطة الخروج:</b> {exit_price:.5f}
<b>السبب:</b> {exit_reason}
━━━━━━━━━━━━━━━━━━━━━━
<b>الربح الإجمالي:</b> ${gross_pnl:+.2f}
<b>العمولة:</b> -${abs(net_pnl - gross_pnl):.2f}
<b>{pnl_indicator} الربح النهائي:</b> <u>{profit_emoji} ${net_pnl:+.2f}</u>
━━━━━━━━━━━━━━━━━━━━━━
<b>💰 الرصيد الحالي:</b> ${current_balance:.2f}
<b>📈 الربح الشهري:</b> ${monthly_pnl:+.2f}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_hourly_summary(self, account_stats, trades_today):
        """ملخص ساعي"""
        balance = account_stats['current_balance']
        monthly = account_stats['monthly_pnl']
        unrealized = account_stats['unrealized_pnl']
        
        monthly_emoji = "📈" if monthly > 0 else "📉"
        
        text = f"""
<b>⏰ ملخص ساعي</b>

<b>💰 الرصيد:</b> ${balance:.2f}
<b>المبلغ المستثمر:</b> ${account_stats['starting_balance']:.2f}
━━━━━━━━━━━━━━━━━━━━━━
<b>{monthly_emoji} الربح الشهري:</b> <u>${monthly:+.2f}</u>
<b>📊 الأرباح المعلقة:</b> ${unrealized:+.2f}
<b>💹 الإجمالي:</b> <u>${balance + unrealized:+.2f}</u>
━━━━━━━━━━━━━━━━━━━━━━
<b>الصفقات اليوم:</b> {trades_today}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_daily_summary(self, account_stats, total_trades, winning_trades, losing_trades):
        """ملخص يومي"""
        balance = account_stats['current_balance']
        monthly = account_stats['monthly_pnl']
        
        if total_trades > 0:
            win_rate = (winning_trades / total_trades) * 100
        else:
            win_rate = 0
        
        monthly_emoji = "📈" if monthly > 0 else "📉"
        
        text = f"""
<b>📊 ملخص يومي</b>

<b>📊 إجمالي الصفقات:</b> {total_trades}
<b>✅ صفقات رابحة:</b> {winning_trades} ({win_rate:.1f}%)
<b>❌ صفقات خاسرة:</b> {losing_trades}
━━━━━━━━━━━━━━━━━━━━━━
<b>💰 الرصيد:</b> ${balance:.2f}
<b>{monthly_emoji} الربح الشهري:</b> <u>${monthly:+.2f}</u>
━━━━━━━━━━━━━━━━━━━━━━
<b>معدل النجاح:</b> {win_rate:.1f}%

📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_monthly_end(self, month, account_stats, total_trades, winning_trades, losing_trades):
        """ملخص نهاية الشهر"""
        balance = account_stats['current_balance']
        monthly = account_stats['monthly_pnl']
        
        if total_trades > 0:
            win_rate = (winning_trades / total_trades) * 100
        else:
            win_rate = 0
        
        monthly_emoji = "📈" if monthly > 0 else "📉"
        roi = ((balance - account_stats['starting_balance']) / account_stats['starting_balance']) * 100
        
        text = f"""
<b>🎯 ملخص نهاية الشهر - {month}</b>

<b>📊 إجمالي الصفقات:</b> {total_trades}
<b>✅ صفقات رابحة:</b> {winning_trades} ({win_rate:.1f}%)
<b>❌ صفقات خاسرة:</b> {losing_trades}
━━━━━━━━━━━━━━━━━━━━━━
<b>💰 الرصيد الابتدائي:</b> ${account_stats['starting_balance']:.2f}
<b>💰 الرصيد النهائي:</b> ${balance:.2f}
<b>{monthly_emoji} الربح الشهري:</b> <u>${monthly:+.2f}</u>
━━━━━━━━━━━━━━━━━━━━━━
<b>العائد (ROI):</b> {roi:+.2f}%
<b>معدل النجاح:</b> {win_rate:.1f}%

📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
    
    def notify_system_event(self, message):
        """إخطار حدث نظام"""
        text = f"""
<b>⚙️ حدث نظام</b>

{message}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
