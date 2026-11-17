#!/usr/bin/env python3 -I
"""يرسل إقرار الاستلام إلى صاحب النظام وحده في تيليجرام: إخبارٌ بما فُهم من كلامه وما صار إليه.
الإقرار إخبارٌ فقط لا يطلب شيئًا؛ وما يحتاج قراره سؤالٌ في «الأسئلة».
خيارٌ معطّلٌ افتراضًا: يعمل إن كان telegram.enabled وtelegram.ack كلاهما true في config.json.
لا يرسل إلّا إلى telegram.owner_id (أو state/telegram_owner)، ولا يقبل غيره.
الاستعمال: telegram_ack.py <ملفّ نصّ الإقرار>
السطر: ACK ok | ACK OFF | ACK SKIP | ACK NO_TOKEN | ACK NO_OWNER | ACK FAIL <سبب>
"""
import importlib.util, os, subprocess, sys

H = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("config", os.path.join(H, "config.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
STATE = C.STATE


def main():
    tg = C.cfg["telegram"]
    if not (tg.get("enabled") and tg.get("ack")):
        print("ACK OFF  (إقرار الاستلام معطّل في الإعدادات: telegram.ack)"); return 0
    if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
        print("ACK SKIP"); return 0
    txt = open(sys.argv[1], encoding="utf-8").read().strip()
    if not txt:
        print("ACK SKIP"); return 0
    tok = C.keychain(C.cfg["keychain"]["telegram"])
    if not tok:
        print("ACK NO_TOKEN"); return 0
    owner = str(tg.get("owner_id") or "").strip()
    op = os.path.join(STATE, "telegram_owner")
    if not owner and os.path.exists(op):
        owner = open(op).read().strip()
    if not owner:
        print("ACK NO_OWNER"); return 0
    r = subprocess.run(["curl", "-sS", "--max-time", "30", "-X", "POST", f"https://api.telegram.org/bot{tok}/sendMessage",
                        "--data-urlencode", f"chat_id={owner}", "--data-urlencode", "text=" + txt[:3900]],
                       capture_output=True, text=True)
    print("ACK ok" if '"ok":true' in r.stdout else "ACK FAIL " + (r.stdout or r.stderr)[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())
