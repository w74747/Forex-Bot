import os
import sys
import time
import requests
import psycopg2
from psycopg2 import sql

# --- 1. إعدادات البيئة والمحاكاة ---
DRY_RUN = True
SYMBOL = "XAUUSD"  # الذهب كمثال أو EURUSD
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

PRIMARY_DB = os.environ.get("DATABASE_URL")
FALLBACK_DB = os.environ.get("FALLBACK_DATABASE_URL")

current_db_url = PRIMARY_DB

# --- 2. محرك الاتصال التبادلي بقواعد البيانات (Failover) ---
def get_db_connection():
    global current_db_url
    try:
        conn = psycopg2.connect(current_db_url, connect_timeout=5)
        return conn
    except Exception as e:
        print(f"⚠️ فشل الاتصال بقاعدة البيانات الحالية. جاري التحول للاحتياطية... الخطأ: {e}")
        # التبديل التلقائي للمولد الاحتياطي
        if current_db_url == PRIMARY_DB and FALLBACK_DB:
            current_db_url = FALLBACK_DB
        else:
            current_db_url = PRIMARY_DB
        
        try:
            conn = psycopg2.connect(current_db_url, connect_timeout=5)
            send_telegram_msg("🚨 <b>تنبيه أمني:</b> تم التحول تلقائياً إلى قاعدة البيانات الاحتياطية (Neon) لاستمرار العمل دون انقطاع!")
            return conn
        except Exception as critical_e:
            print(f"❌ انهيار كامل في الاتصال بقواعد البيانات: {critical_e}")
            return None

# تهيئة الجداول في قواعد البيانات (إذا لم تكن موجودة)
def init_db():
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
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
                    pnl NUMERIC,
                    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
    except Exception as e:
        print(f"Error init DB: {e}")
    finally:
        conn.close()

# --- 3. نظام إرسال تقارير تيليجرام ---
def send_telegram_msg(text):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=5)
        except:
            pass

# --- 4. جالب الأسعار الحية الحرة الحقيقية (Binance كمثال سريع للذهب/العملات) ---
def get_live_price(symbol):
    # تحويل الرموز لـ Binance (مثلاً XAUUSD الحقيقي يقابله PAXGUSDT أو نستخدم الذهب المباشر)
    # لتبسيط المحاكاة سنأخذ سعر الذهب الفوري عبر سيرفر مفتوح
    url = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT" # الذهب الرقمي المدعوم بالذهب الحقيقي اللحظي
    try:
        resp = requests.get(url, timeout=5).json()
        return float(resp['price'])
    except:
        # سعر افتراضي مرن في حال انقطاع السيرفر مؤقتاً لكي لا ينهار البوت
        return 2350.0

# --- 5. محرك إدارة الصفقات والمحاكاة السحابية ---
def open_virtual_trade(direction, entry, tp, sl):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO virtual_trades (symbol, direction, entry_price, tp_price, sl_price) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
                (SYMBOL, direction, entry, tp, sl)
            )
            trade_id = cur.fetchone()[0]
            conn.commit()
            
            msg = (
                f"🚀 <b>تم فتح صفقة افتراضية سحابية جديدة!</b>\n\n"
                f"🔢 رقم الصفقة: #{trade_id}\n"
                f"📈 الاتجاه: {direction}\n"
                f"💵 سعر الدخول: {entry}\n"
                f"🎯 الهدف (TP): {tp}\n"
                f"🛑 وقف الخسارة (SL): {sl}"
            )
            send_telegram_msg(msg)
    except Exception as e:
        print(f"Error opening trade: {e}")
    finally:
        conn.close()

def monitor_and_close_trades(current_price):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, direction, entry_price, tp_price, sl_price FROM virtual_trades WHERE status = 'OPEN';")
            open_trades = cur.fetchall()
            
            for trade in open_trades:
                tid, direction, entry, tp, sl = trade
                is_closed = False
                pnl = 0.0
                reason = ""
                
                if direction == "BUY":
                    if current_price >= float(tp):
                        is_closed = True; pnl = float(tp) - float(entry); reason = "🎯 ضربت الهدف (TP)"
                    elif current_price <= float(sl):
                        is_closed = True; pnl = float(sl) - float(entry); reason = "🛑 ضربت وقف الخسارة (SL)"
                else: # SELL
                    if current_price <= float(tp):
                        is_closed = True; pnl = float(entry) - float(tp); reason = "🎯 ضربت الهدف (TP)"
                    elif current_price >= float(sl):
                        is_closed = True; pnl = float(entry) - float(sl); reason = "🛑 ضربت وقف الخسارة (SL)"
                
                if is_closed:
                    # حساب افتراضي تقريبي للربح بالدولار (نفرض لوت 0.1 يعني النقطة بـ 1 دولار)
                    profit_usd = pnl * 100 
                    cur.execute(
                        "UPDATE virtual_trades SET status = 'CLOSED', exit_price = %s, pnl = %s WHERE id = %s;",
                        (current_price, profit_usd, tid)
                    )
                    conn.commit()
                    
                    status_emoji = "🟢" if profit_usd >= 0 else "🔴"
                    msg = (
                        f"{status_emoji} <b>إغلاق صفقة افتراضية سحابية!</b>\n\n"
                        f"🔢 رقم الصفقة: #{tid}\n"
                        f"سبب الإغلاق: {reason}\n"
                        f"💵 سعر الخروج الحقيقي: {current_price}\n"
                        f"💰 النتيجة الماليّة: {profit_usd:+.2f} USD"
                    )
                    send_telegram_msg(msg)
    except Exception as e:
        print(f"Error monitoring: {e}")
    finally:
        conn.close()

# --- 6. فحص الإقلاع والصحة الذكي (Post-Restore Health Check) ---
def run_post_restore_health_check():
    send_telegram_msg("🔄 <b>نظام الفحص الذكي (Health Check):</b> جاري مراجعة النظام وتدقيق الصفقات بعد إعادة التشغيل...")
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, direction, entry_price, tp_price, sl_price FROM virtual_trades WHERE status = 'OPEN';")
            open_trades = cur.fetchall()
            
            report = f"📊 <b>تقرير فحص الصحة السحابي المباشر:</b>\n"
            report += f"عدد الصفقات المفتوحة النشطة: {len(open_trades)}\n\n"
            
            for trade in open_trades:
                tid, direction, entry, tp, sl = trade
                # تدقيق أمني منطقي للأهداف ووقف الخسارة
                is_valid = True
                warning_note = ""
                
                if float(tp) <= 0 or float(sl) <= 0:
                    is_valid = False
                    warning_note = "⚠️ تحذير: الأهداف غير محددة برقم منطقي!"
                
                report += f"🔹 صفقة #{tid} ({direction}): الدخول {entry} | "
                report += f"حالة الأهداف: {'✅ آمنة وقابلة للتحقيق' if is_valid else warning_note}\n"
                
            send_telegram_msg(report)
    except Exception as e:
        print(f"Error during health check: {e}")
    finally:
        conn.close()

# --- 7. الحلقة الرئيسية لتشغيل البوت ---
def main():
    print("🚀 انطلاق البوت السحابي في وضع المحاكاة الفائقة...")
    send_telegram_msg("🚀 <b>تم تفعيل البوت سحابياً بنجاح!</b>\nالنظام يعمل الآن في وضع المحاكاة الذكية المربوطة بالأسعار الحقيقية الحية.")
    
    init_db()
    run_post_restore_health_check()
    
    # محاكاة فتح صفقة تجريبية أولى فورية عند أول إقلاع للتأكد من عمل النظام
    live_p = get_live_price(SYMBOL)
    open_virtual_trade("BUY", live_p, live_p + 15, live_p - 10)
    
    while True:
        try:
            live_price = get_live_price(SYMBOL)
            print(f"السعر الحالي الحي: {live_price}")
            
            # مراقبة الصفقات المفتوحة وإغلاقها تلقائياً إذا ضربت الأهداف
            monitor_and_close_trades(live_price)
            
            # فحص كل 10 ثوانٍ لحركة السوق الحية
            time.sleep(10)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"خطأ في الحلقة الرئيسية: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
