"""
نقطة التشغيل الرئيسية - وضع المحاكاة (Paper Trading Simulation)
================================================================
يشغّل البوت على بيانات اصطناعية لعدة "أيام" مضغوطة زمنيًا، ثم يطبع
تقرير تحليلي كامل عن الأداء (بدون أي مخاطرة بأموال حقيقية).
"""

import asyncio
import logging
import statistics
import sys
from datetime import datetime

from config import Config
from execution_engine import ExecutionEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("forex_bot.log", encoding="utf-8"),
    ],
)
# نبقي الطرفية أهدأ (تحذيرات فقط) لأن آلاف التكات ستُنتج آلاف الأسطر خلال المحاكاة السريعة
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.WARNING)
logging.getLogger().addHandler(console)

logger = logging.getLogger("forex_bot.main")


def print_report(engine: ExecutionEngine):
    account = engine.broker.account
    trades = account.closed_trades

    print("\n" + "=" * 60)
    print("تقرير أداء المحاكاة (Paper Trading Report)")
    print("=" * 60)
    print(f"رأس المال الابتدائي     : ${account.starting_equity:.2f}")
    print(f"رأس المال النهائي       : ${account.equity:.2f}")
    net_change = account.equity - account.starting_equity
    pct_change = (net_change / account.starting_equity) * 100
    print(f"صافي التغيّر            : ${net_change:.2f} ({pct_change:+.2f}%)")
    print(f"عدد الصفقات المنفذة     : {len(trades)}")

    if not trades:
        print("لا توجد صفقات كافية لإجراء تحليل إحصائي.")
        print("=" * 60)
        return

    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl <= 0]
    win_rate = (len(wins) / len(trades)) * 100
    total_commission = sum(t.commission for t in trades)
    avg_win = statistics.mean([t.net_pnl for t in wins]) if wins else 0
    avg_loss = statistics.mean([t.net_pnl for t in losses]) if losses else 0

    print(f"نسبة الصفقات الرابحة    : {win_rate:.1f}% ({len(wins)} رابحة / {len(losses)} خاسرة)")
    print(f"متوسط الربح للصفقة     : ${avg_win:.3f}")
    print(f"متوسط الخسارة للصفقة   : ${avg_loss:.3f}")
    print(f"إجمالي العمولات المدفوعة: ${total_commission:.2f}")

    # أقصى تراجع (Max Drawdown) من منحنى الرصيد
    equity_curve = [account.starting_equity]
    running = account.starting_equity
    for t in trades:
        running += t.net_pnl
        equity_curve.append(running)

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        dd = (peak - e) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    print(f"أقصى تراجع (Max Drawdown): {max_dd:.2f}%")

    # تفصيل حسب سبب الإغلاق
    reasons = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    print("\nتفصيل أسباب إغلاق الصفقات:")
    for reason, count in reasons.items():
        print(f"  - {reason}: {count}")

    print("=" * 60)
    print("⚠️  تنبيه هام: هذه بيانات محاكاة اصطناعية (Random Walk) وليست")
    print("    بيانات سوق حقيقية. النتائج هنا تختبر فقط صحة منطق الكود،")
    print("    ولا تُستخدم كدليل على ربحية الاستراتيجية في السوق الفعلي.")
    print("=" * 60 + "\n")


async def main():
    cfg = Config()
    logger.info(f"بدء المحاكاة | رأس المال: ${cfg.starting_equity} | الرافعة: {cfg.leverage}x")
    logger.info(f"الأزواج المستهدفة: {cfg.target_pairs}")

    # نبدأ المحاكاة عند 9:00 صباحًا EST لضمان المرور بدورة يوم كاملة على الأقل
    sim_start = datetime.now(cfg.tz_est).replace(hour=9, minute=0, second=0, microsecond=0)

    engine = ExecutionEngine(cfg, sim_start_est=sim_start, seed=42, real_time_sleep=False)

    # كل "يوم" محاكاة = 24 ساعة زمن افتراضي (مضغوط بسرعة عبر real_time_sleep=False)
    seconds_per_sim_day = 24 * 60 * 60
    total_seconds = seconds_per_sim_day * cfg.simulation_days

    await engine.run(total_sim_seconds=total_seconds)

    print_report(engine)


if __name__ == "__main__":
    asyncio.run(main())
