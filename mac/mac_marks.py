#!/usr/bin/env python3 -I
"""ينقل علامات قائمة «المذكّر» إلى Notion بمفتاح الماك، بلا ذكاءٍ اصطناعيّ ولا موصل.
- «التزام:<معرّف>» معلَّمٌ اليوم ← «الحال» = منجز، و«أُنجز في» = اليوم.
- «قراءة:…» و«سؤال:…» و«أسئلة:…» وبنود البادئات الخارجيّة (external_prefixes) معلَّمةٌ اليوم ← لا شيء في Notion، تُسجَّل فقط.
- البند الذي أضافه صاحب النظام بيده (بلا مفتاح، غير معلَّم) ← عنصرٌ في «الوارد» (المصدر يدوي).
- «حفظ:<معرّف>» لمقطع «حفظ جديد» له «حصّة الأسبوع» ← «من» يتقدّم بالحصّة، ومقطع المراجعة يمتدّ إليها، والبند يغيب حتّى السبت.
- «حفظ:<معرّف>» (مراجعة) ← آخر مراجعة = اليوم، وعدد المراجعات + ١، والفاصل = الدرجة التالية من ١، ٣، ٧، ١٤، ٣٠، ٦٠، والمراجعة القادمة = اليوم + الفاصل.
- «ثابت:<معرّف>:<التاريخ>» ← صفٌّ في «سجلّ المتكرّر» (إن وصل إليه المفتاح)، بعد البحث بالمفتاح لئلّا يتكرّر.
- ما لا يصل إليه المفتاح، وكلّ مفتاحٍ آخر، يُطبع LEFT ويتركه للوكيل.
كلّ ما نُقل يُكتب في state/recorded-<يوم إنجازه>.txt، فلا يُنقل مرّتين. وما عُلِّم في الأيّام السبعة الماضية ولم يُنقل
(ماكٌ مغلق، أو تعليمٌ قرب منتصف الليل) يُنقل بيوم إنجازه، فلا تضيع علامة. وما مضى عليه ٣٠ يومًا من هذه الملفّات يُحذف.
ثمّ يزامن القائمة من صفحة «قائمة اليوم (للماك)» (config.json ← pages.today_list) إن تغيّر version وكان date اليوم (state/list_version).
- الالتزام «عاجل» الذي لم يُنجز ولا وقت له في القائمة: يُوقَّت تنبيهه بعد urgent.delay_minutes من أوّل ظهوره في القائمة
  (ولا قبل urgent.earliest صباحًا)، ويُكتب أوّل اسمه «عاجل»، ويُحفظ وقته في state/urgent_alerts.json فلا يرنّ مرّةً ثانية
  إذا أُعيدت المزامنة (كان بندٌ عاجل يدخل القائمة وتنبيهه على منتصف الليل الماضي، فلا يرنّ).
السطران الأخيران: SYNC <الحال>   ثمّ   MARKS done=… recorded=… manual=… left=… fail=…   (أو MARKS NO-KEY)
الاستعمال: mac_marks.py [--dry]
"""
import importlib.util, json, os, re, subprocess, sys
from datetime import date, datetime, timedelta

H = os.path.dirname(os.path.abspath(__file__))
DRY = "--dry" in sys.argv
spec = importlib.util.spec_from_file_location("mc", os.path.join(H, "mac_calendar.py"))
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)
C = mc.C
STATE = C.STATE

SILENT = ("قراءة:", "سؤال:", "أسئلة:") + tuple(C.cfg["external_prefixes"])
STEPS = [1, 3, 7, 14, 30, 60]


def next_step(cur):
    if not cur:
        return STEPS[0]
    return next((s for s in STEPS if s > cur), STEPS[-1])


AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def retitle(title, a, b):
    """يبدّل المدى الرقميّ في اسم المقطع (مثل «المتن ٥١–٢٠٠»)، ويُبقي ما سواه."""
    rng = f"{a}–{b}".translate(AR)
    t, n = re.subn(r"[0-9٠-٩]+\s*[–-]\s*[0-9٠-٩]+", rng, title or "", count=1)
    return t if n else f"{title} {rng}".strip()


def next_saturday(today):
    return today + timedelta(days=((5 - today.weekday()) % 7) or 7)


def do_new_memory(tok, p, today):
    """«حفظ جديد» بحصّةٍ أسبوعيّة: يتقدّم «من» بالحصّة، ويمتدّ مقطع المراجعة إليها،
    ويغيب البند حتّى السبت التالي (أوّل الأسبوع)."""
    quota = int(mc.prop(p, "حصّة الأسبوع") or 0)
    start, end = int(mc.prop(p, "من") or 0), int(mc.prop(p, "إلى") or 0)
    matn = mc.prop(p, "المتن")
    new_start = start + quota
    rev = [r for r in mc.query_all(tok, C.db("memory"), {"filter": {"and": [
        {"property": "المتن", "select": {"equals": matn}},
        {"property": "المرحلة", "select": {"equals": "مراجعة"}},
        {"property": "إلى", "number": {"equals": start - 1}}]}})]
    if not DRY:
        props = {"من": {"number": new_start},
                 "آخر مراجعة": {"date": {"start": today.isoformat()}},
                 "المراجعة القادمة": {"date": {"start": next_saturday(today).isoformat()}}}
        if new_start > end:
            props["المرحلة"] = {"select": {"name": "مراجعة"}}
        else:
            props["المقطع"] = {"title": [{"text": {"content": retitle(mc.prop(p, "المقطع"), new_start, end)}}]}
        patch(tok, "pages/" + p["id"], {"properties": props})
        for r in rev[:1]:
            first = int(mc.prop(r, "من") or 1)
            patch(tok, "pages/" + r["id"], {"properties": {
                "إلى": {"number": new_start - 1},
                "المقطع": {"title": [{"text": {"content": retitle(mc.prop(r, "المقطع"), first, new_start - 1)}}]}}})
    return f"حفظ جديد: {start}–{new_start - 1}، والتالي من {new_start} يوم السبت {next_saturday(today)}، والمراجعة تمتدّ إلى {new_start - 1} ({len(rev)} مقطع مراجعة)"


def do_memory(tok, pid, today):
    p = mc.notion(tok, "pages/" + pid)
    if mc.prop(p, "المرحلة") == "حفظ جديد" and mc.prop(p, "حصّة الأسبوع"):
        return do_new_memory(tok, p, today)
    gap = next_step(mc.prop(p, "الفاصل بالأيام"))
    n = (mc.prop(p, "عدد المراجعات") or 0) + 1
    if not DRY:
        patch(tok, "pages/" + pid, {"properties": {
            "آخر مراجعة": {"date": {"start": today.isoformat()}},
            "عدد المراجعات": {"number": n},
            "الفاصل بالأيام": {"number": gap},
            "المراجعة القادمة": {"date": {"start": (today + timedelta(days=gap)).isoformat()}}}})
    return f"الفاصل {gap}، المراجعة {n}"


def do_fixed(tok, key):
    _, fid, day = key.split(":", 2)
    log_db = C.db("recurring_log")
    if mc.query_all(tok, log_db, {"filter": {"property": "المفتاح", "rich_text": {"equals": key}}}):
        return "موجود من قبل"
    name = mc.prop(mc.notion(tok, "pages/" + fid), "الاسم") or key
    if not DRY:
        mc.notion(tok, "pages", {"parent": {"database_id": log_db}, "properties": {
            "البند": {"title": [{"text": {"content": name}}]},
            "التاريخ": {"date": {"start": day}},
            "الأصل": {"relation": [{"id": fid}]},
            "المفتاح": {"rich_text": [{"text": {"content": key}}]}}})
    return name


def mark_urgent(tok, items, today):
    """يوقّت تنبيه الالتزامات العاجلة. يعيد عدد ما وُقِّت."""
    rows = mc.query_all(tok, mc.DB["commitments"], {"filter": {"property": "الأولوية", "select": {"equals": "عاجل"}}})
    urgent = {p["id"].replace("-", "") for p in rows if mc.prop(p, "الحال") not in ("منجز", "معتذر عنه")}
    path = os.path.join(STATE, "urgent_alerts.json")
    st = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    if st.get("date") != today.isoformat():
        st = {"date": today.isoformat(), "keys": {}}
    now = datetime.now(C.TZ)
    eh, em = (int(x) for x in C.cfg["urgent"]["earliest"].split(":"))
    n = 0
    for it in items:
        key = str(it.get("key", ""))
        if not key.startswith("التزام:") or key.split(":", 1)[1].replace("-", "") not in urgent:
            continue
        it["window"] = "عاجل"
        if it.get("time"):
            continue
        t = st["keys"].get(key)
        if not t:
            at = now + timedelta(minutes=C.cfg["urgent"]["delay_minutes"])
            earliest = now.replace(hour=eh, minute=em, second=0, microsecond=0)
            t = max(at, earliest).isoformat(timespec="minutes")
            st["keys"][key] = t
        it["time"] = t
        n += 1
    # العاجل أوّل القائمة
    items.sort(key=lambda x: 0 if x.get("window") == "عاجل" else 1)
    if not DRY:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    return n


KIND_ICON = {"تصحيح": "🐞", "تحسين": "✨", "ملاحظة مستخدم": "💬", "فكرة": "💡"}


def project_notes(tok, items):
    if not C.has_db("project_notes"):
        return
    import re
    for it in items:
        m = re.search(r"ملاحظات «([^»]+)»", it.get("title") or "")
        if not m or "\n• " in (it.get("notes") or ""):
            continue
        rows = mc.query_all(tok, C.db("project_notes"), {"filter": {"and": [
            {"property": "المشروع", "select": {"equals": m.group(1)}},
            {"or": [{"property": "الحال", "select": {"equals": "جديدة"}}, {"property": "الحال", "select": {"equals": "قيد العمل"}}]}]},
            "sorts": [{"property": "التاريخ", "direction": "descending"}]})
        if not rows:
            continue
        lines = [f"• {KIND_ICON.get(mc.prop(r, 'النوع'), '•')} {mc.prop(r, 'الملاحظة')}" for r in rows[:15]]
        if len(rows) > 15:
            lines.append(f"و{len(rows) - 15} غيرها في «ملاحظات المشاريع»")
        it["notes"] = ((it.get("notes") or "") + "\n\n" + "\n".join(lines)).strip()


def sync_list(tok, today):
    blocks = mc.notion(tok, f"blocks/{C.page('today_list')}/children?page_size=100")["results"]
    code = next((b for b in blocks if b["type"] == "code"), None)
    if not code:
        return "NO-JSON"
    data = json.loads("".join(s["plain_text"] for s in code["code"]["rich_text"]))
    vpath = os.path.join(STATE, "list_version")
    old = open(vpath, encoding="utf-8").read().strip() if os.path.exists(vpath) else ""
    if data.get("date") != today.isoformat():
        return "STALE-DATE " + str(data.get("date"))
    if data.get("version") == old:
        return "SAME"
    if DRY:
        return "WOULD-SYNC " + str(data.get("version"))
    items = data.get("items", [])
    # رابط سماع الكلام الأصليّ (يكتبه mac_audio.py)
    lp = os.path.join(STATE, "audio_links.json")
    links = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}
    for it in items:
        k = str(it.get("key", ""))
        cid = k.split(":", 1)[1].replace("-", "") if k.startswith("التزام:") else ""
        if cid in links and "🎧" not in (it.get("notes") or ""):
            it["notes"] = ((it.get("notes") or "") + "\n🎧 اسمع كلامك: " + links[cid]).strip()
    # تفاصيل «العمل على ملاحظات «المشروع»»: البند يقول عدد الملاحظات فقط، والملاحظات نفسها في مخزن «ملاحظات المشاريع».
    # فتُكتب في ملاحظة البند نفسه، فتُقرأ من التذكير دون فتح Notion. (يحتاج المخزنُ اتّصالَ تكامل الماك.)
    try:
        project_notes(tok, items)
    except Exception as e:
        print("NOTES FAIL", str(e)[:120])
    try:
        urg = mark_urgent(tok, items, today)
    except Exception as e:  # لا تُعطَّل المزامنة إن تعذّر الاستعلام
        urg = "FAIL " + str(e)[:60]
    tmp = os.path.join(STATE, "sync_items.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False)
    r = C.osa("reminders.js", "sync", tmp, timeout=900)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200])
    with open(vpath, "w", encoding="utf-8") as f:
        f.write(str(data.get("version")))
    return "DONE " + str(data.get("version")) + " " + r.stdout.strip() + " urgent=" + str(urg)


MANUAL_NOTE = f"أضافه {C.cfg['owner_title']} بيده إلى قائمة «{C.cfg['apple']['reminders_list']}»"


def patch(tok, path, body):
    cmd = ["curl", "-sS", "--max-time", "40", "-X", "PATCH", "https://api.notion.com/v1/" + path,
           "-H", "Authorization: Bearer " + tok, "-H", "Notion-Version: 2022-06-28",
           "-H", "Content-Type: application/json", "--data-binary", "@-"]
    r = subprocess.run(cmd, input=json.dumps(body), capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    if j.get("object") == "error":
        raise RuntimeError(j.get("message"))
    return j


WINDOW_DAYS = 7  # مراجعة ١٧ نوفمبر ٢٠٢٦: كانت العلامة تضيع إن لم يُنقل البند في يوم إنجازه


def local_day(iso):
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().date()


def main():
    if not mc.single("marks"):
        print("MARKS BUSY: جولةٌ أخرى تنقل العلامات الآن"); return 0
    tok = mc.token()
    if not tok:
        print("MARKS NO-KEY")
        return 3
    today = date.today()
    rec_path = os.path.join(STATE, f"recorded-{today.isoformat()}.txt")
    recorded = set()
    if os.path.exists(rec_path):
        recorded = {l.strip() for l in open(rec_path, encoding="utf-8") if l.strip()}
    # المنقول يُعرف بمفتاحه ويوم إنجازه معًا، فالبند الثابت الذي يتكرّر كلّ يوم لا يُخلط بأمسه.
    done_on = {}
    for back in range(WINDOW_DAYS + 1):
        dd = today - timedelta(days=back)
        pth = os.path.join(STATE, f"recorded-{dd.isoformat()}.txt")
        if os.path.exists(pth):
            done_on[dd] = {l.strip() for l in open(pth, encoding="utf-8") if l.strip()}
    old = (today - timedelta(days=30)).isoformat()
    for fn in os.listdir(STATE):
        if fn.startswith("recorded-") and fn.endswith(".txt") and fn[9:19] < old:
            try:
                os.remove(os.path.join(STATE, fn))
            except OSError:
                pass
    r = C.osa("reminders.js", "read", timeout=900)
    items = json.loads(r.stdout)

    new_rec, done, silent, manual, left, fail = [], 0, 0, 0, 0, 0
    for it in items:
        key, title = it.get("key"), (it.get("title") or "").strip()
        cday = local_day(it.get("completionDate")) if it.get("completed") else None
        if it.get("completed") and not cday:
            cday = today  # معلَّمٌ بلا تاريخ إنجاز: يُعدّ من اليوم
        if cday and key and today - timedelta(days=WINDOW_DAYS) <= cday <= today and key not in done_on.get(cday, set()):
            if key.startswith("التزام:"):
                pid = key.split(":", 1)[1]
                try:
                    if not DRY:
                        patch(tok, "pages/" + pid, {"properties": {
                            "الحال": {"status": {"name": "منجز"}},
                            "أُنجز في": {"date": {"start": cday.isoformat()}}}})
                    print("DONE", key, title)
                    new_rec.append((cday, key)); done += 1
                except Exception as e:
                    print("FAIL", key, e); fail += 1
            elif key.startswith(SILENT):
                new_rec.append((cday, key)); silent += 1
            elif key.startswith(("حفظ:", "ثابت:")):
                try:
                    info = do_memory(tok, key.split(":", 1)[1], cday) if key.startswith("حفظ:") else do_fixed(tok, key)
                    print("DONE", key, title, "—", info)
                    new_rec.append((cday, key)); done += 1
                except Exception as e:
                    print("LEFT", key, title, "—", e); left += 1
            else:
                print("LEFT", key, title); left += 1
        elif not key and not it.get("completed") and title and title not in recorded:
            try:
                found = mc.query_all(tok, mc.DB["inbox"], {"filter": {"and": [
                    {"property": "النص", "title": {"equals": title}},
                    {"property": "ملاحظة الوكيل", "rich_text": {"contains": "بيده"}}]}})
                if not found and not DRY:
                    mc.notion(tok, "pages", {"parent": {"database_id": mc.DB["inbox"]}, "properties": {
                        "النص": {"title": [{"text": {"content": title}}]},
                        "المصدر": {"select": {"name": "يدوي"}},
                        "الحال": {"select": {"name": "جديد"}},
                        "ملاحظة الوكيل": {"rich_text": [{"text": {"content": MANUAL_NOTE}}]}}})
                print("MANUAL", title, "(موجود من قبل)" if found else "")
                new_rec.append((today, title)); manual += 1
            except Exception as e:
                print("FAIL", "يدوي:", title, e); fail += 1

    if new_rec and not DRY:
        for dd in sorted({x for x, _ in new_rec}):
            with open(os.path.join(STATE, f"recorded-{dd.isoformat()}.txt"), "a", encoding="utf-8") as f:
                f.write("".join(k + "\n" for x, k in new_rec if x == dd))
    try:
        print("SYNC", sync_list(tok, today))
    except Exception as e:
        print("SYNC FAIL", e)
    print(f"MARKS done={done} recorded={silent} manual={manual} left={left} fail={fail}" + (" (dry)" if DRY else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
