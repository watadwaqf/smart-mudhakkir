#!/usr/bin/env python3 -I
"""يقرأ مجلّدات المشاريع التقنيّة قراءةً فقط، فيعرف آخر تعديلٍ في كلٍّ منها.
المشاريع في config.json ← projects: {"stall_days": 14, "projects": [{"name", "paths": [...], "watch": true}]}.
- آخر تعديل = أحدث commit إن كان المجلّد git، وإلّا أحدث ملفّ (بلا node_modules و.git وbuild وDerivedData وPods).
- يكتب state/projects_activity.json.
- المشروع المراقَب (watch) الذي مرّ عليه stall_days بلا تعديل: عنصرٌ واحد في «الوارد» لكلّ فترة توقّف، لا يتكرّر (state/projects_alerted.json).
السطر الأخير: PROJECTS ok=… stalled=… alerted=…   أو PROJECTS NO-KEY
الاستعمال: mac_projects.py [--dry] [--force]   (مرّةً في اليوم، وما بعدها SKIP)
"""
import importlib.util, json, os, subprocess, sys
from datetime import date, datetime

H = os.path.dirname(os.path.abspath(__file__))
DRY = "--dry" in sys.argv
SKIP = {"node_modules", ".git", "build", "DerivedData", "Pods", ".build", "dist", ".next", "__pycache__", "venv", ".venv"}
spec = importlib.util.spec_from_file_location("mc", os.path.join(H, "mac_calendar.py"))
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)
C = mc.C
STATE = C.STATE


def last_change(path):
    p = os.path.expanduser(path)
    if not os.path.isdir(p):
        return None
    r = subprocess.run(["git", "-C", p, "log", "-1", "--format=%cs"], capture_output=True, text=True)
    best = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    newest = 0
    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for f in files:
            try:
                newest = max(newest, os.stat(os.path.join(root, f)).st_mtime)
            except OSError:
                pass
    fs = date.fromtimestamp(newest).isoformat() if newest else None
    return max(x for x in (best, fs) if x) if (best or fs) else None


def main():
    cfg = C.cfg["projects"]
    if not cfg.get("projects"):
        print("PROJECTS ok=0 (لا مشاريع في config.json)"); return 0
    today = date.today()
    act = os.path.join(STATE, "projects_activity.json")
    if "--force" not in sys.argv and not DRY and os.path.exists(act) and json.load(open(act)).get("date") == today.isoformat():
        print("PROJECTS SKIP (قُرئت اليوم)"); return 0
    alerted_path = os.path.join(STATE, "projects_alerted.json")
    alerted = json.load(open(alerted_path)) if os.path.exists(alerted_path) else {}
    out, stalled, new_alerts = {}, 0, 0
    tok = None
    for pr in cfg["projects"]:
        dates = [d for d in (last_change(x) for x in pr["paths"]) if d]
        last = max(dates) if dates else None
        days = (today - date.fromisoformat(last)).days if last else None
        out[pr["name"]] = {"last": last, "days": days, "watch": pr.get("watch", False)}
        print("PROJECT", pr["name"], last or "?", f"({days} يومًا)" if days is not None else "")
        if pr.get("watch") and days is not None and days >= cfg["stall_days"]:
            stalled += 1
            if alerted.get(pr["name"]) == last:
                continue
            tok = tok or mc.token()
            if not tok:
                print("PROJECTS NO-KEY"); return 3
            text = f"لم يتغيّر مشروع «{pr['name']}» منذ {days} يومًا (آخر تعديل {last})."
            if not DRY:
                mc.notion(tok, "pages", {"parent": {"database_id": mc.DB["inbox"]}, "properties": {
                    "النص": {"title": [{"text": {"content": text}}]},
                    "المصدر": {"select": {"name": "يدوي"}},
                    "الحال": {"select": {"name": "جديد"}},
                    "ملاحظة الوكيل": {"rich_text": [{"text": {"content": "كتبه mac_projects.py من مجلّدات المشاريع (قراءةً فقط). يُسأل صاحب النظام: أين وصل المشروع، أم توقّف؟"}}]}}})
                alerted[pr["name"]] = last
            print("STALLED", pr["name"], text); new_alerts += 1
    if not DRY:
        json.dump({"date": today.isoformat(), "projects": out}, open(os.path.join(STATE, "projects_activity.json"), "w"), ensure_ascii=False, indent=1)
        json.dump(alerted, open(alerted_path, "w"), ensure_ascii=False)
    print(f"PROJECTS ok={len(out)} stalled={stalled} alerted={new_alerts}" + (" (dry)" if DRY else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
