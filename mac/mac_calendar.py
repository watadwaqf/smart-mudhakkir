#!/usr/bin/env python3 -I
"""يملأ عرض «المذكّر» في تطبيقَي Apple من Notion مباشرةً، بلا ذكاءٍ اصطناعيّ:
١. تقويم «المذكّر»: السكن في كلّ يوم (إن فُعِّل خيار households)، والمواعيد، والدروس الثابتة — لليوم والأيّام الستّة بعده.
٢. بند «أسئلة اليوم» في قائمة «المذكّر» بالتذكيرات، وتنبيهه بعد الصلاة التالية (يُحدَّث في كلّ جولة)، ويُزال إن لم يبقَ سؤال.
المفتاح: تكامل Notion في سلسلة المفاتيح (اسم الخدمة في config.json ← keychain.notion).
الاستعمال: mac_calendar.py [--dry]   ← يطبع سطرًا: CAL … | Q …   (--dry يطبع ما سيُكتب ولا يكتب)
وهذا الملفّ مكتبةٌ أيضًا: تستورده السكربتات الأخرى لـ token وnotion وquery_all وprop.
"""
import importlib.util, json, os, re, subprocess, sys
from datetime import date, datetime, timedelta
from urllib.parse import quote

HOME = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("config", os.path.join(HOME, "config.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

STATE = C.STATE
DRY = "--dry" in sys.argv


class _DB(dict):
    """DB["inbox"] … يُقرأ من config.json عند الحاجة، فيعطي خطأً واضحًا إن لم يُضبط."""
    def __missing__(self, k):
        return C.db(k)


DB = _DB()
DAYS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]  # بترتيب weekday() في بايثون
POS = {"بعد الفجر": ("الفجر", 20), "الضحى": ("الظهر", -150), "بعد الظهر": ("الظهر", 20),
       "بعد العصر": ("العصر", 20), "بين العشاءين": ("المغرب", 10), "بعد العشاء": ("العشاء", 20)}
ADHAN = ["الفجر", "الظهر", "العصر", "المغرب", "العشاء"]
Q_LINK = "shortcuts://run-shortcut?name=" + quote(C.cfg["shortcuts"]["questions_shortcut_name"])


def token():
    return C.token()


def notion(tok, path, body=None):
    # عبر curl لا urllib: curl يثق بسلسلة مفاتيح النظام، وبعض الوسطاء في الشبكات يكسرون تحقّق شهادات بايثون
    cmd = ["curl", "-sS", "--max-time", "40", "https://api.notion.com/v1/" + path,
           "-H", "Authorization: Bearer " + tok, "-H", "Notion-Version: 2022-06-28", "-H", "Content-Type: application/json"]
    if body is not None:
        cmd += ["-X", "POST", "--data-binary", "@-"]
    r = subprocess.run(cmd, input=json.dumps(body) if body is not None else None, capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    if j.get("object") == "error":
        raise RuntimeError(j.get("message"))
    return j


def query_all(tok, db, body):
    rows, cur = [], None
    for _ in range(10):
        b = dict(body, page_size=100)
        if cur:
            b["start_cursor"] = cur
        j = notion(tok, f"databases/{db}/query", b)
        rows += j.get("results", [])
        if not j.get("has_more"):
            break
        cur = j.get("next_cursor")
    return rows


def prop(p, name):
    x = p["properties"].get(name)
    if not x:
        return None
    t = x["type"]
    if t in ("title", "rich_text"):
        return "".join(s["plain_text"] for s in x[t])
    if t in ("select", "status"):
        return x[t] and x[t]["name"]
    if t == "multi_select":
        return [o["name"] for o in x[t]]
    if t in ("date", "checkbox", "number"):
        return x[t]
    return None


def prayers(d):
    out = subprocess.run([sys.executable, "-I", os.path.join(HOME, "prayer_times.py"), d.isoformat()],
                         capture_output=True, text=True).stdout
    return {k: datetime.combine(d, datetime.strptime(v, "%H:%M").time()) for k, v in json.loads(out).items()}


def residence(d):
    """السكن في يومٍ (خيار households، معطّلٌ افتراضًا). لمن له بيتان أو أكثر يتناوب بينها بالأيّام:
    by_day: {"السبت": "البيت أ", …}، وalternating: [{"day": "الجمعة", "anchor": "YYYY-MM-DD", "even": "…", "odd": "…"}]
    لليوم الذي يتبادل كلّ أسبوع: في الأسابيع الزوجيّة البعد عن anchor يُعرض even، وفي الفرديّة odd."""
    h = C.cfg["households"]
    if not h.get("enabled"):
        return None
    name = DAYS[d.weekday()]
    for alt in h.get("alternating") or []:
        if alt.get("day") == name and alt.get("anchor"):
            weeks = round((d - date.fromisoformat(alt["anchor"])).days / 7)
            return alt.get("even") if weeks % 2 == 0 else alt.get("odd")
    return (h.get("by_day") or {}).get(name)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def short(s):
    return re.sub(r"^(درس)\s+", "", s or "").replace("«", "").replace("»", "").strip()


def build_events(tok, days):
    ev = []
    first, last = days[0], days[-1]
    # ١. السكن: حدثُ يومٍ كامل (إن فُعِّل)
    for d in days:
        home = residence(d)
        if home:
            ev.append({"key": f"سكن:{d}", "title": "🏠 " + home, "allday": True,
                       "start": iso(datetime.combine(d, datetime.min.time())), "end": iso(datetime.combine(d + timedelta(days=1), datetime.min.time())),
                       "notes": "السكن في هذا اليوم (من إعداد households)."})
    pr = {d: prayers(d) for d in days}
    # ٢. الجدول الثابت: ما «يُذكَّر به» من الدروس ونحوها (لا البيت ولا الإمامة)
    for p in query_all(tok, DB["fixed"], {}):
        ty, name = prop(p, "النوع"), prop(p, "الاسم")
        if ty in ("أسرة", "إمامة") or prop(p, "يُذكَّر به") is not True:
            continue
        dd = prop(p, "الأيّام") or []
        clock, pos = (prop(p, "الساعة") or "").strip(), prop(p, "بالنسبة إلى الصلاة")
        dur = prop(p, "المدّة بالدقائق") or 60
        vf, vt = prop(p, "يسري من"), prop(p, "ينتهي في")
        for d in days:
            if not ("يوميًّا" in dd or DAYS[d.weekday()] in dd):
                continue
            if vf and vf.get("start") and d.isoformat() < vf["start"][:10]:
                continue
            if vt and vt.get("start") and d.isoformat() > vt["start"][:10]:
                continue
            if re.fullmatch(r"\d\d:\d\d", clock):
                s = datetime.combine(d, datetime.strptime(clock, "%H:%M").time())
            elif pos in POS:
                s = pr[d][POS[pos][0]] + timedelta(minutes=POS[pos][1])
            else:
                s = None
            e = {"key": f"ثابت:{p['id'].replace('-', '')}:{d}", "title": icon(ty, name) + " " + short(name), "notes": f"من «الجدول الثابت»{' · ' + pos if pos and not re.fullmatch(r'\d\d:\d\d', clock) else ''}"}
            if s:
                e.update(start=iso(s), end=iso(s + timedelta(minutes=dur)), allday=False)
            else:
                e.update(start=iso(datetime.combine(d, datetime.min.time())), end=iso(datetime.combine(d + timedelta(days=1), datetime.min.time())), allday=True)
            ev.append(e)
    # ٣. المواعيد من الالتزامات
    rows = query_all(tok, DB["commitments"], {"filter": {"and": [
        {"property": "الحال", "status": {"does_not_equal": "منجز"}},
        {"property": "الحال", "status": {"does_not_equal": "معتذر عنه"}},
        {"property": "النوع", "select": {"equals": "موعد"}}]}})
    for p in rows:
        due = prop(p, "الاستحقاق") or prop(p, "يبدأ التذكير")
        if not due or not due.get("start"):
            continue
        ds = due["start"]
        d = date.fromisoformat(ds[:10])
        if not (first <= d <= last):
            continue
        title, role = prop(p, "العنوان"), prop(p, "الدور")
        notes = " · ".join(x for x in [prop(p, "لمن"), prop(p, "لماذا")] if x)
        e = {"key": "التزام:" + p["id"].replace("-", ""), "title": title + (f" · {role}" if role else ""), "notes": notes}
        if len(ds) > 10:
            s = datetime.fromisoformat(ds).astimezone().replace(tzinfo=None)
            end = due.get("end")
            en = datetime.fromisoformat(end).astimezone().replace(tzinfo=None) if end and len(end) > 10 else s + timedelta(hours=1)
            e.update(start=iso(s), end=iso(en), allday=False)
        else:
            win = prop(p, "الوقت") or []
            if win:
                e["title"] = f"بعد {win[0]}: " + e["title"]
            e.update(start=iso(datetime.combine(d, datetime.min.time())), end=iso(datetime.combine(d + timedelta(days=1), datetime.min.time())), allday=True)
        ev.append(e)
    return ev


PENDING_ANSWERS = 0


def icon(ty, name):
    """أيقونة الحدث بنوعه، والصحّيّ بكلمات health_keywords (كانت 📖 للجميع، فظهرت الأدوية بأيقونة الدروس)."""
    if any(m in (name or "") for m in C.cfg["health_keywords"]):
        return "💊"
    return {"درس": "📖", "محاضرة": "🎓", "ساعة مكتبيّة": "🏫", "حلقة": "📿", "اجتماع دوريّ": "👥"}.get(ty, "📌")


def open_questions(tok):
    qs = query_all(tok, DB["questions"], {
        "filter": {"property": "الحال", "select": {"equals": "مفتوح"}},  # كلّ المفتوح، بلا مواعيد
        "sorts": [{"property": "الأولويّة", "direction": "ascending"}, {"timestamp": "created_time", "direction": "ascending"}]})
    pending = set()
    for r in query_all(tok, DB["inbox"], {"filter": {"and": [{"property": "الحال", "select": {"equals": "جديد"}},
                                                               {"property": "المصدر", "select": {"equals": "أسئلة المذكّر"}}]}}):
        m = re.search(r"السؤال ([0-9a-f-]{32,36})", prop(r, "ملاحظة الوكيل") or "", re.I)
        if m:
            pending.add(m.group(1).replace("-", ""))
    global PENDING_ANSWERS
    PENDING_ANSWERS = len(pending)
    return [q for q in qs if q["id"].replace("-", "") not in pending]


def count_word(n):
    if n == 1:
        return "سؤالٌ واحد"
    if n == 2:
        return "سؤالان"
    return f"{n} أسئلة" if 3 <= n % 100 <= 10 else f"{n} سؤالًا"


def osa(script, *args):
    r = C.osa(script, *args)
    return (r.stdout or r.stderr).strip()


def main():
    tok = token()
    if not tok:
        print(f"NO-KEY: احفظ مفتاح Notion في سلسلة المفاتيح بالخدمة {C.cfg['keychain']['notion']}")
        return 3
    today = date.today()
    days = [today + timedelta(days=i) for i in range(7)]
    events = build_events(tok, days)
    qs = open_questions(tok)
    now = datetime.now()
    after = C.cfg["questions"]["after_prayer_minutes"]
    # بعد الصلاة التالية (الأذان + after دقيقة)، ولو كانت فجر الغد: التنبيه بعد الصلاة لا عند الأذان
    upcoming = [t + timedelta(minutes=after) for d in (today, today + timedelta(days=1))
                for k, t in prayers(d).items() if k in ADHAN and t + timedelta(minutes=after) > now]
    nxt = min(upcoming) if upcoming else None
    if DRY:
        for e in sorted(events, key=lambda e: e["start"]):
            print(e["start"][:16].replace("T", " "), "|", e["title"], "| يوم كامل" if e["allday"] else "")
        print("أسئلة:", len(qs), "| الأذان التالي:", nxt)
        return 0
    path = os.path.join(STATE, "calendar_events.json")
    json.dump({"from": days[0].isoformat(), "to": days[-1].isoformat(), "events": events}, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    cal = osa("calendar.js", "sync", path, C.cfg["apple"]["calendar_name"])
    # بند «أسئلة اليوم»: واحدٌ في القائمة، وتنبيهه بعد الصلاة التالية، أو بعد دقيقة لسؤالٍ جديد
    key = f"أسئلة:{today}"
    if qs:
        first = prop(qs[0], "السؤال")
        item = {"key": key, "window": "سؤال", "title": f"أسئلة اليوم: {count_word(len(qs))}", "role": "",
                "notes": f"أوّلها: {first}\nللإجابة افتح اختصار «{C.cfg['shortcuts']['questions_shortcut_name']}»:\n{Q_LINK}\nوعلِّم هذا البند إذا اكتفيتَ اليوم."}
        # سؤالٌ جديد نشأ في آخر fresh دقيقة (من تسجيلٍ للتوّ): ينبّه بعد دقيقة، لا بعد الصلاة، ليجيب فورًا
        fresh_min = C.cfg["questions"]["fresh_minutes"]
        apath = os.path.join(STATE, "questions_alerted.json")
        alerted = set(json.load(open(apath))) if os.path.exists(apath) else set()
        fresh = [q for q in qs if q["id"] not in alerted and
                 datetime.fromisoformat(q["created_time"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None) > now - timedelta(minutes=fresh_min)]
        when = now + timedelta(minutes=1) if fresh else nxt
        if fresh:
            item["notes"] = f"سؤالٌ جديد: {prop(fresh[-1], 'السؤال')}\n" + item["notes"]
        json.dump(sorted(alerted | {q["id"] for q in qs}), open(apath, "w"))
        if when:
            item["time"] = when.strftime("%Y-%m-%dT%H:%M:00") + C.tz_suffix()
        qp = os.path.join(STATE, "questions_item.json")
        json.dump({"items": [item]}, open(qp, "w", encoding="utf-8"), ensure_ascii=False)
        qres = osa("reminders.js", "upsert", qp)
    else:
        qres = osa("reminders.js", "remove", key)
    osa("reminders.js", "prune", "أسئلة:", key)  # بنود الأسئلة للأيّام الماضية
    print(f"CAL {cal} | Q {len(qs)} {qres}")
    print(f"ANSWERS {PENDING_ANSWERS}")  # أجوبةٌ في الوارد لم تُطبَّق بعد: يفرزها وكيل الماك فورًا
    return 0 if not cal.startswith("NO-CALENDAR") else 4


if __name__ == "__main__":
    sys.exit(main())
