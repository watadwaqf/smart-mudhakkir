#!/usr/bin/env python3 -I
"""تذكير التحضير العلميّ (الدرس ٢١).
- **الدروس الأسبوعيّة** (صفوف «الجدول الثابت» من نوع «درس» المعلَّمة «يُذكَّر به»): بندٌ في مساء اليوم السابق للدرس
  («بين العشاءين»، تنبيهه بعد المغرب بعشرين دقيقة): «تحضير «الدرس» لغد: <الموضع القادم>».
  والموضع القادم في خاصّيّة «الموضع القادم» للدرس. ويوم الدرس بعد العشاء يُنشأ سؤالٌ واحد: «أين وصلتَ في درس … اليوم؟»
  فإذا أُجيب كتب هذا السكربت الجواب في «الموضع القادم» وجعل السؤال «طُبِّق».
- **المحاضرات لمرّةٍ واحدة** (التزاماتٌ عنوانها يبدأ بـ«محاضرة» ولها استحقاق): «إعداد مادّة محاضرة …» قبلها بثلاثة أيّام
  إلى يومين («بعد العصر»، تنبيهه بعد العصر بنصف ساعة)، و«مراجعة محاضرة … غدًا» قبلها بيوم (مساءً).
بنوده مفاتيحها «تحضير:…»، تحفظها المزامنة ولا يُنقل تعليمها، وتوضع في صفحة نافذتها، وما فات يومه يُحذف إن لم يُعلَّم.
يشغّله النبض (mac_tick.py). السطر الأخير: PREP items=n questions=k applied=m
"""
import importlib.util, json, os, subprocess, tempfile
from datetime import datetime, timedelta, timezone

H = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mc", os.path.join(H, "mac_calendar.py"))
mc = importlib.util.module_from_spec(spec); spec.loader.exec_module(mc)
C = mc.C
STATE = mc.STATE
KW = C.TZ
BASE = C.cfg["apple"]["reminders_list"]
NPAGES = max(1, int(C.cfg["apple"].get("pages", 3) or 1))
PAGE_NAMES = [BASE] + [f"{BASE} {str(i + 1).translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩'))}" for i in range(1, NPAGES)]
RANK = {"بعد العصر": 3, "بين العشاءين": 4}
DAYS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
PAGE_OF = {w: PAGE_NAMES[min(NPAGES - 1, RANK[w] * NPAGES // 6)] for w in RANK}  # صفحة النافذة كما في reminders.js
NEXT = "الموضع القادم"
MARK = "موضع:"  # في «ملاحظة الوكيل» لسؤال الموضع: موضع:<معرّف الدرس>:<التاريخ>


def osa(*args, paged=False):
    r = C.osa("reminders.js", *args, timeout=1500, reminders=paged)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200])
    return r.stdout.strip()


def api(tok, method, path, body):
    r = subprocess.run(["curl", "-sS", "--max-time", "40", "-X", method, "https://api.notion.com/v1/" + path,
                        "-H", "Authorization: Bearer " + tok, "-H", "Notion-Version: 2022-06-28",
                        "-H", "Content-Type: application/json", "--data-binary", "@-"],
                       input=json.dumps(body), capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    if j.get("object") == "error":
        raise RuntimeError(j.get("message"))
    return j


def text(s):
    return {"rich_text": [{"text": {"content": s[:1900]}}]}


def lessons(tok, day):
    out = []
    for p in mc.query_all(tok, mc.DB["fixed"], {"filter": {"property": "النوع", "select": {"equals": "درس"}}}):
        if not mc.prop(p, "يُذكَّر به") or DAYS[day.weekday()] not in (mc.prop(p, "الأيّام") or []):
            continue
        frm, end = mc.prop(p, "يسري من"), mc.prop(p, "ينتهي في")
        if frm and frm.get("start") and frm["start"][:10] > day.isoformat():
            continue
        if end and end.get("start") and end["start"][:10] < day.isoformat():
            continue
        out.append(p)
    return out


def short(name):
    return name.replace("درس ", "", 1).strip()


def main():
    tok = mc.token()
    if not tok:
        print("PREP NO-KEY"); return
    now = datetime.now(KW).replace(tzinfo=None)
    today = now.date()
    tmr = today + timedelta(days=1)
    pr = mc.prayers(today)
    eve = (pr["المغرب"] + timedelta(minutes=20)).isoformat()
    aft = (pr["العصر"] + timedelta(minutes=30)).isoformat()
    want = []  # (القائمة، البند)

    # ١. تحضير دروس الغد
    for p in lessons(tok, tmr):
        name = short(mc.prop(p, "الاسم") or "")
        pos = (mc.prop(p, NEXT) or "").strip()
        title = f"تحضير {name} لغد: {pos}" if pos else f"تحضير {name} لغد (لم يُعرف الموضع بعد)"
        want.append(("بين العشاءين", {"key": f"تحضير:{p['id'].replace('-', '')}:{tmr.isoformat()}", "window": "بين العشاءين",
                                       "title": title, "time": eve}))

    # ٢. المحاضرات لمرّةٍ واحدة
    rows = mc.query_all(tok, mc.DB["commitments"], {"filter": {"and": [
        {"property": "الاستحقاق", "date": {"on_or_after": tmr.isoformat()}},
        {"property": "الاستحقاق", "date": {"on_or_before": (today + timedelta(days=3)).isoformat()}}]}})
    for p in rows:
        t = (mc.prop(p, "العنوان") or "").strip()
        if not t.startswith("محاضرة") or mc.prop(p, "الحال") in ("منجز", "معتذر عنه"):
            continue
        d = datetime.fromisoformat(mc.prop(p, "الاستحقاق")["start"][:10]).date()
        cid = p["id"].replace("-", "")
        label = t.split("(")[0].strip()
        if (d - today).days >= 2:
            want.append(("بعد العصر", {"key": f"تحضير:{cid}:إعداد", "window": "بعد العصر",
                                     "title": f"إعداد مادّة {label} ({DAYS[d.weekday()]})", "time": aft}))
        else:
            want.append(("بين العشاءين", {"key": f"تحضير:{cid}:مراجعة", "window": "بين العشاءين",
                                        "title": f"مراجعة {label} غدًا", "time": eve}))

    # ٣. الكتابة: ما يلزم يُضاف أو يُحدَّث في صفحة نافذته، وما لم يعد لازمًا يُحذف إن لم يُعلَّم
    keys = {it["key"] for _, it in want}
    for win in PAGE_OF:
        items = [it for w, it in want if w == win]
        if items:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
                json.dump({"items": items}, f, ensure_ascii=False)
            osa("upsert", f.name, f"--list={PAGE_OF[win]}"); os.unlink(f.name)
    for x in json.loads(osa("read", paged=True) or "[]"):
        k = x.get("key") or ""
        if k.startswith("تحضير:") and not x.get("completed") and k not in keys:
            osa("remove", k, f"--list={PAGE_NAMES[x.get('page', 1) - 1]}")

    # ٤. سؤال الموضع: يوم الدرس بعد العشاء، مرّةً واحدة
    nq = 0
    if now >= pr["العشاء"]:
        for p in lessons(tok, today):
            fid = p["id"].replace("-", "")
            mark = f"{MARK}{fid}:{today.isoformat()}"
            if mc.query_all(tok, mc.DB["questions"], {"filter": {"property": "ملاحظة الوكيل", "rich_text": {"contains": mark}}}):
                continue
            name = short(mc.prop(p, "الاسم") or "")
            mc.notion(tok, "pages", {"parent": {"database_id": mc.DB["questions"]}, "properties": {
                "السؤال": {"title": [{"text": {"content": f"أين وصلتَ في {name} اليوم؟ (ليُكتب الموضع في تحضير الدرس القادم) (أجب بصوتك)"}}]},
                "الحال": {"select": {"name": "مفتوح"}}, "الأولويّة": {"select": {"name": "عاديّ"}},
                "يُسأل في": {"date": {"start": today.isoformat()}},
                "ملاحظة الوكيل": text(f"{mark} · يطبّقه الماك آليًّا (mac_prep.py): يكتب الجواب في «{NEXT}» للدرس، فلا يطبّقه الوكيل.")}})
            nq += 1

    # ٥. تطبيق أجوبة الموضع
    na = 0
    for q in mc.query_all(tok, mc.DB["questions"], {"filter": {"and": [
            {"property": "ملاحظة الوكيل", "rich_text": {"contains": MARK}},
            {"property": "الحال", "select": {"equals": "أُجيب"}}]}}):
        note = mc.prop(q, "ملاحظة الوكيل") or ""
        fid = note.split(MARK, 1)[1].split(":", 1)[0]
        ans = (mc.prop(q, "الجواب") or "").strip()
        if ans:
            api(tok, "PATCH", f"pages/{fid}", {"properties": {NEXT: text(ans)}})
        api(tok, "PATCH", f"pages/{q['id']}", {"properties": {"الحال": {"select": {"name": "طُبِّق"}}}})
        na += 1
    print(f"PREP items={len(want)} questions={nq} applied={na}")


if __name__ == "__main__":
    main()
