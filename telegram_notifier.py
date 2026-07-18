"""
telegram_notifier_v3.py - Compact Reports Every 30 Minutes
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger("telegram")

class TelegramNotifierV3:
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
            logger.error(f"[Telegram] {e}")
            return False
    
    def notify_compact_report(self, account_stats, trades_data, monthly_summary):
        """تقرير مختصر كل 30 دقيقة"""
        
        balance = account_stats['current_balance']
        monthly_pnl = account_stats['monthly_pnl']
        total_trades_closed = trades_data['total_trades']
        wins = trades_data['wins']
        losses = trades_data['losses']
        pnl_30min = trades_data['pnl_30min']
        
        # رموز بناءً على الأداء
        monthly_emoji = "📈" if monthly_pnl > 0 else "📉"
        period_emoji = "✅" if pnl_30min >= 0 else "⚠️"
        
        text = f"""
<b>📊 تقرير كل 30 دقيقة</b>

<b>💰 الرصيد:</b> ${balance:.2f}
<b>📈 الشهري:</b> ${monthly_pnl:+.2f}
━━━━━━━━━━━━━━━━━━━━━━
<b>{period_emoji} آخر 30 دقيقة:</b>
- الصفقات: {total_trades_closed} (✅{wins} ❌{losses})
- الربح: ${pnl_30min:+.2f}
━━━━━━━━━━━━━━━━━━━━━━
<b>🎯 الشهر:</b>
- الإجمالي: {monthly_summary['total_trades']}
- معدل النجاح: {monthly_summary['win_rate']:.1f}%

⏰ {datetime.now().strftime('%H:%M')}
"""
        self.send_message(text)
    
    def notify_ai_analysis(self, performance_analysis, code_review):
        """تقرير تحليل DeepSeek"""
        
        text = f"""
<b>🤖 تقرير DeepSeek AI</b>

<b>📊 تحليل الأداء:</b>
{performance_analysis}

━━━━━━━━━━━━━━━━━━━━━━
<b>🔧 مراجعة الكود:</b>
{code_review}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
