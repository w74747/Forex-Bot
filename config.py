"""
Config Module
=============
كل الثوابت والمعايير القابلة للتعديل في مكان واحد.
"""

from dataclasses import dataclass, field
from typing import List
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Config:
    # ---------- رأس المال والمخاطر ----------
    starting_equity: float = 1000.0          # رأس المال الافتراضي (وضع تجريبي)
    leverage: float = 20.0                    # نقطة التوازن المكتشفة عبر leverage_sweep.py (أفضل نسبة عائد/مخاطرة)
    risk_per_trade_pct: float = 2.0           # % من رأس المال كحد أقصى مخاطرة لكل صفقة (عدواني)
    max_daily_drawdown_pct: float = 10.0      # إيقاف تلقائي إذا خسر الحساب هذه النسبة في يوم واحد
    max_concurrent_positions: int = 4         # صفقات متعددة بالتوازي لزيادة عدد الفرص

    # ---------- الأصول المستهدفة ----------
    target_pairs: List[str] = field(default_factory=lambda: ["EURUSD", "GBPUSD"])

    # ---------- تكاليف التنفيذ ----------
    commission_per_lot_round_turn: float = 7.0   # $ لكل لوت قياسي (round turn)
    max_allowed_spread_pips: float = 0.3         # أقصى سبريد مسموح به لتنفيذ صفقة
    pip_value_per_lot: float = 10.0              # تقريبي لأزواج XXX/USD بلوت قياسي

    # ---------- استراتيجية الدخول (Mean Reversion) ----------
    atr_period: int = 14                # فترة حساب ATR
    std_period: int = 20                # فترة حساب الانحراف المعياري
    entry_std_multiplier: float = 2.5   # عدد الانحرافات المعيارية لاعتبار السعر "متطرف" (نتيجة البحث المنهجي)
    trailing_stop_pips: float = 4.0     # وقف خسارة متحرك أوسع (بدل السكالبينج الضيق غير المجدي)
    fixed_take_profit_pips: float = 6.0 # جني ربح أوسع يغطي العمولة بهامش صحي (نتيجة البحث المنهجي)

    # ---------- حماية فجوة السعر (Gap Risk Guard) ----------
    # سبب هندسي بحت وليس شرعيًا: مع رافعة 100x، فجوة سعرية بسيطة بين إغلاق
    # وافتتاح السوق (خصوصًا نهاية الأسبوع أو أخبار مفاجئة) قد تُصفّي الحساب
    # بالكامل لأن وقف الخسارة لا يعمل أثناء إغلاق السوق. الإغلاق اليومي هنا
    # هو خط الدفاع الوحيد الفعّال ضد هذا السيناريو مع رافعة بهذا الحجم.
    tz_est: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/New_York"))
    tz_makkah: ZoneInfo = field(default_factory=lambda: ZoneInfo("Asia/Riyadh"))

    freeze_start_hour_est: int = 16      # 4:00 PM EST -> تجميد فتح صفقات جديدة
    freeze_start_minute_est: int = 0
    force_liquidation_hour_est: int = 16     # 4:45 PM EST -> تصفية إجبارية
    force_liquidation_minute_est: int = 45
    rollover_window_end_hour_est: int = 18   # 6:00 PM EST -> نهاية نافذة الخطر
    rollover_window_end_minute_est: int = 0
    cooloff_end_hour_est: int = 18           # 6:15 PM EST -> نهاية فترة التبريد
    cooloff_end_minute_est: int = 15

    # ---------- محاكاة (Paper Trading) ----------
    simulation_days: int = 10
    ticks_per_second: float = 2.0       # سرعة توليد التكات الوهمية (للاختبار السريع)
    log_file: str = "forex_bot.log"
