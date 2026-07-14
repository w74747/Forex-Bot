import os
import sys
import time
import requests
import psycopg2
from psycopg2 import sql

# --- 1. الإعدادات الأساسية ومتعددة الأصول ---
DRY_RUN = True
INITIAL_BALANCE = 200.0

# تعريف الأصول المدعومة مع إعدادات السكالبينج الخاصة بكل منها:
# (TP: جني الأرباح بالدولار، SL: وقف الخسارة بالدولار، LOT_SIZE: حجم العقد)
ASSETS_CONFIG = {
    "XAUUSD": {
        "coingecko_id": "pax-gold",
        "lot_size": 0.02,
        "tp_dist": 1.50,   # هدف سريع (1.5 دولار من حركة الذهب)
        "sl_dist": 3.00,   # ستوب لحماية الحساب من التقلب العنيف للذهب
        "commission": 7.00, # عمولة البروكر لكل لوت كامل
        "spread": 0.15     # سبريد متوسط افتراضي
    },
    "BTCUSD": {
        "coingecko_id": "bitcoin",
        "lot_size": 0.01,
        "tp_dist": 150.0,  # هدف خاطف بالدولار لحركة البيتكوين
        "sl_dist": 300.0,  # وقف خسارة حامٍ للحساب
        "commission": 5.00,
        "spread": 10.0
    },
    "ETHUSD": {
        "coingecko_id": "ethereum",
        "lot_size": 0.05,
        "tp_dist": 8.00,   # هدف سكالبينج خاطف للايثيريوم
        "sl_dist": 16.00,  # وقف خسارة آمن
        "commission": 5.00,
        "spread": 0.50
    }
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
PRIMARY_DB = os.environ.get("DATABASE_URL")
FALLBACK_DB = os.environ.get("FALLBACK_DATABASE_URL")

current_db_url = PRIMARY_DB

# --- 2. محرك قاعدة البيانات والأرشفة التفصيلية ---
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

def init_db():
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            # جدول الصفقات المطور (يحتوي على رمز الأصل وعمود الرصيد التراكمي)
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
            # جدول أرشيف لوج النظام الكامل
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

def log_to_db(log_type, message):
    print(f"[{log_type}] {message}")
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

# --- 3. تيليجرام وجالب الأسعار اللحظية المتعددة ---
def send_telegram_msg(text):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=5)
        except: pass

def get_live_prices():
    # جلب جميع أسعار الأصول المحددة في طلب واحد لتوفير استهلاك الخادم والشبكة
    ids = ",".join([config["coingecko_id"] for config in ASSETS_CONFIG.values()])
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
    prices = {}
    try:
        resp = requests.get(url, timeout=10).json()
        for symbol, config in ASSETS_CONFIG.items():
            cg_id = config["coingecko_id"]
            if cg_id in resp and "usd" in resp[cg_id]:
                prices[symbol] = float(resp[cg_id]["usd"])
            else:
                prices[symbol] = None
    except Exception as e:
        log_to_db("PRICE_ERROR", f"فشل جلب الأسعار المتعددة: {e}")
    return prices

# --- 4. إدارة الصفقات الخاطفة متعددة الأصول ---
def open_scalping_trade(symbol, direction, entry):
    config = ASSETS_CONFIG[symbol]
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            # التحقق مما إذا كانت هناك صفقة مفتوحة بالفعل لهذا الأصل لمنع التكرار المفرط
            cur.execute("SELECT COUNT(*) FROM virtual_trades WHERE symbol = %s AND status = 'OPEN';", (symbol,))
            if cur.fetchone()[0] > 0: return 
            
            tp = entry + config["tp_dist"] if direction == "BUY" else entry - config["tp_dist"]
            sl = entry - config["sl_dist"] if direction == "BUY" else entry + config["sl_dist"]
            
            # حساب رسوم المنصة بدقة للصفقة الحالية بناء على حجم لوت الأصل المحدد
            trade_fees = (config["commission"] * config["lot_size"] * 2) + (config["spread"] * config["lot_size"] * 100)
            
            cur.execute(
                "INSERT INTO virtual_trades (symbol, direction, entry_price, tp_price, sl_price, fees) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;",
                (symbol, direction, entry, tp, sl, trade_fees)
            )
            trade_id = cur.fetchone()[0]
            conn.commit()
            
            log_to_db("TRADE_OPEN", f"تم فتح صفقة {symbol} خاطفة #{trade_id} على سعر {entry}")
            
            msg = (
                f"⚡ <b>ماكينة السكالبينج: صفقة {symbol} جديدة!</b>\n\n"
                f"🔢 رقم الصفقة: #{trade_id}\n"
                f"📈 الاتجاه: {direction} | ⚖️ اللوت: {config['lot_size']}\n"
                f"💵 سعر الدخول: {entry:.2f}\n"
                f"🎯 الهدف (TP): {tp:.2f}\n"
                f"🛑 وقف الخسارة (SL): {sl:.2f}\n"
                f"💸 الرسوم المستقطعة المقدرة: {trade_fees:.2f} USD"
            )
            send_telegram_msg(msg)
    except Exception as e:
        log_to_db("TRADE_OPEN_ERROR", f"خطأ عند فتح صفقة لـ {symbol}: {e}")
    finally:
        conn.close()

def monitor_and_close_trades(prices):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, symbol, direction, entry_price, tp_price, sl_price, fees FROM virtual_trades WHERE status = 'OPEN';")
            open_trades = cur.fetchall()
            
            for trade in open_trades:
                tid, symbol, direction, entry, tp, sl, fees = trade
                current_price = prices.get(symbol)
                if not current_price: continue # في حال تعذر جلب السعر اللحظي لهذا الزوج مؤقتاً
                
                config = ASSETS_CONFIG[symbol]
                is_closed = False
                gross_pnl = 0.0
                reason = ""
                
                # حساب النسبة الحركية الخاصة بكل لوت لكل أصل
                multiplier = 100 if symbol == "XAUUSD" else 1.0 # الذهب يحتاج لمضاعف النقاط أما غيره فيحسب كأصل مباشر
                
                if direction == "BUY":
                    if current_price >= float(tp):
                        is_closed = True; gross_pnl = (float(tp) - float(entry)) * config["lot_size"] * multiplier; reason = "🎯 تم قنص الهدف!"
                    elif current_price <= float(sl):
                        is_closed = True; gross_pnl = (float(sl) - float(entry)) * config["lot_size"] * multiplier; reason = "🛑 ضربت الستوب لحماية رأس المال"
                else: # SELL
                    if current_price <= float(tp):
                        is_closed = True; gross_pnl = (float(entry) - float(tp)) * config["lot_size"] * multiplier; reason = "🎯 تم قنص الهدف!"
                    elif current_price >= float(sl):
                        is_closed = True; gross_pnl = (float(entry) - float(sl)) * config["lot_size"] * multiplier; reason = "🛑 ضربت الستوب لحماية رأس المال"
                
                if is_closed:
                    net_pnl = gross_pnl - float(fees)
                    
                    # 1. حساب الرصيد التراكمي المحدث
                    cur.execute("SELECT SUM(net_pnl) FROM virtual_trades WHERE status = 'CLOSED';")
                    past_net = cur.fetchone()[0]
                    past_net_val = float(past_net if past_net else 0)
                    new_cumulative_balance = INITIAL_BALANCE + past_net_val + net_pnl
                    
                    # 2. التحديث الفوري في الأرشيف
                    cur.execute(
                        "UPDATE virtual_trades SET status = 'CLOSED', exit_price = %s, gross_pnl = %s, net_pnl = %s, cumulative_balance = %s WHERE id = %s;",
                        (current_price, gross_pnl, net_pnl, new_cumulative_balance, tid)
                    )
                    conn.commit()
                    
                    log_to_db("TRADE_CLOSE", f"تم إغلاق صفقة #{tid} على {symbol}. النتيجة الصافية: {net_pnl:+.2f} USD. الرصيد التراكمي: {new_cumulative_balance:.2f}")
                    
                    status_emoji = "🖨️💵" if net_pnl > 0 else "📉"
                    msg = (
                        f"{status_emoji} <b>تقرير إغلاق صفقة {symbol}!</b>\n\n"
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
        log_to_db("MONITOR_ERROR", f"خطأ أثناء مراقبة صفقات الأصول: {e}")
    finally:
        conn.close()

# --- 5. الفحص عند الإقلاع ---
def run_post_restore_health_check():
    balance = get_current_balance()
    log_to_db("HEALTH_CHECK", f"بدء الفحص الذكي للأصول المتعددة. الرصيد الحالي الموثق: {balance:.2f} USD")
    msg = (
        f"⚙️ <b>فحص الصلاحية والمطبعة الذكية المحدثة:</b>\n"
        f"💳 الرصيد التراكمي الحالي: {balance:.2f} USD\n"
        f"📂 الأصول النشطة للتداول: {', '.join(ASSETS_CONFIG.keys())}\n"
        f"🗄️ <b>أرشيف قاعدة البيانات:</b> نشط بالكامل ويحدث الصفقات والـ Logs بدقة تفصيلية."
    )
    send_telegram_msg(msg)

# --- 6. حلقة العمل الأساسية المتواصلة ---
def main():
    init_db()
    log_to_db("SYSTEM_START", "تم إطلاق النسخة متعددة الأصول والأرشفة الدائمة.")
    run_post_restore_health_check()
    
    while True:
        try:
            prices = get_live_prices()
            
            # التحقق من كل أصل وإطلاق صفقات سكالبينج تزامنية
            for symbol, price in prices.items():
                if price is None: continue
                
                conn = get_db_connection()
                if conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM virtual_trades WHERE symbol = %s AND status = 'OPEN';", (symbol,))
                        if cur.fetchone()[0] == 0:
                            # فتح صفقة BUY تجريبية للتحقق من زخم حركة الزوج وسرعة استجابته
                            open_scalping_trade(symbol, "BUY", price)
                    conn.close()
            
            monitor_and_close_trades(prices)
            time.sleep(5)  # مراقبة سريعة كل 5 ثوانٍ لاصطياد الفرص الفائقة
        except Exception as e:
            log_to_db("CRITICAL_LOOP_ERROR", f"انهيار مؤقت في حلقة التداول المتعددة: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
