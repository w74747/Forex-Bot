"""
Leverage Comparison Sweep
=========================
يشغّل المحرك الكامل (مع حماية فجوة السعر، حد الخسارة اليومي، حجم الصفقة
المبني على % مخاطرة) على نفس الاستراتيجية المُحسّنة (من param_sweep.py)
عند مستويات رافعة مختلفة، لإيجاد نقطة التوازن بين العائد والمخاطرة.
"""

import asyncio
import statistics
from dataclasses import replace
from datetime import datetime

from config import Config
from execution_engine import ExecutionEngine


def max_drawdown_pct(equity_curve):
    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        dd = (peak - e) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
    return max_dd


async def run_one(cfg: Config, seed: int, sim_days: int):
    sim_start = datetime.now(cfg.tz_est).replace(hour=9, minute=0, second=0, microsecond=0)
    engine = ExecutionEngine(cfg, sim_start_est=sim_start, seed=seed, real_time_sleep=False)
    total_seconds = 24 * 60 * 60 * sim_days
    await engine.run(total_sim_seconds=total_seconds)

    account = engine.broker.account
    trades = account.closed_trades

    equity_curve = [account.starting_equity]
    running = account.starting_equity
    for t in trades:
        running += t.net_pnl
        equity_curve.append(running)

    final_return_pct = (account.equity - account.starting_equity) / account.starting_equity * 100
    dd = max_drawdown_pct(equity_curve)
    win_rate = (len([t for t in trades if t.net_pnl > 0]) / len(trades) * 100) if trades else 0

    return {
        "final_equity": account.equity,
        "return_pct": final_return_pct,
        "max_dd_pct": dd,
        "n_trades": len(trades),
        "win_rate": win_rate,
        "wiped_out": account.equity <= account.starting_equity * 0.1,  # خسارة 90%+ = عمليًا منتهي
    }


async def main():
    base_cfg = Config()
    leverages = [1, 5, 10, 20, 50, 100]
    seeds = [11, 22, 33]  # عدة عينات لكل مستوى رافعة
    sim_days = 10

    print(f"مقارنة {len(leverages)} مستويات رافعة × {len(seeds)} عينات × {sim_days} أيام محاكاة")
    print("=" * 90)
    print(f"{'رافعة':>8} {'متوسط العائد%':>15} {'أسوأ عائد%':>13} {'متوسط أقصى تراجع%':>20} {'صفقات(متوسط)':>15} {'حالات إفلاس':>12}")

    summary_rows = []
    for lev in leverages:
        cfg = replace(base_cfg, leverage=float(lev))
        run_results = []
        for seed in seeds:
            res = await run_one(cfg, seed, sim_days)
            run_results.append(res)

        returns = [r["return_pct"] for r in run_results]
        dds = [r["max_dd_pct"] for r in run_results]
        n_trades_avg = statistics.mean([r["n_trades"] for r in run_results])
        wipeouts = sum(1 for r in run_results if r["wiped_out"])

        avg_return = statistics.mean(returns)
        worst_return = min(returns)
        avg_dd = statistics.mean(dds)

        summary_rows.append({
            "leverage": lev, "avg_return": avg_return, "worst_return": worst_return,
            "avg_dd": avg_dd, "n_trades_avg": n_trades_avg, "wipeouts": wipeouts,
        })

        print(f"{lev:>7}x {avg_return:>14.2f}% {worst_return:>12.2f}% {avg_dd:>19.2f}% "
              f"{n_trades_avg:>15.0f} {wipeouts:>11}/{len(seeds)}")

    print("=" * 90)

    # نقطة التوازن: أفضل نسبة عائد-إلى-مخاطرة (Return / MaxDD) بدون أي حالة إفلاس
    safe_rows = [r for r in summary_rows if r["wipeouts"] == 0 and r["avg_return"] > 0]
    if safe_rows:
        best = max(safe_rows, key=lambda r: r["avg_return"] / max(r["avg_dd"], 0.01))
        print(f"\n✅ أفضل نقطة توازن (عائد/مخاطرة) بدون أي حالة إفلاس: رافعة {best['leverage']}x")
        print(f"   متوسط العائد: {best['avg_return']:.2f}% | متوسط أقصى تراجع: {best['avg_dd']:.2f}%")
    else:
        print("\n⚠️ لم يُحقق أي مستوى رافعة عائدًا موجبًا بدون حالات إفلاس في هذه العينة.")


if __name__ == "__main__":
    asyncio.run(main())
