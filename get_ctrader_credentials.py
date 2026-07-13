"""
get_ctrader_credentials.py
============================
سكربت تفاعلي لمرة واحدة — يُنجز رحلة OAuth الكاملة تلقائيًا:
  1. يبني رابط التفويض ويطبعه لك لفتحه بالمتصفح
  2. تلصق رمز "code" الذي يصلك في رابط التحويل بعد الموافقة
     ⚠️ هذا الرمز صالح لمدة دقيقة واحدة فقط (مؤكَّد من توثيق cTrader
     الرسمي) — لهذا هذا السكربت يُنفّذ كل الخطوات التالية فورًا وتلقائيًا
     بدل أن تبنيها يدويًا خطوة بخطوة
  3. يُبادل الرمز بـ Access Token و Refresh Token تلقائيًا
  4. يتصل فعليًا بالخادم (Demo) ويجلب ctidTraderAccountId الحقيقي
     المرتبط بحسابك تلقائيًا (لا حاجة لتخمينه أو افتراضه)
  5. يطبع كل القيم الأربع جاهزة للنسخ المباشر إلى Railway Variables

الاستخدام:
    export CTRADER_CLIENT_ID=xxxxx
    export CTRADER_CLIENT_SECRET=xxxxx
    python3 get_ctrader_credentials.py
"""

import os
import sys

from ctrader_open_api import Auth, Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAGetAccountListByAccessTokenReq,
)
from twisted.internet import reactor

REDIRECT_URI = os.environ.get("CTRADER_REDIRECT_URI", "https://example.com/callback")


def main():
    client_id = os.environ.get("CTRADER_CLIENT_ID")
    client_secret = os.environ.get("CTRADER_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("❌ يجب ضبط CTRADER_CLIENT_ID و CTRADER_CLIENT_SECRET كمتغيرات بيئة أولاً.")
        sys.exit(1)

    auth = Auth(client_id, client_secret, REDIRECT_URI)

    print("=" * 70)
    print("الخطوة 1: افتح هذا الرابط في متصفحك ووافق على الوصول:")
    print(auth.getAuthUri())
    print("=" * 70)
    print("بعد الموافقة، سيُعيد المتصفح توجيهك لرابط يحتوي على '?code=...'")
    print("انسخ فقط قيمة code من ذلك الرابط (وليس الرابط كاملاً).")
    print("⚠️ الرمز صالح لدقيقة واحدة فقط — الصقه هنا فورًا:")
    print("=" * 70)

    auth_code = input("code = ").strip()
    if not auth_code:
        print("❌ لم يُدخَل أي رمز.")
        sys.exit(1)

    print("\nالخطوة 2: مبادلة الرمز بـ Access/Refresh Token ...")
    token_response = auth.getToken(auth_code)

    if token_response.get("errorCode"):
        print(f"❌ فشل المبادلة: {token_response.get('description')}")
        sys.exit(1)

    access_token = token_response["accessToken"]
    refresh_token = token_response["refreshToken"]
    expires_in_days = token_response.get("expiresIn", 0) / 86400

    print(f"✅ تم الحصول على Access Token (صالح تقريبًا {expires_in_days:.0f} يومًا)")

    print("\nالخطوة 3: الاتصال بالخادم لجلب رقم الحساب (ctidTraderAccountId) ...")

    use_live = os.environ.get("CTRADER_USE_LIVE", "false").lower() == "true"
    host = EndPoints.PROTOBUF_LIVE_HOST if use_live else EndPoints.PROTOBUF_DEMO_HOST
    client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)

    found_account_ids = []

    def on_connected(c):
        request = ProtoOAApplicationAuthReq()
        request.clientId = client_id
        request.clientSecret = client_secret
        c.send(request)

    def on_message(c, message):
        payload = Protobuf.extract(message)
        type_name = type(payload).__name__

        if type_name == "ProtoOAApplicationAuthRes":
            request = ProtoOAGetAccountListByAccessTokenReq()
            request.accessToken = access_token
            c.send(request)

        elif type_name == "ProtoOAGetAccountListByAccessTokenRes":
            for account in payload.ctidTraderAccount:
                found_account_ids.append({
                    "ctidTraderAccountId": account.ctidTraderAccountId,
                    "traderLogin": account.traderLogin,
                    "isLive": account.isLive,
                })
            reactor.callLater(0.5, reactor.stop)

        elif type_name == "ProtoOAErrorRes":
            print(f"❌ خطأ من الخادم: {payload.description}")
            reactor.callLater(0.5, reactor.stop)

    client.setConnectedCallback(on_connected)
    client.setMessageReceivedCallback(on_message)
    client.startService()

    reactor.callLater(15, reactor.stop)  # مهلة أمان لو تعطّل الاتصال
    reactor.run()

    print("\n" + "=" * 70)
    if found_account_ids:
        print("✅ اكتملت العملية! الحسابات المرتبطة بهذا التوكن:\n")
        for acc in found_account_ids:
            kind = "LIVE" if acc["isLive"] else "DEMO"
            print(f"  - Login: {acc['traderLogin']} | النوع: {kind} | "
                  f"ctidTraderAccountId: {acc['ctidTraderAccountId']}")

        print("\nانسخ هذه القيم إلى Railway Variables:\n")
        print(f"CTRADER_ACCESS_TOKEN={access_token}")
        print(f"CTRADER_REFRESH_TOKEN={refresh_token}")
        if len(found_account_ids) == 1:
            print(f"CTRADER_ACCOUNT_ID={found_account_ids[0]['ctidTraderAccountId']}")
        else:
            print("# وُجد أكثر من حساب — طابق Login أعلاه مع رقم حسابك الظاهر في")
            print("# Pepperstone Client Area (مثلاً 5310813)، ثم استخدم ctidTraderAccountId المقابل له")
            print("CTRADER_ACCOUNT_ID=<اختر الرقم المطابق من القائمة أعلاه>")
    else:
        print("⚠️ لم يتم العثور على أي حساب. تحقق من صحة Client ID/Secret وأن")
        print("   التطبيق مُفعَّل (وليس Submitted) على openapi.ctrader.com/apps")
        print(f"\nمع ذلك، احتفظ بهذين القيمتين فهما صالحتان:")
        print(f"CTRADER_ACCESS_TOKEN={access_token}")
        print(f"CTRADER_REFRESH_TOKEN={refresh_token}")
    print("=" * 70)


if __name__ == "__main__":
    main()
