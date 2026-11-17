#!/usr/bin/env python3 -I
"""يكشف التفريغات العالقة: عنصرٌ في «الوارد» نصّه «تسجيل صوتي ينتظر التفريغ: <ملف>» وحاله «جديد»،
ونصّ ملفّه موجودٌ على الماك (<ملف>.txt بجانب التسجيل في iCloud). هذا يحدث إذا فُرِّغ التسجيل في جولةٍ تعطّلت
قبل أن تنقل النصّ، فلا يطبعه transcribe.sh بعدها NEW. يطبع سطرًا لكلّ عالق:
  STUCK <معرّف عنصر الوارد> <اسم الملف> <مسار النصّ>
ثمّ سطرًا أخيرًا: STUCK-COUNT <عدد>   (قراءةٌ فقط؛ لا يكتب في Notion)
"""
import importlib.util, os, re

H = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mc", os.path.join(H, "mac_calendar.py"))
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)
REC = mc.C.path("recordings")

tok = mc.token()
if not tok:
    print("STUCK-COUNT NO-KEY")
    raise SystemExit(3)
rows = mc.query_all(tok, mc.DB["inbox"], {"filter": {"and": [
    {"property": "الحال", "select": {"equals": "جديد"}},
    {"property": "النص", "title": {"starts_with": "تسجيل صوتي ينتظر التفريغ"}}]}})
n = 0
for r in rows:
    text = (mc.prop(r, "النص") or "").replace("\\", "")
    m = re.search(r"ينتظر التفريغ:\s*(\S+?\.m4a)", text)
    if not m:
        continue
    txt = os.path.join(REC, m.group(1)[:-4] + ".txt")
    if os.path.exists(txt) and os.path.getsize(txt) > 0:
        print("STUCK", r["id"], m.group(1), txt)
        n += 1
print("STUCK-COUNT", n)
