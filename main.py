"""
paper_trading_live.py (v2)
============================
تحديث: إضافة USDJPY وAUDUSD لتنويع حقيقي (ارتباط إحصائي أقل مع EUR/GBP).

⚠️ تصحيح مهم لزوج USDJPY تحديدًا: قيمة النقطة بالدولار لأزواج الين
(XXX/JPY) ليست ثابتة $10 لكل لوت كما في EURUSD/GBPUSD/AUDUSD (لأن
عملة التسعير Quote Currency هي الين وليست الدولار). قيمتها تتغير مع
سعر الصرف نفسه، لذا تُحسب ديناميكيًا هنا بدل استخدام رقم ثابت خاطئ.
"""

import os
import time
import requests
import psycopg2
from collections import deque
from statistics import mean, pstdev
from datetime import datetime, timezone

# ---------- الإعدادات ----------
DATABASE_URL = os.environ.get("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

INITIAL_BALANCE = 200.0
POLL_SECONDS = 30

STD_WINDOW = 20
ENTRY_STD_MULTIPLIER = 2.5
SL_PIPS = 4.0
TP_PIPS = 6.0
LOT_UNITS = 1000
LOT_SIZE = LOT_UNITS / 100_000  # = 0.01

# is_jpy_pair: يُستخدم لحساب قيمة النقطة ديناميكيًا بدل رقم ثابت خاطئ
ASSETS = {
    "EURUSD": {"pip_size": 0.0001, "assumed_spread_pips": 0.8, "commission_per_lot": 7.0, "is_jpy_pair": False},
    "GBPUSD": {"pip_size": 0.0001, "assumed_spread_pips": 1.2, "commission_per_lot": 7.0, "is_jpy_pair": False},
    "USDJPY": {"pip_size": 0.01,   "assumed_spread_pips": 1.0, "commission_per_lot": 7.0, "is_jpy_pair": True},
    "AUDUSD": {"pip_size": 0.0001, "assumed_spread_pips": 1.5, "commission_per_lot": 7.0, "is_jpy_pair": False},
}

price_windows = {sym: deque(maxlen=STD_WINDOW) for sym in ASSETS}
open_positions = {}


def pip_value_per_lot(symbol, current_price):
    """
    قيمة النقطة بالدولار لكل لوت قياسي (1.0 لوت = 100,000 وحدة):
      - أزواج XXX/USD (اليورو، الإسترليني، الأسترالي): ثابتة $10 دائمًا
      - أزواج XXX/JPY: تتغير مع السعر لأن عملة التسعير ليست الدولار
        الصيغة: (pip_size × 100,000) ÷ السعر الحالي USDJPY
    """
    cfg = ASSETS[symbol]
    if cfg["is_jpy_pair"]:
        return (cfg["pip_size"] * 100_000) / current_price
    return 10.0


# ---------- قاعدة البيانات ----------
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        log_event("DB_CONNECTION_ERROR", str(e))
        return None


def init_db():
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS live_paper_trades (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    direction VARCHAR(5) NOT NULL,
                    entry_price NUMERIC NOT NULL,
                    sl_price NUMERIC NOT NULL,
                    tp_price NUMERIC NOT NULL,
                    status VARCHAR(10) DEFAULT 'OPEN',
                    exit_price NUMERIC,
                    exit_reason VARCHAR(20),
                    gross_pnl NUMERIC,
                    commission NUMERIC,
                    net_pnl NUMERIC,
                    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id SERIAL PRIMARY KEY,
                    log_type VARCHAR(30),
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
    except Exception as e:
        print(f"[DB INIT ERROR] {e}")
    finally:
        conn.close()


def log_event(log_type, message):
    print(f"[{log_type}] {message}")
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO system_logs (log_type, message) VALUES (%s, %s);", (log_type, message))
            conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def get_cumulative_net_pnl():
    conn = get_db_connection()
    if not conn:
        return 0.0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(net_pnl), 0) FROM live_paper_trades WHERE status = 'CLOSED';")
            return float(cur.fetchone()[0])
    except Exception:
        return 0.0
    finally:
        conn.close()


def insert_open_trade(symbol, direction, entry, sl, tp):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO live_paper_trades (symbol, direction, entry_price, sl_price, tp_price) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id;",
                (symbol, direction, entry, sl, tp)
            )
            trade_id = cur.fetchone()[0]
            conn.commit()
            return trade_id
    except Exception as e:
        log_event("TRADE_INSERT_ERROR", str(e))
        return None
    finally:
        conn.close()


def close_trade_in_db(trade_id, exit_price, exit_reason, gross_pnl, commission, net_pnl):
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE live_paper_trades SET status='CLOSED', exit_price=%s, exit_reason=%s, "
                "gross_pnl=%s, commission=%s, net_pnl=%s, closed_at=CURRENT_TIMESTAMP WHERE id=%s;",
                (exit_price, exit_reason, gross_pnl, commission, net_pnl, trade_id)
            )
            conn.commit()
    except Exception as e:
        log_event("TRADE_CLOSE_ERROR", str(e))
    finally:
        conn.close()


# ---------- تيليجرام ----------
def send_telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception:
        pass


# ---------- الأسعار الحقيقية ----------
def get_live_prices():
    url = "https://www.freeforexapi.com/api/live?pairs=" + ",".join(ASSETS.keys())
    prices = {}
    try:
        resp = requests.get(url, timeout=10).json()
        rates = resp.get("rates", {})
        for symbol in ASSETS:
            if symbol in rates and "rate" in rates[symbol]:
                prices[symbol] = float(rates[symbol]["rate"])
    except Exception as e:
        log_event("PRICE_FETCH_ERROR", str(e))
    return prices


def mid_to_bid_ask(symbol, mid_price):
    cfg = ASSETS[symbol]
    half_spread = (cfg["assumed_spread_pips"] / 2) * cfg["pip_size"]
    return mid_price - half_spread, mid_price + half_spread


# ---------- الاستراتيجية ----------
def scan_signal(symbol, mid_price):
    window = price_windows[symbol]
    window.append(mid_price)
    if len(window) < STD_WINDOW:
        return None
    std = pstdev(window)
    m = mean(window)
    if std == 0:
        return None
    z = (mid_price - m) / std
    if z <= -ENTRY_STD_MULTIPLIER:
        return "BUY"
    if z >= ENTRY_STD_MULTIPLIER:
        return "SELL"
    return None


# ---------- فتح/إغلاق الصفقات ----------
def try_open_trade(symbol, bid, ask):
    if symbol in open_positions:
        return
    mid = (bid + ask) / 2
    signal = scan_signal(symbol, mid)
    if signal is None:
        return

    cfg = ASSETS[symbol]
    entry = ask if signal == "BUY" else bid
    if signal == "BUY":
        sl = entry - SL_PIPS * cfg["pip_size"]
        tp = entry + TP_PIPS * cfg["pip_size"]
    else:
        sl = entry + SL_PIPS * cfg["pip_size"]
        tp = entry - TP_PIPS * cfg["pip_size"]

    trade_id = insert_open_trade(symbol, signal, entry, sl, tp)
    if trade_id is None:
        return

    open_positions[symbol] = {"id": trade_id, "direction": signal, "entry": entry, "sl": sl, "tp": tp}
    log_event("TRADE_OPEN", f"#{trade_id} {symbol} {signal} @ {entry:.5f}")
    send_telegram(
        f"⚡ <b>صفقة {symbol} جديدة (بيانات حقيقية)</b>\n"
        f"#{trade_id} | {signal} | لوت {LOT_SIZE}\n"
        f"دخول: {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f}"
    )


def try_close_trade(symbol, bid, ask):
    pos = open_positions.get(symbol)
    if pos is None:
        return

    cfg = ASSETS[symbol]
    direction = pos["direction"]
    exit_reason = None
    exit_price = None

    if direction == "BUY":
        if bid >= pos["tp"]:
            exit_reason, exit_price = "TAKE_PROFIT", bid
        elif bid <= pos["sl"]:
            exit_reason, exit_price = "STOP_LOSS", bid
    else:
        if ask <= pos["tp"]:
            exit_reason, exit_price = "TAKE_PROFIT", ask
        elif ask >= pos["sl"]:
            exit_reason, exit_price = "STOP_LOSS", ask

    if exit_reason is None:
        return

    pip_diff = (exit_price - pos["entry"]) / cfg["pip_size"]
    if direction == "SELL":
        pip_diff = -pip_diff

    pv = pip_value_per_lot(symbol, exit_price)
    gross_pnl = pip_diff * pv * LOT_SIZE
    commission = cfg["commission_per_lot"] * LOT_SIZE
    net_pnl = gross_pnl - commission

    close_trade_in_db(pos["id"], exit_price, exit_reason, gross_pnl, commission, net_pnl)
    del open_positions[symbol]

    cumulative = INITIAL_BALANCE + get_cumulative_net_pnl()
    emoji = "🟢" if net_pnl > 0 else "🔴"
    log_event("TRADE_CLOSE", f"#{pos['id']} {symbol} {exit_reason} صافي={net_pnl:+.2f}")
    send_telegram(
        f"{emoji} <b>إغلاق صفقة {symbol}</b>\n"
        f"#{pos['id']} | {exit_reason}\n"
        f"خروج: {exit_price:.5f}\n"
        f"إجمالي: {gross_pnl:+.2f}$ | عمولة: -{commission:.2f}$\n"
        f"✅ صافي: {net_pnl:+.2f}$\n"
        f"💳 الرصيد التراكمي: {cumulative:.2f}$"
    )


# ---------- الحلقة الرئيسية ----------
def main():
    init_db()
    cumulative = INITIAL_BALANCE + get_cumulative_net_pnl()
    log_event("SYSTEM_START", f"بدء التشغيل. الرصيد التراكمي: {cumulative:.2f}$")
    send_telegram(
        f"🚀 <b>نظام Paper Trading ببيانات فوركس حقيقية بدأ العمل (v2)</b>\n"
        f"الأزواج: {', '.join(ASSETS.keys())}\n"
        f"💳 الرصيد التراكمي الحالي: {cumulative:.2f}$\n"
        f"⚠️ هذه صفقات محاكاة وهمية بأسعار حقيقية - وليست تداولاً فعليًا."
    )

    while True:
        try:
            prices = get_live_prices()
            for symbol, mid in prices.items():
                bid, ask = mid_to_bid_ask(symbol, mid)
                try_close_trade(symbol, bid, ask)
                try_open_trade(symbol, bid, ask)
            time.sleep(POLL_SECONDS)
        except Exception as e:
            log_event("MAIN_LOOP_ERROR", str(e))
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
