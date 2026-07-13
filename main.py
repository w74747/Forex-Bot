import os
import sys
import time
import requests
import psycopg2
from psycopg2 import sql

# --- 1. الإعدادات الأساسية ---
DRY_RUN = True
SYMBOL = "XAUUSD"
INITIAL_BALANCE = 200.0
LOT_SIZE = 0.02

SCALPING_TP_DIST = 1.50   
SCALPING_SL_DIST = 3.00   

PLATFORM_COMMISSION_PER_LOT = 7.00  
ESTIMATED_SPREAD = 0.15             

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
PRIMARY_DB = os.environ.get("DATABASE_URL")
FALLBACK_DB = os.environ.get("FALLBACK_DATABASE_URL")

current_db_url = PRIMARY_DB

# --- 2. محرك الاتصال والأرشفة في قاعدة البيانات ---
def get_db_connection():
    global current_db_url
    try:
        conn = psycopg2.connect(current_db_url, connect_timeout=5)
        return conn
    except Exception as e:
        if current_db_url == PRIMARY_DB and FALLBACK_DB:
            current_db_url = FALLBACK_DB
        else:
            current_db_url = PRIMARY_DB
        try:
            conn = psycopg2.connect(current_db_url, connect_timeout=5)
            log_to_db("DATABASE_FAILOVER", f"تم التحول تلقائياً لقاعدة البيانات الاحتياطية بسبب: {e}")
            return conn
        except:
            return None

# إنشاء الجداول ونظام الأرشيف المتكامل
def init_db():
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            # 1. جدول الصفقات المطور (يحتوي على خانة الرصيد التراكمي بعد الإغلاق)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS virtual_trades (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10),
                    direction VARCHAR(5),
                    entry_price NUMERIC,
                    tp_price NUMERIC,
                    sl_price NUMERIC,
                    status VARCHAR(10) DEFAULT 'OPEN',
                    exit_price NUMERIC,
                    gross_pnl NUMERIC DEFAULT 0,
                    fees NUMERIC DEFAULT 0,
                    net_pnl NUMERIC DEFAULT 0,
                    cumulative_balance NUMERIC DEFAULT 200.0,
                    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # 2. جدول أرشيف لوج النظام بالكامل
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
        print(f"Error init DB: {e}")
    finally:
        conn.close()

# دالة مخصصة لكتابة أي حدث في أرشيف قاعدة البيانات
def log_to_db(log_type, message):
    print(f"[{log_type}] {message}") # طباعة في لوج Railway
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO system_logs (log_type, message) VALUES (%s, %s);", (log_type, message))
            conn.commit()
    except:
        pass
    finally:
        conn.close()

# حساب المجموع التراكمي الفعلي من قاعدة البيانات لتوثيقه مع الصفقة الجديدة
def get_current_balance():
    conn = get_db_connection()
    if not conn: return INITIAL_BALANCE
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT SUM(net_pnl) FROM virtual_trades WHERE status = 'CLOSED';")
            total_net = cur.fetchone()[0]
            return INITIAL_BALANCE + float(total_net if total_net else 0)
    except:
        return INITIAL_BALANCE
    finally:
        conn.close()

# --- 3. تيليجرام والأسعار حية ---
def send_telegram_msg(text):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=5)
        except: pass

def get_live_price():
    url = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT"
    try:
        resp = requests.get(url, timeout=5).json()
        return float(resp['price'])
    except Exception as e:
        log_to_db("PRICE_ERROR", f"فشل جلب السعر الحي: {e}")
        return 2350.0

# --- 4. إدارة الصفقات والمحاكاة الذكية ---
def open_scalping_trade(direction, entry):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM virtual_trades WHERE status = 'OPEN';")
            if cur.fetchone()[0] > 0: return 
            
            tp = entry + SCALPING_TP_DIST if direction == "BUY" else entry - SCALPING_TP_DIST
            sl = entry - SCALPING_SL_DIST if direction == "BUY" else entry + SCALPING_SL_DIST
            
            trade_fees = (PLATFORM_COMMISSION_PER_LOT * LOT_SIZE * 2) + (ESTIMATED_SPREAD * LOT_SIZE * 100)
            
            cur.execute(
                "INSERT INTO virtual_trades (symbol, direction, entry_price, tp_price, sl_price, fees) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;",
                (SYMBOL, direction, entry, tp, sl, trade_fees)
            )
            trade_id = cur.fetchone()[0]
            conn.commit()
            
            log_to_db("TRADE_OPEN", f"تم فتح صفقة خاطفة #{trade_id} على سعر {entry}")
            
            msg = (
                f"⚡ <b>ماكينة السكالبينج: صفقة خاطفة جديدة!</b>\n\n"
                f"🔢 رقم الصفقة: #{trade_id}\n"
                f"📈 الاتجاه: {direction} | ⚖️ اللوت: {LOT_SIZE}\n"
                f"💵 سعر الدخول: {entry:.2f}\n"
                f"🎯 الهدف (TP): {tp:.2f}\n"
                f"🛑 وقف الخسارة (SL): {sl:.2f}\n"
                f"💸 الرسوم المستقطعة للمنصة: {trade_fees:.2f} USD"
            )
            send_telegram_msg(msg)
    except Exception as e:
        log_to_db("TRADE_OPEN_ERROR", f"خطأ عند فتح صفقة: {e}")
    finally:
        conn.close()

def monitor_and_close_trades(current_price):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, direction, entry_price, tp_price, sl_price, fees FROM virtual_trades WHERE status = 'OPEN';")
            open_trades = cur.fetchall()
            
            for trade in open_trades:
                tid, direction, entry, tp, sl, fees = trade
                is_closed = False
                gross_pnl = 0.0
                reason = ""
                
                if direction == "BUY":
                    if current_price >= float(tp):
                        is_closed = True; gross_pnl = (float(tp) - float(entry)) * LOT_SIZE * 100; reason = "🎯 تم قنص الهدف!"
                    elif current_price <= float(sl):
                        is_closed = True; gross_pnl = (float(sl) - float(entry)) * LOT_SIZE * 100; reason = "🛑 ضربت الستوب لحماية الحساب"
                else:
                    if current_price <= float(tp):
                        is_closed = True; gross_pnl = (float(entry) - float(tp)) * LOT_SIZE * 100; reason = "🎯 تم قنص الهدف!"
                    elif current_price >= float(sl):
                        is_closed = True; gross_pnl = (float(entry) - float(sl)) * LOT_SIZE * 100; reason = "🛑 ضربت الستوب لحماية الحساب"
                
                if is_closed:
                    net_pnl = gross_pnl - float(fees)
                    
                    # 1. حساب الرصيد التراكمي المحدث للحساب فوراً
                    cur.execute("SELECT SUM(net_pnl) FROM virtual_trades WHERE status = 'CLOSED';")
                    past_net = cur.fetchone()[0]
                    past_net_val = float(past_net if past_net else 0)
                    new_cumulative_balance = INITIAL_BALANCE + past_net_val + net_pnl
                    
                    # 2. تحديث الصفقة وحفظ الرصيد التراكمي في أرشيفها الخاص بدقة
                    cur.execute(
                        "UPDATE virtual_trades SET status = 'CLOSED', exit_price = %s, gross_pnl = %s, net_pnl = %s, cumulative_balance = %s WHERE id = %s;",
                        (current_price, gross_pnl, net_pnl, new_cumulative_balance, tid)
                    )
                    conn.commit()
                    
                    log_to_db("TRADE_CLOSE", f"تم إغلاق صفقة #{tid} بنتيجة صافية: {net_pnl:+.2f} USD. الرصيد التراكمي الجديد: {new_cumulative_balance:.2f}")
                    
                    status_emoji = "🖨️💵" if net_pnl > 0 else "📉"
                    msg = (
                        f"{status_emoji} <b>تقرير إغلاق الصفقات الخاطفة!</b>\n\n"
                        f"🔢 صفقة رقم: #{tid}\n"
                        f"📊 النتيجة: {reason}\n"
                        f"💵 سعر الخروج الحقيقي: {current_price:.2f}\n"
                        f"💰 الربح الإجمالي: {gross_pnl:+.2f} USD\n"
                        f"💸 الرسوم المستقطعة: -{fees:.2f} USD\n"
                        f"✅ <b>صافي الأرباح المضافة: {net_pnl:+.2f} USD</b>\n"
                        f"💳 <b>المجموع التراكمي للمحفظة: {new_cumulative_balance:.2f} USD</b>"
                    )
                    send_telegram_msg(msg)
    except Exception as e:
        log_to_db("MONITOR_ERROR", f"خطأ أثناء مراقبة الصفقات: {e}")
    finally:
        conn.close()

# --- 5. الفحص الذكي عند الإقلاع ---
def run_post_restore_health_check():
    balance = get_current_balance()
    log_to_db("HEALTH_CHECK", f"بدء الفحص الذكي المطور. الرصيد الحالي الموثق: {balance:.2f} USD")
    msg = (
        f"⚙️ <b>فحص الصلاحية والمطبعة الذكية:</b>\n"
        f"💳 الرصيد التراكمي الحالي: {balance:.2f} USD\n"
        f"🏹 حجم اللوت النشط: {LOT_SIZE}\n"
        f"🗄️ <b>وضع الأرشفة وسجلات النظام:</b> نشط ويحفظ كل السجلات في PostgreSQL."
    )
    send_telegram_msg(msg)

# --- 6. التشغيل الدائم ---
def main():
    init_db()
    log_to_db("SYSTEM_START", "تم ترقية وتشغيل البوت في وضع مطبعة الأموال والأرشفة الشاملة.")
    run_post_restore_health_check()
    
    while True:
        try:
            live_price = get_live_price()
            
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM virtual_trades WHERE status = 'OPEN';")
                    if cur.fetchone()[0] == 0:
                        open_scalping_trade("BUY", live_price)
                conn.close()
            
            monitor_and_close_trades(live_price)
            time.sleep(5)  
        except Exception as e:
            log_to_db("CRITICAL_LOOP_ERROR", f"انهيار مؤقت في الحلقة الأساسية: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
