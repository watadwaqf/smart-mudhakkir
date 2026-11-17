#!/usr/bin/env python3 -I
"""يرصد أوقات الإنجاز الفعليّة ليتعلّم الوكيل نوافذ صاحب النظام الحقيقيّة.
- كلّ جولة: يقرأ قائمة «المذكّر» في التذكيرات، ويحفظ كلّ بندٍ عُلِّم (المفتاح، والنافذة، ووقت الإنجاز)
  في state/completions.jsonl مرّةً واحدة.
- يوم السبت (بعد ٧ صباحًا، مرّةً في الأسبوع): يكتب في «الوارد» عنصرًا «ملخّص أوقات الإنجاز» للأيّام السبعة الماضية:
  لكلّ نافذة كم بندًا أُنجز، وفي أيّ وقتٍ من اليوم أُنجز فعلًا (بأوقات الصلاة في مدينته، من إعداد location). فيقرؤه الفرز إشارةَ تعلّم.
السطر الأخير: LEARN new=… [weekly=sent|skip]   أو LEARN NO-KEY
الاستعمال: mac_learn.py [--dry] [--weekly]   (‎--weekly يفرض الملخّص الآن)
"""
import importlib.util, json, os, subprocess, sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

H = os.path.dirname(os.path.abspath(__file__))
DRY = "--dry" in sys.argv
WINDOWS = ("بعد الفجر", "بعد الظهر", "بعد العصر", "بعد العشاء", "بين العشاءين", "عاجل")
spec = importlib.util.spec_from_file_location("mc", os.path.join(H, "mac_calendar.py"))
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)
C = mc.C
STATE = C.STATE
LOG = os.path.join(STATE, "completions.jsonl")
SENT = os.path.join(STATE, "learn_weekly_sent")


AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def ar(x):
    return str(x).translate(AR)


def prayers(d):
    r = subprocess.run([sys.executable, "-I", os.path.join(H, "prayer_times.py"), d.isoformat()],
                       capture_output=True, text=True)
    return json.loads(r.stdout)


def real_window(dt):
    """في أيّ نافذةٍ وقع الإنجاز فعلًا، بأوقات صلاة ذلك اليوم."""
    p = prayers(dt.date())
    hm = dt.strftime("%H:%M")
    if hm < p["الفجر"]:
        return "آخر الليل"
    if hm < p["الظهر"]:
        return "بعد الفجر" if hm < p["الشروق"] or hm < "09:00" else "الضحى"
    if hm < p["العصر"]:
        return "بعد الظهر"
    if hm < p["المغرب"]:
        return "بعد العصر"
    if hm < p["العشاء"]:
        return "بين العشاءين"
    return "بعد العشاء"


def read_list():
    r = C.osa("reminders.js", "read", timeout=120)
    return json.loads(r.stdout or "[]")


def main():
    seen = set()
    rows = []
    if os.path.exists(LOG):
        for l in open(LOG, encoding="utf-8"):
            try:
                x = json.loads(l)
                rows.append(x)
                seen.add((x["key"] or x["title"], x["done_at"][:10]))
            except Exception:
                pass
    new = 0
    out = []
    for it in read_list():
        if not it.get("completed") or not it.get("completionDate"):
            continue
        title = it.get("title") or ""
        EMO = {"🌅": "بعد الفجر", "☀️": "بعد الظهر", "🌇": "بعد العصر", "🌙": "بعد العشاء", "🕌": "بين العشاءين", "❗": "عاجل"}
        win = next((w for w in WINDOWS if title.startswith(w)), "") or next((v for k, v in EMO.items() if title.startswith(k)), "")
        done = datetime.fromisoformat(it["completionDate"].replace("Z", "+00:00")).astimezone()
        ident = (it.get("key") or title, done.date().isoformat())
        if ident in seen or done.date() < date.today() - timedelta(days=8):
            continue
        rec = {"key": it.get("key"), "title": title, "window": win, "done_at": done.isoformat(timespec="minutes"),
               "real": real_window(done)}
        out.append(rec); seen.add(ident); new += 1
    if out and not DRY:
        with open(LOG, "a", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    rows += out

    # الملخّص الأسبوعيّ: السبت بعد السابعة، مرّةً في الأسبوع
    today = date.today()
    week = today.isocalendar()[:2]
    last = open(SENT).read().strip() if os.path.exists(SENT) else ""
    force = "--weekly" in sys.argv
    weekly = "skip"
    if force or (today.weekday() == 5 and datetime.now().hour >= 7 and last != str(week)):
        since = today - timedelta(days=7)
        recent = [r for r in rows if r["done_at"][:10] >= since.isoformat() and r.get("window") and r["window"] != "عاجل"]
        by = defaultdict(Counter)
        for r in recent:
            by[r["window"]][r["real"]] += 1
        if recent:
            parts = []
            for w in ("بعد الفجر", "بعد الظهر", "بعد العصر", "بين العشاءين", "بعد العشاء"):
                if by[w]:
                    n = sum(by[w].values())
                    dist = "، ".join(f"{k} {ar(v)}" for k, v in by[w].most_common())
                    parts.append(f"«{w}» (عدد البنود {ar(n)}) أُنجزت فعلًا: {dist}")
            text = f"ملخّص أوقات الإنجاز ({ar(since.isoformat())} – {ar(today.isoformat())}): " + "؛ ".join(parts) + "."
            tok = mc.token()
            if not tok:
                print("LEARN NO-KEY"); return 3
            if not DRY:
                mc.notion(tok, "pages", {"parent": {"database_id": mc.DB["inbox"]}, "properties": {
                    "النص": {"title": [{"text": {"content": text[:1900]}}]},
                    "المصدر": {"select": {"name": "يدوي"}},
                    "الحال": {"select": {"name": "جديد"}},
                    "ملاحظة الوكيل": {"rich_text": [{"text": {"content": "إشارة تعلّم كتبها mac_learn.py من علامات قائمة «" + C.cfg["apple"]["reminders_list"] + "». ليست طلب تذكير: تُقرأ بحسب قسم «التعلّم» في الدستور، فيُحدَّث «أوقات الإنجاز الفعليّة» في «ما أعرفه عنك»."}}]}}})
                open(SENT, "w").write(str(week))
            weekly = "sent"
            print(text)
        else:
            weekly = "empty"
    print(f"LEARN new={new} weekly={weekly}" + (" (dry)" if DRY else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
