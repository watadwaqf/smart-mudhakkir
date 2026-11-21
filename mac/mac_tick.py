#!/usr/bin/env python3 -I
"""نبض الماك: يزامن «التذكيرات» و«التقويم» كلّ عشر دقائق بلا Claude.
الدرس ١٩: انتهت صلاحيّة دخول Claude، فعلقت جولة وكيل الماك يومين، وتوقّفت التذكيرات كلّها بصمت.
والسكربتات الآليّة لا تحتاج ذكاءً اصطناعيًّا، فيشغّلها launchd وحده:
  ١. التقويم والأسئلة، والعلامات والمزامنة، والآفاق، ورصد الإنجاز، واحدًا بعد واحد.
     ويكتب مخرجها في state/tick_last.txt، فيقرؤه وكيل الماك بدل إعادة تشغيلها.
  ٢. يراقب نبض الوكيل (state/agent_heartbeat، يلمسه الوكيل أوّل كلّ جولة): إن مضت عليه ٤٠ دقيقة
     وضع في القائمة بندًا واحدًا «⚠️ وكيل المذكّر متوقّف» ينبّه مرّةً، ويحذفه إذا عاد النبض.
الاستعمال:
  mac_tick.py              نبضةٌ واحدة (يشغّلها launchd)
  mac_tick.py --install    يكتب ~/Library/LaunchAgents/<label>.plist ويحمّله
  mac_tick.py --uninstall  يوقفه ويحذفه
السطر الأخير: TICK ok=n fail=k agent=alive|stale(<دقائق>)|unknown
"""
import datetime, importlib.util, json, os, subprocess, sys, tempfile, time

H = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("config", os.path.join(H, "config.py"))
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
STATE = C.STATE
BEAT = os.path.join(STATE, "agent_heartbeat")
FLAG = os.path.join(STATE, "agent_alert")
LAST = os.path.join(STATE, "tick_last.txt")
STALE_MIN = 40
KEY = "تنبيه:الوكيل"   # بادئة «تنبيه:» لا تحذفها المزامنة ولا يُنقل تعليمها إلى Notion
LABEL = "com.mudhakkir.tick"
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
JOBS = ["mac_calendar.py", "mac_marks.py", "mac_horizons.py", "mac_learn.py"]


def run_job(name):
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, "-I", os.path.join(H, name)], capture_output=True, text=True, timeout=1500)
        out, ok = (r.stdout + r.stderr).strip().splitlines(), r.returncode == 0
    except subprocess.TimeoutExpired:
        out, ok = ["TIMEOUT"], False
    return ok, f"== {name} ({round(time.time() - t0)}ث، {'نجح' if ok else 'فشل'})\n" + "\n".join(out[-15:])


def watch_agent():
    if not os.path.exists(BEAT):
        return "unknown"
    age = (time.time() - os.path.getmtime(BEAT)) / 60
    if age < STALE_MIN:
        if os.path.exists(FLAG):
            C.osa("reminders.js", "remove", KEY); os.unlink(FLAG)
        return "alive"
    if not os.path.exists(FLAG):
        since = datetime.datetime.fromtimestamp(os.path.getmtime(BEAT))
        alarm = since + datetime.timedelta(minutes=STALE_MIN)  # وقتٌ ثابت، فلا يُعاد ضبط التنبيه في كلّ نبضة
        item = {"key": KEY, "title": f"⚠️ وكيل المذكّر متوقّف منذ {since:%H:%M} ({since:%d/%m})",
                "notes": "التذكيرات تُزامَن وحدها، لكنّ التسجيلات والفرز متوقّفان. افتح Claude على الماك، وتأكّد من تسجيل الدخول.",
                "time": alarm.astimezone().isoformat()}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"items": [item]}, f, ensure_ascii=False)
        C.osa("reminders.js", "upsert", f.name); os.unlink(f.name)
        open(FLAG, "w").write(since.isoformat())
    return f"stale({round(age)})"


def install():
    log = os.path.join(STATE, "tick.log")
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>{sys.executable}</string><string>-I</string><string>{os.path.abspath(__file__)}</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""
    uninstall(quiet=True)
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    open(PLIST, "w").write(body)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", PLIST], capture_output=True, text=True)
    print("TICK INSTALLED" if r.returncode == 0 else f"TICK INSTALL FAIL {r.stderr.strip()}")


def uninstall(quiet=False):
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    if os.path.exists(PLIST):
        os.unlink(PLIST)
    if not quiet:
        print("TICK REMOVED")


def main():
    stamp = time.strftime("%Y-%m-%d %H:%M")
    ok = fail = 0; parts = []
    for j in JOBS:
        good, text = run_job(j)
        parts.append(text); ok += good; fail += not good
    agent = watch_agent()
    summary = f"TICK ok={ok} fail={fail} agent={agent}"
    tmp = LAST + ".tmp"
    open(tmp, "w", encoding="utf-8").write(f"نبض {stamp}\n" + "\n\n".join(parts) + "\n\n" + summary + "\n")
    os.replace(tmp, LAST)
    print(stamp, summary, flush=True)


if __name__ == "__main__":
    os.makedirs(STATE, exist_ok=True)
    if "--install" in sys.argv:
        install()
    elif "--uninstall" in sys.argv:
        uninstall()
    else:
        main()
