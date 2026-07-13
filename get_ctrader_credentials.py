import os
import sys
import time
import requests
from ctrader_open_api import Auth, Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAGetAccountListByAccessTokenReq,
)
from twisted.internet import reactor

REDIRECT_URI = "https://example.com/callback"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_msg(text):
    if BOT_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})

def get_telegram_code():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    start_time = time.time()
    send_telegram_msg("⏳ بانتظار إرسالك الـ code هنا في المحادثة... (لديك دقيقة واحدة)")
    
    while time.time() - start_time < 60:
        try:
            resp = requests.get(url, timeout=5).json()
            if resp.get("ok") and resp.get("result"):
                last_msg = resp["result"][-1]["message"]
                if str(last_msg["chat"]["id"]) == str(CHAT_ID):
                    text = last_msg["text"].strip()
                    if len(text) > 10 and not text.startswith("/"):
                        return text
        except Exception:
            pass
        time.sleep(3)
    return None

def main():
    client_id = os.environ.get("CTRADER_CLIENT_ID")
    client_secret = os.environ.get("CTRADER_CLIENT_SECRET")

    if not client_id or not client_secret or not BOT_TOKEN:
        print("❌ نقص في متغيرات البيئة الأساسية.")
        sys.exit(1)

    auth = Auth(client_id, client_secret, REDIRECT_URI)
    
    # استخدام صلاحية accounts المتوافقة مع حالة Submitted
    auth_uri = f"https://openapi.ctrader.com/apps/auth?client_id={client_id}&redirect_uri={REDIRECT_URI}&scope=accounts"
    
    welcome_text = (
        f"🔗 <b>خطوة استخراج التوكن السحابي</b>\n\n"
        f"1. افتح هذا الرابط في متصفحك ووافق على الصلاحيات:\n{auth_uri}\n\n"
        f"2. بعد الموافقة، سيحولك الرابط لصفحة بيضاء (example.com)، انسخ الـ code الموجود في عنوان الصفحة وصادق عليه بإرساله كرسالة نصية عادية هنا فوراً!"
    )
    send_telegram_msg(welcome_text)

    auth_code = get_telegram_code()
    if not auth_code:
        send_telegram_msg("❌ انتهت المهلة ولم أستلم الرمز على تيليجرام.")
        sys.exit(1)

    send_telegram_msg("🔄 جاري معالجة الرمز ومبادلته بالتوكن النهائي...")
    token_response = auth.getToken(auth_code)

    if token_response.get("errorCode"):
        send_telegram_msg(f"❌ فشل استخراج التوكن: {token_response.get('description')}")
        sys.exit(1)

    access_token = token_response["accessToken"]
    
    success_msg = (
        f"✅ <b>مبروك! تم استخراج التوكن بنجاح:</b>\n\n"
        f"<code>CTRADER_ACCESS_TOKEN={access_token}</code>\n\n"
        f"قم بنسخ السطر أعلاه وضعه في Railway Variables وافتح البوت!"
    )
    send_telegram_msg(success_msg)
    print("Done successfully via Telegram!")

if __name__ == "__main__":
    main()
