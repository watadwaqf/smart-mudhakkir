#!/usr/bin/env python3 -I
"""قائمة «المذكّر — غدًا» : ما يُستعدّ له الليلة، لا صورةٌ من قائمة الغد.
فيها: مواعيد الغد بساعاتها (الدروس والالتزامات، من تقويم «المذكّر»)، ثمّ الالتزامات التي استحقاقها غدًا.
وليس فيها: السكن والأدوية والمراجعات اليوميّة، فهي تتكرّر كلّ يوم.
- للعرض: بلا تنبيهٍ ولا تاريخ، فلا تتكرّر الإشعارات مع قائمة اليوم.
- تعليم بندٍ «التزام:» فيها إنجازٌ مبكّر: يُكتب «منجز» في Notion.
- يشغّله النبض (mac_tick.py) كلّ عشر دقائق، ولا يكتب في «التذكيرات» إلّا إن تغيّر شيء.
السطر الأخير: TOMORROW items=n changed=yes|no done=k   أو   TOMORROW NO-KEY
"""
import hashlib, importlib.util, json, os, subprocess, sys, tempfile
from datetime import date, datetime, timedelta, timezone

H = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mc", os.path.join(H, "mac_calendar.py"))
mc = importlib.util.module_from_spec(spec); spec.loader.exec_module(mc)
STATE = mc.STATE
C = mc.C
LIST = C.cfg["apple"]["reminders_list"] + " — غدًا"
KW = C.TZ
SKIP_EMOJI = ("🏠", "💊", "📌")
HASH = os.path.join(STATE, "tomorrow_hash")
SEEN = os.path.join(STATE, "tomorrow_done.json")
AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def osa(*args):
    r = C.osa("reminders.js", *args, f"--list={LIST}", timeout=1500, reminders=False)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200])
    return r.stdout.strip()


def patch(tok, page, body):
    r = subprocess.run(["curl", "-sS", "--max-time", "40", "-X", "PATCH", f"https://api.notion.com/v1/pages/{page}",
                        "-H", "Authorization: Bearer " + tok, "-H", "Notion-Version: 2022-06-28",
                        "-H", "Content-Type: application/json", "--data-binary", "@-"],
                       input=json.dumps(body), capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    if j.get("object") == "error":
        raise RuntimeError(j.get("message"))


def build(tok, tmr):
    items, seen = [], set()
    ev = json.load(open(os.path.join(STATE, "calendar_events.json"), encoding="utf-8")).get("events", [])
    for e in sorted(ev, key=lambda e: e["start"]):
        if e["start"][:10] != tmr.isoformat() or e["title"].startswith(SKIP_EMOJI):
            continue
        k = e["key"] if e["key"].startswith("التزام:") else "غد:" + e["key"]
        when = "" if e.get("allday") else e["start"][11:16].translate(AR) + " "
        items.append({"key": k, "title": when + e["title"], "nodate": True}); seen.add(k)
    rows = mc.query_all(tok, mc.DB["commitments"], {"filter": {"property": "الاستحقاق", "date": {"equals": tmr.isoformat()}}})
    for p in rows:
        if mc.prop(p, "الحال") in ("منجز", "معتذر عنه"):
            continue
        k = "التزام:" + p["id"].replace("-", "")
        if k in seen:
            continue
        mark = "❗ " if mc.prop(p, "الأولوية") == "عاجل" else ""
        items.append({"key": k, "title": mark + (mc.prop(p, "العنوان") or ""), "nodate": True}); seen.add(k)
    return items


def harvest(tok):
    """ما علّمه صاحب النظام في قائمة الغد: «التزام:» يصير منجزًا في Notion، مرّةً واحدة."""
    done = json.load(open(SEEN, encoding="utf-8")) if os.path.exists(SEEN) else []
    n = 0
    for x in json.loads(osa("read") or "[]"):
        k = x.get("key") or ""
        if not x.get("completed") or not k.startswith("التزام:") or k in done:
            continue
        patch(tok, k.split(":", 1)[1], {"properties": {"الحال": {"status": {"name": "منجز"}},
                                                         "أُنجز في": {"date": {"start": date.today().isoformat()}}}})
        done.append(k); n += 1
    json.dump(done[-300:], open(SEEN, "w", encoding="utf-8"), ensure_ascii=False)
    return n


def main():
    tok = mc.token()
    if not tok:
        print("TOMORROW NO-KEY"); return
    tmr = datetime.now(KW).date() + timedelta(days=1)
    items = build(tok, tmr)
    h = hashlib.sha1(json.dumps([tmr.isoformat(), items], ensure_ascii=False).encode()).hexdigest()
    old = open(HASH).read().strip() if os.path.exists(HASH) else ""
    changed = h != old.split("|", 1)[0]
    if changed:
        old_keys = old.split("|", 1)[1] if "|" in old else ""
        new_keys = ",".join(i["key"] for i in items)
        if old_keys != new_keys:
            osa("prune", "", "-")  # تغيّر الترتيب أو البنود: تُعاد كلّها بترتيب الوقت (قائمةٌ قصيرة بلا تنبيه)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"items": items}, f, ensure_ascii=False)
        osa("sync", f.name); os.unlink(f.name)
        open(HASH, "w").write(h + "|" + new_keys)
    n = harvest(tok)
    print(f"TOMORROW items={len(items)} changed={'yes' if changed else 'no'} done={n}")


if __name__ == "__main__":
    main()
