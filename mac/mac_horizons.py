#!/usr/bin/env python3 -I
"""قوائم الآفاق في «التذكيرات» لويدجت شاشة الجوّال.
خمس قوائم، كلٌّ منها أفقٌ لا يتداخل مع غيره (فيكون أوّل ما في الويدجت أقربَه):
  🔭 الأسبوع (غدًا–٧ أيّام)، 🔭 الشهر (٨–٣٠)، 🔭 الربع (٣١–٩١)، 🔭 النصف (٩٢–١٨٢)، 🔭 السنة (١٨٣–٣٦٥).
واليوم في قائمة «المذكّر» نفسها. المصادر: الالتزامات المفتوحة ذات التاريخ، و«المواعيد الدوريّة» (ومنها معالم
التقويم الدراسيّ أو المهنيّ) إن وصل إليها مفتاح الماك. البنود بلا تاريخ ولا تنبيه، والتاريخ في أوّل العنوان، مرتّبةً بالأقرب.
وما علّمه صاحب النظام منجزًا في هذه القوائم يُحصَد إلى Notion (سطر «مرجع: التزام:…» في ملاحظة البند).
ويكتب «تاريخ العرض» في الالتزامات (الاستحقاق وإلّا بدء التذكير)، لأنّ Notion لا يبني تقويمًا على صيغة.
لا يكتب في التذكيرات إلّا إن تغيّر المحتوى (state/horizons_hash).
الأدوار وأيقوناتها وصفحاتها وكلماتها الدالّة من config.json ← roles: [{name, icon, page_id, keywords}].
السطر الأخير: HORIZONS week=… month=… quarter=… half=… year=… [same|written] [periodic=ok|no-access]
الاستعمال: mac_horizons.py [--dry] [--force]
"""
import hashlib, importlib.util, json, os, subprocess, sys
from datetime import date, timedelta

H = os.path.dirname(os.path.abspath(__file__))
DRY, FORCE = "--dry" in sys.argv, "--force" in sys.argv
spec = importlib.util.spec_from_file_location("mc", os.path.join(H, "mac_calendar.py"))
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)
C = mc.C
STATE = C.STATE

AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
DAYS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
ROLE_ICON = {r["name"]: r.get("icon") or "•" for r in C.roles()}
ROLE_PAGE = {(r.get("page_id") or "").replace("-", ""): r["name"] for r in C.roles() if r.get("page_id") and not r["page_id"].startswith("<")}
# الكلمات الدالّة على كلّ دور: العلاقة بالأدوار قد لا تظهر لمفتاح الماك، فيُستنتج الدور من الاسم
GUESS = [(tuple(r.get("keywords") or ()), r["name"]) for r in C.roles() if r.get("keywords")]
BUCKETS = [("🔭 الأسبوع", 1, 7), ("🔭 الشهر", 8, 30), ("🔭 الربع", 31, 91), ("🔭 النصف", 92, 182), ("🔭 السنة", 183, 365)]


def label(d, today):
    delta = (d - today).days
    if delta <= 7:
        return f"{DAYS[d.weekday()]} {str(d.day).translate(AR)}"
    return f"{str(d.day).translate(AR)} {MONTHS[d.month - 1]}"


def guess_role(name):
    return next((r for keys, r in GUESS if any(k in name for k in keys)), "")


def words(t):
    return {w for w in t.replace(":", " ").replace("(", " ").split() if len(w) > 3}


SYNCED = []


def patch(tok, pid, props):
    body = json.dumps({"properties": props})
    r = subprocess.run(["curl", "-sS", "--max-time", "40", "-X", "PATCH", "https://api.notion.com/v1/pages/" + pid,
                        "-H", "Authorization: Bearer " + tok, "-H", "Notion-Version: 2022-06-28",
                        "-H", "Content-Type: application/json", "--data-binary", "@-"], input=body, capture_output=True, text=True)
    return '"object":"page"' in r.stdout


def set_shown(tok, pid, day):
    """«تاريخ العرض» في الالتزامات = الاستحقاق وإلّا بدء التذكير، للتقويم الشهريّ وNotion Calendar (Notion لا يبني التقويم على صيغة)."""
    return patch(tok, pid, {"تاريخ العرض": {"date": {"start": day} if day else None}})


def entries(tok, today):
    out = []
    for p in mc.query_all(tok, mc.DB["commitments"], {"filter": {"property": "الحال", "status": {"does_not_equal": "منجز"}}}):
        if mc.prop(p, "الحال") == "معتذر عنه":
            continue
        dd = mc.prop(p, "الاستحقاق") or mc.prop(p, "يبدأ التذكير")
        shown = mc.prop(p, "تاريخ العرض")
        want = dd["start"][:10] if dd and dd.get("start") else None
        if (shown or {}).get("start", "")[:10] != (want or "") and not DRY:
            SYNCED.append(set_shown(tok, p["id"], want))
        if not dd or not dd.get("start"):
            continue
        out.append((date.fromisoformat(dd["start"][:10]), mc.prop(p, "العنوان") or "", mc.prop(p, "الدور") or "", "التزام", p["id"].replace("-", "")))
    periodic = "ok"
    if not C.has_db("periodic"):
        return out, "unset"
    try:
        for p in mc.query_all(tok, mc.DB["periodic"], {}):
            dd = mc.prop(p, "الموعد القادم")
            if not dd or not dd.get("start"):
                continue
            rel = p["properties"].get("الدور", {}).get("relation", [])
            role = ROLE_PAGE.get(rel[0]["id"].replace("-", ""), "") if rel else ""
            name = mc.prop(p, "الاسم") or ""
            role = role or guess_role(name)  # العلاقة بالأدوار قد لا تظهر لمفتاح الماك، فيُستنتج الدور من الاسم
            end = dd.get("end")
            if end:
                e = date.fromisoformat(end[:10])
                name += f" (حتّى {label(e, today) if (e - today).days > 7 else str(e.day).translate(AR) + ' ' + MONTHS[e.month - 1]})"
            out.append((date.fromisoformat(dd["start"][:10]), name, role, "موعد", ""))
    except RuntimeError:
        periodic = "no-access"
    return out, periodic


HARVEST_JS = r"""
function run() {
  const app = Application('Reminders'); const out = [];
  app.lists().forEach(l => { if (!l.name().startsWith('🔭')) return;
    const b = l.reminders.body(), c = l.reminders.completed(), n = l.reminders.name();
    for (let i = 0; i < b.length; i++) if (c[i] && (b[i] || '').includes('مرجع: التزام:')) out.push({ name: n[i], key: b[i].split('مرجع: التزام:')[1].trim() });
  });
  return JSON.stringify(out);
}
"""


def harvest(tok, today):
    """ما عُلِّم منجزًا في قوائم الآفاق يصير «منجزًا» في الالتزامات (كان التعليم فيها لا يصل، فيعود البند غير منجز)."""
    if DRY:
        return 0
    jsf = os.path.join(STATE, "harvest.js")
    open(jsf, "w", encoding="utf-8").write(HARVEST_JS)
    r = subprocess.run(["osascript", "-l", "JavaScript", jsf], capture_output=True, text=True, timeout=120)
    try:
        done = json.loads(r.stdout or "[]")
    except Exception:
        return 0
    n = 0
    for it in done:
        n += patch(tok, it["key"], {"الحال": {"status": {"name": "منجز"}}, "أُنجز في": {"date": {"start": today.isoformat()}}})
    if n:
        # يُعاد بناء القوائم كلّها لئلّا يبقى البند المعلَّم فيها
        for f in ("horizons_hash", "horizons_prev.json"):
            fp = os.path.join(STATE, f)
            if os.path.exists(fp):
                os.remove(fp)
    return n


def main():
    tok = mc.token()
    if not tok:
        print("HORIZONS NO-KEY"); return 3
    today = date.today()
    harvested = harvest(tok, today)
    ents, periodic = entries(tok, today)
    # لا يتكرّر معلَمٌ دوريّ له التزامٌ في اليوم نفسه بالمعنى نفسه (كرصد الدرجات)
    commits = [(d, words(t)) for d, t, r, k, _ in ents if k == "التزام"]
    ents = [e for e in ents if e[3] == "التزام" or not any(d == e[0] and len(w & words(e[1])) >= 2 for d, w in commits)]
    ents.sort(key=lambda x: (x[0], x[1]))
    lists = []
    for name, lo, hi in BUCKETS:
        items = []
        for d, title, role, kind, cid in ents:
            if lo <= (d - today).days <= hi:
                icon = ROLE_ICON.get(role, "•")
                items.append({"title": f"{label(d, today)} · {icon} {title}",
                              "notes": f"{kind} · {role or 'بلا دور'} · {d.isoformat()}" + (f"\n\nمرجع: التزام:{cid}" if cid else "")})
        lists.append({"name": name, "items": items})
    blob = json.dumps({"lists": lists}, ensure_ascii=False)
    hpath = os.path.join(STATE, "horizons_hash")
    h = hashlib.sha1(blob.encode()).hexdigest()
    old = open(hpath).read().strip() if os.path.exists(hpath) else ""
    counts = " ".join(f"{k}={len(L['items'])}" for k, L in zip(("week", "month", "quarter", "half", "year"), lists))
    if DRY:
        for L in lists:
            print(L["name"]); [print("  ", i["title"]) for i in L["items"]]
        print(f"HORIZONS {counts} dry periodic={periodic}"); return 0
    if h == old and not FORCE:
        print(f"HORIZONS {counts} same periodic={periodic} shown={sum(SYNCED)}/{len(SYNCED)} done={harvested}"); return 0
    # لا تُكتب إلّا القوائم التي تغيّرت، فالكتابة في «التذكيرات» بطيئة
    prev_path = os.path.join(STATE, "horizons_prev.json")
    prev = json.load(open(prev_path, encoding="utf-8")) if os.path.exists(prev_path) and not FORCE else {}
    changed = [L for L in lists if prev.get(L["name"]) != L["items"]]
    path = os.path.join(STATE, "horizons.json")
    open(path, "w", encoding="utf-8").write(json.dumps({"lists": changed}, ensure_ascii=False))
    r = C.osa("horizons.js", "replace", path, timeout=900)
    if r.returncode != 0:
        print("HORIZONS FAIL", (r.stderr or r.stdout).strip()[:200]); return 1
    open(hpath, "w").write(h)
    json.dump({L["name"]: L["items"] for L in lists}, open(prev_path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"HORIZONS {counts} written periodic={periodic} shown={sum(SYNCED)}/{len(SYNCED)} done={harvested}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
