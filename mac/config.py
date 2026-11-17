#!/usr/bin/env python3 -I
"""قارئ إعدادات «المذكّر الذكي». كلّ سكربتٍ في هذا المجلّد يأخذ منه معرّفات Notion والمسارات والخيارات،
فلا يُكتب في السكربتات معرّفٌ ولا اسمٌ ولا مسارٌ خاصّ.

الإعدادات في config.json بجانب هذا الملفّ (انسخه من config.example.json)، أو في المسار الذي يسمّيه
المتغيّر MUDHAKKIR_CONFIG. وما لم يُذكر فيه يؤخذ من الافتراضات أدناه.

الاستعمال من سكربتٍ آخر (والسكربتات تُشغَّل بـ python3 -I، فلا يُستورد بالاسم بل بمساره):
    spec = importlib.util.spec_from_file_location("config", os.path.join(HERE, "config.py"))
    C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
    C.cfg["db"]["inbox"], C.STATE, C.token() …

ومن سطر الأوامر:
    python3 -I config.py --check   ← يفحص الإعدادات ويطبع ما نقص
    python3 -I config.py --shell   ← يطبع متغيّراتٍ لـ transcribe.sh (MUD_…=…)
    python3 -I config.py --get db.inbox
"""
import copy, json, os, shlex, subprocess, sys
from datetime import timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "owner_title": "صاحب النظام",
    "keychain": {"notion": "mudhakkir-notion", "telegram": "mudhakkir-telegram"},
    "db": {},          # معرّفات المخازن لواجهة Notion (database id)
    "data_sources": {},  # معرّفات collection:// للموصل (تُملأ بها تعليمات الوكلاء)
    "pages": {},
    "apple": {"reminders_list": "المذكّر", "calendar_name": "المذكّر"},
    "location": {"city": "", "lat": 0.0, "lon": 0.0, "tz_offset": 3.0,
                 "fajr_angle": 18.0, "isha_angle": 17.0, "isha_minutes_after_maghrib": None, "asr": "standard"},
    "roles": [],
    "health_keywords": ["دواء", "حبّة", "حبة", "إبرة", "فيتامين", "قطرة"],
    "external_prefixes": [],
    "households": {"enabled": False, "by_day": {}, "alternating": []},
    "paths": {
        "state": "state",
        "models": "models",
        "glossary": "glossary.txt",
        "telegram_audio": "telegram",
        "voicememos_out": "voicememos",
        "recordings": "~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/المذكّر/تسجيلات",
        "voice_memos_app": "~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings",
    },
    "whisper": {"bin": "/opt/homebrew/bin/whisper-cli", "ffmpeg": "/opt/homebrew/bin/ffmpeg",
                "model": "ggml-large-v3.bin", "language": "ar", "threads": 8},
    "voice_memos": {"enabled": True, "cutoff_utc": "2026-01-01 00:00:00"},
    "telegram": {"enabled": False, "owner_id": "", "ack": False},
    "shortcuts": {"key_shortcut_name": "مفتاح المذكّر", "key_shortcut_id": "",
                  "questions_shortcut_name": "أسئلة المذكّر", "recordings_folder": "المذكّر/تسجيلات/"},
    "questions": {"after_prayer_minutes": 20, "fresh_minutes": 20},
    "urgent": {"delay_minutes": 10, "earliest": "07:30"},
    "audio": {"enabled": True, "keep_days_unlinked": 7},
    "projects": {"stall_days": 14, "projects": []},
}

REQUIRED_DB = ("inbox", "commitments", "questions", "fixed")


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _path():
    return os.path.expanduser(os.environ.get("MUDHAKKIR_CONFIG") or os.path.join(HERE, "config.json"))


def load():
    p = _path()
    user = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            user = json.load(f)
    c = _merge(DEFAULTS, user)
    c["_loaded_from"] = p if os.path.exists(p) else None
    return c


cfg = load()


def path(key):
    """مسارٌ من cfg["paths"]: النسبيّ يُحسب من مجلّد السكربتات، و~ يُوسَّع."""
    v = os.path.expanduser(cfg["paths"][key])
    return v if os.path.isabs(v) else os.path.join(HERE, v)


STATE = path("state")
os.makedirs(STATE, exist_ok=True)

# المنطقة الزمنيّة من إعداد الموقع (ساعاتٌ عن UTC)
TZ_HOURS = float(cfg["location"].get("tz_offset") or 0)
TZ = timezone(timedelta(hours=TZ_HOURS))


def tz_suffix():
    """مثل +03:00 أو -05:30، لكتابة الأوقات في بنود التذكيرات."""
    m = int(round(abs(TZ_HOURS) * 60))
    return ("-" if TZ_HOURS < 0 else "+") + f"{m // 60:02d}:{m % 60:02d}"


def db(name):
    v = cfg["db"].get(name) or ""
    if not v or v.startswith("<"):
        raise RuntimeError(f"معرّف المخزن «{name}» غير مضبوط في config.json")
    return v


def page(name):
    v = cfg["pages"].get(name) or ""
    if not v or v.startswith("<"):
        raise RuntimeError(f"معرّف الصفحة «{name}» غير مضبوط في config.json")
    return v


def has_db(name):
    v = cfg["db"].get(name) or ""
    return bool(v) and not v.startswith("<")


def keychain(service):
    r = subprocess.run(["security", "find-generic-password", "-s", service, "-w"], capture_output=True, text=True)
    return r.stdout.strip() or None


def token():
    """مفتاح تكامل Notion من سلسلة المفاتيح (لا يُكتب في ملفّ)."""
    return keychain(cfg["keychain"]["notion"])


def reminders_args():
    """وسائط reminders.js: اسم القائمة، والبادئات الخارجيّة التي لا يحذفها sync."""
    out = ["--list=" + cfg["apple"]["reminders_list"]]
    if cfg["external_prefixes"]:
        out.append("--keep=" + ",".join(cfg["external_prefixes"]))
    return out


def osa(script, *args, timeout=900, reminders=None):
    """يشغّل سكربت JXA من هذا المجلّد. reminders.js يأخذ اسم القائمة والبادئات تلقائيًّا."""
    extra = reminders_args() if (reminders if reminders is not None else script == "reminders.js") else []
    r = subprocess.run(["osascript", "-l", "JavaScript", os.path.join(HERE, script), *args, *extra],
                       capture_output=True, text=True, timeout=timeout)
    return r


def roles():
    return cfg.get("roles") or []


def problems():
    out = []
    if not cfg["_loaded_from"]:
        out.append("لا يوجد config.json (انسخ config.example.json إليه واملأه)")
    for k in REQUIRED_DB:
        v = cfg["db"].get(k) or ""
        if not v or v.startswith("<"):
            out.append(f"db.{k} غير مضبوط")
    v = cfg["pages"].get("today_list") or ""
    if not v or v.startswith("<"):
        out.append("pages.today_list غير مضبوط")
    loc = cfg["location"]
    if not loc.get("lat") and not loc.get("lon"):
        out.append("location.lat/lon غير مضبوطين (أوقات الصلاة)")
    if not token():
        out.append(f"مفتاح Notion غير محفوظ في سلسلة المفاتيح (الخدمة {cfg['keychain']['notion']})")
    return out


def _get(dotted):
    x = cfg
    for part in dotted.split("."):
        x = x[part] if isinstance(x, dict) else x[int(part)]
    return x


def _shell():
    w, v = cfg["whisper"], cfg["voice_memos"]
    model = os.path.expanduser(w["model"])
    if not os.path.isabs(model):
        model = os.path.join(path("models"), model)
    pairs = {
        "MUD_BASE": HERE, "MUD_STATE": STATE, "MUD_REC_DIR": path("recordings"), "MUD_VM": path("voice_memos_app"),
        "MUD_VMOUT": path("voicememos_out"), "MUD_TG": path("telegram_audio"), "MUD_GLOSSARY": path("glossary"),
        "MUD_MODEL": model, "MUD_WHISPER": w["bin"], "MUD_FFMPEG": w["ffmpeg"], "MUD_LANG": w["language"],
        "MUD_THREADS": str(w["threads"]), "MUD_VM_ENABLED": "1" if v["enabled"] else "0", "MUD_VM_CUTOFF": v["cutoff_utc"],
        "MUD_TG_ENABLED": "1" if cfg["telegram"]["enabled"] else "0",
    }
    return "\n".join(f"{k}={shlex.quote(str(val))}" for k, val in pairs.items())


if __name__ == "__main__":
    if "--shell" in sys.argv:
        print(_shell())
    elif "--get" in sys.argv:
        x = _get(sys.argv[sys.argv.index("--get") + 1])
        print(json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else x)
    else:
        p = problems()
        print("CONFIG OK" if not p else "CONFIG ناقص:\n- " + "\n- ".join(p))
        sys.exit(1 if p else 0)
