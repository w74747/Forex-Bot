"""
Strategy Parameter Sweep
=========================
هدفه: إيجاد الحافة الإحصائية (Expectancy) الحقيقية لمنطق mean-reversion
بمعزل عن الرافعة وحجم رأس المال، عبر اختبار توليفات مختلفة من:
  - entry_std_multiplier (حساسية إشارة الدخول)
  - trailing_stop_pips (وقف الخسارة)
  - fixed_take_profit_pips (جني الربح)

لكل توليفة نحسب Expectancy لكل لوت واحد (بمعزل عن حجم الصفقة/الرافعة)
عبر عدة seeds مختلفة لتفادي الانحياز لعينة عشوائية واحدة (Overfitting).

⚠️ البيانات المستخدمة اصطناعية (Random Walk)، لذا هذا الاختبار يقيس فقط
"صحة بنية الاستراتيجية رياضيًا" (هل التكاليف تُهزم منطقيًا) وليس ربحية
مضمونة في السوق الحقيقي.
"""

import itertools
import statistics
from dataclasses import replace

from config import Config
from market_scanner import MarketScanner, SignalType
from price_feed import SimulatedPriceFeed


def simulate_expectancy(cfg: Config, seed: int, n_ticks: int = 4000):
    """محاكاة مبسطة (بدون asyncio ولا حماية زمنية) لقياس Expectancy لكل لوت=1.0 فقط."""
    scanner = MarketScanner(cfg)
    feed = SimulatedPriceFeed(cfg.target_pairs, seed=seed)

    open_positions = {}  # symbol -> dict(direction, entry, stop, tp)
    trades_net_pnl = []  # بالدولار لكل لوت=1.0 (نطبّع لاحقًا)

    pip = 0.0001
    t = 0.0
    for i in range(n_ticks):
        for symbol in cfg.target_pairs:
            tick = feed.next_tick(symbol, t)
            pos = open_positions.get(symbol)

            if pos is None:
                signal = scanner.on_tick(tick)
                if signal != SignalType.NONE:
                    direction = "BUY" if signal == SignalType.BUY_REVERSION else "SELL"
                    entry = tick.ask if direction == "BUY" else tick.bid
                    if direction == "BUY":
                        stop = entry - cfg.trailing_stop_pips * pip
                        tp = entry + cfg.fixed_take_profit_pips * pip
                    else:
                        stop = entry + cfg.trailing_stop_pips * pip
                        tp = entry - cfg.fixed_take_profit_pips * pip
                    open_positions[symbol] = {
                        "direction": direction, "entry": entry, "stop": stop, "tp": tp
                    }
            else:
                # تحديث الوقف المتحرك
                if pos["direction"] == "BUY":
                    new_stop = tick.bid - cfg.trailing_stop_pips * pip
                    if new_stop > pos["stop"]:
                        pos["stop"] = new_stop
                    exit_reason = None
                    if tick.bid <= pos["stop"]:
                        exit_reason = "SL"
                    elif tick.bid >= pos["tp"]:
                        exit_reason = "TP"
                else:
                    new_stop = tick.ask + cfg.trailing_stop_pips * pip
                    if new_stop < pos["stop"]:
                        pos["stop"] = new_stop
                    exit_reason = None
                    if tick.ask >= pos["stop"]:
                        exit_reason = "SL"
                    elif tick.ask <= pos["tp"]:
                        exit_reason = "TP"

                if exit_reason:
                    exit_price = tick.bid if pos["direction"] == "BUY" else tick.ask
                    pip_diff = (exit_price - pos["entry"]) / pip
                    if pos["direction"] == "SELL":
                        pip_diff = -pip_diff
                    gross = pip_diff * cfg.pip_value_per_lot  # لكل لوت = 1.0
                    commission = cfg.commission_per_lot_round_turn
                    net = gross - commission
                    trades_net_pnl.append(net)
                    del open_positions[symbol]
        t += 20  # نفس sim_step_seconds

    return trades_net_pnl


def evaluate(cfg: Config, seeds):
    all_trades = []
    for seed in seeds:
        all_trades.extend(simulate_expectancy(cfg, seed))
    if len(all_trades) < 20:
        return None  # عينة غير كافية إحصائيًا
    wins = [t for t in all_trades if t > 0]
    losses = [t for t in all_trades if t <= 0]
    win_rate = len(wins) / len(all_trades)
    avg_win = statistics.mean(wins) if wins else 0
    avg_loss = statistics.mean(losses) if losses else 0
    expectancy = statistics.mean(all_trades)
    return {
        "n_trades": len(all_trades),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy_per_lot": expectancy,
    }


def main():
    base_cfg = Config()
    seeds = [1, 2, 3, 4, 5, 6, 7, 8]  # عينات أكثر للتأكد من ثبات النتيجة

    std_multipliers = [2.0, 2.5, 3.0]
    stop_options = [2.5, 3.0, 3.5, 4.0]
    tp_options = [3.0, 4.0, 5.0, 6.0]

    results = []
    combos = list(itertools.product(std_multipliers, stop_options, tp_options))
    print(f"عدد التوليفات المُختبرة: {len(combos)}")

    for std_mult, sl, tp in combos:
        cfg = replace(base_cfg, entry_std_multiplier=std_mult, trailing_stop_pips=sl, fixed_take_profit_pips=tp)
        res = evaluate(cfg, seeds)
        if res:
            results.append({"std_mult": std_mult, "sl": sl, "tp": tp, **res})

    results.sort(key=lambda r: r["expectancy_per_lot"], reverse=True)

    print("\nأفضل 10 توليفات حسب Expectancy لكل لوت (بالدولار):")
    print(f"{'std':>5} {'SL':>5} {'TP':>5} {'صفقات':>7} {'فوز%':>7} {'Expectancy/lot':>16}")
    for r in results[:10]:
        print(f"{r['std_mult']:>5} {r['sl']:>5} {r['tp']:>5} {r['n_trades']:>7} "
              f"{r['win_rate']*100:>6.1f}% {r['expectancy_per_lot']:>15.4f}$")

    print("\nأسوأ 5 توليفات (للمقارنة):")
    for r in results[-5:]:
        print(f"{r['std_mult']:>5} {r['sl']:>5} {r['tp']:>5} {r['n_trades']:>7} "
              f"{r['win_rate']*100:>6.1f}% {r['expectancy_per_lot']:>15.4f}$")

    positive = [r for r in results if r["expectancy_per_lot"] > 0]
    print(f"\nعدد التوليفات ذات Expectancy موجب: {len(positive)} من أصل {len(results)}")

    return results


if __name__ == "__main__":
    main()
