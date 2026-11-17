#!/usr/bin/env python3 -I
"""قارئ بوت «المذكّر» في تيليجرام (على الماك).
  telegram_pull.py              يقرأ الجديد، ويحفظه في طابورٍ محلّيّ، ويُقرّ به لتيليجرام،
                                وينزّل الصوت إلى مجلّد paths.telegram_audio ليفرّغه transcribe.sh.
                                ثمّ يطبع: TG pending=<عدد>، وبعده سطر JSON لكلّ رسالةٍ تنتظر الكتابة في الوارد.
  telegram_pull.py --done <id>  يعلّم رسالةً بأنّها كُتبت في الوارد.
  telegram_pull.py --fetch <file_id> <اسم>   ينزّل ملفًّا صوتيًّا سجّل له وكيل السحابة سطرًا في الوارد.
لا يُقبل إلّا ما أرسله صاحب النظام من حسابه (config.json ← telegram.owner_id، أو state/telegram_owner). وما سواه يُهمَل ولا يُحفظ.
والمفتاح في سلسلة المفاتيح (اسم الخدمة في config.json ← keychain.telegram)، ولا يُطبع.
ويعمل إن كان telegram.enabled في config.json (معطّلٌ افتراضًا).
"""
import importlib.util
import json
import os
import subprocess
import sys
import urllib.parse
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("config", os.path.join(BASE, "config.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
STATE = C.STATE
AUDIO = C.path("telegram_audio")
QUEUE = os.path.join(STATE, "telegram_queue.jsonl")
DONE = os.path.join(STATE, "telegram_done.txt")
OFFSET = os.path.join(STATE, "telegram_offset")


def token():
    t = C.keychain(C.cfg["keychain"]["telegram"]) or ""
    if not t:
        print("TG NO_TOKEN")
        sys.exit(0)
    return t


def api(tok, method, **params):
    # عبر curl لا urllib: curl يثق بسلسلة مفاتيح النظام، وبعض الوسطاء في الشبكات يكسرون تحقّق شهادات بايثون
    q = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    r = subprocess.run(["curl", "-sS", "--max-time", "40", f"https://api.telegram.org/bot{tok}/{method}?{q}"],
                       capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    if not d.get("ok"):
        raise RuntimeError(d.get("description", "تيليجرام رفض الطلب أو تعذّر الاتّصال"))
    return d["result"]


def download(tok, file_id, name):
    """ينزّل الملفّ إلى AUDIO باسم name مع امتداده، ويعيد مساره."""
    f = api(tok, "getFile", file_id=file_id)
    ext = os.path.splitext(f["file_path"])[1] or ".oga"
    dest = os.path.join(AUDIO, name + ext)
    if not os.path.exists(dest):
        r = subprocess.run(["curl", "-sS", "--max-time", "120", "-o", dest,
                            f"https://api.telegram.org/file/bot{tok}/{f['file_path']}"], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("تعذّر تنزيل الملفّ")
    return dest


def readlines(p):
    try:
        return open(p).read().split("\n")
    except FileNotFoundError:
        return []



if len(sys.argv) == 3 and sys.argv[1] == "--done":
    with open(DONE, "a") as f:
        f.write(sys.argv[2] + "\n")
    print("علِّم", sys.argv[2])
    sys.exit(0)

if not C.cfg["telegram"].get("enabled"):
    print("TG OFF")
    sys.exit(0)
os.makedirs(AUDIO, exist_ok=True)

tok = token()

if len(sys.argv) == 4 and sys.argv[1] == "--fetch":
    print(download(tok, sys.argv[2], sys.argv[3]))
    sys.exit(0)

owner = str(C.cfg["telegram"].get("owner_id") or "").strip() or (readlines(os.path.join(STATE, "telegram_owner")) or [""])[0].strip()
if not owner:
    print("TG NO_OWNER | اضبط telegram.owner_id في config.json")
    sys.exit(0)

offset = int((readlines(OFFSET) or ["0"])[0] or 0)
try:
    ups = api(tok, "getUpdates", offset=offset + 1, timeout=0)
except Exception as e:
    print(f"TG FAIL | {e}")
    sys.exit(0)

new, ignored, last = 0, 0, offset
with open(QUEUE, "a") as q:
    for u in ups:
        last = max(last, u["update_id"])
        m = u.get("message")
        if not m or str((m.get("from") or {}).get("id")) != owner or m.get("chat", {}).get("type") != "private":
            ignored += 1   # لا يُحفظ شيءٌ ممّا أرسله غير صاحب النظام
            continue
        kind, fid = "text", None
        for k in ("voice", "audio", "video_note"):
            if m.get(k):
                kind, fid = k, m[k]["file_id"]
        if kind == "text" and not (m.get("text") or m.get("caption")):
            kind = "other"
        fwd = ""
        o = m.get("forward_origin") or {}
        if o:
            who = o.get("sender_user") or {}
            fwd = (o.get("sender_user_name") or " ".join(x for x in (who.get("first_name"), who.get("last_name")) if x)
                   or (o.get("chat") or {}).get("title") or "مجهول")
        rec = {"id": f"tg:{u['update_id']}", "date": datetime.fromtimestamp(m["date"]).strftime("%Y-%m-%d %H:%M"),
               "kind": kind, "text": m.get("text") or m.get("caption") or "", "forwarded_from": fwd}
        if fid:
            try:
                rec["audio"] = download(tok, fid, f"tg_{u['update_id']}")
            except Exception as e:
                rec["audio_error"] = str(e)
        q.write(json.dumps(rec, ensure_ascii=False) + "\n")
        new += 1

if last > offset:
    open(OFFSET, "w").write(str(last))
    try:
        api(tok, "getUpdates", offset=last + 1, timeout=0)   # إقرارٌ لتيليجرام، فلا يراها وكيل السحابة مكرّرة
    except Exception:
        pass

done = set(readlines(DONE))
pending = []
for line in readlines(QUEUE):
    if not line.strip():
        continue
    r = json.loads(line)
    if r["id"] in done:
        continue
    if r.get("audio"):
        txt = os.path.splitext(r["audio"])[0] + ".txt"
        if os.path.exists(txt):
            r["transcript"] = txt
        else:
            r["waiting_transcription"] = True
    pending.append(r)

print(f"TG pending={len(pending)} new={new} ignored={ignored}")
for r in pending:
    print(json.dumps(r, ensure_ascii=False))
