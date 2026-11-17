#!/usr/bin/env python3 -I
"""أوقات الصلاة في مدينة صاحب النظام (حسابٌ فلكيّ بلا شبكة)، من إعداد location في config.json:
  {"city", "lat", "lon", "tz_offset", "fajr_angle", "isha_angle", "isha_minutes_after_maghrib", "asr": "standard"|"hanafi"}
العصر «standard» بظلّ المثل (الجمهور)، و«hanafi» بظلّ المثلين. وإن ضُبط isha_minutes_after_maghrib (كتقويم أمّ القرى: ٩٠)
حُسب العشاء بالدقائق بعد المغرب بدل الزاوية.
الاستعمال: prayer_times.py [YYYY-MM-DD]  ← يطبع JSON بأوقات الفجر والشروق والظهر والعصر والمغرب والعشاء (بالتوقيت المحلّيّ).
هذه تقريبيّة إلى دقيقةٍ أو دقيقتين؛ والأصل تقويم الجهة الرسميّة في بلدك."""
import importlib.util, json, math, os, sys
from datetime import date, datetime, timedelta

_H = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("config", os.path.join(_H, "config.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

loc = C.cfg["location"]
LAT, LNG, TZ = float(loc["lat"]), float(loc["lon"]), float(loc["tz_offset"])
FAJR, ISHA = float(loc.get("fajr_angle") or 18.0), float(loc.get("isha_angle") or 17.0)
ISHA_MIN = loc.get("isha_minutes_after_maghrib")
ASR_FACTOR = 2 if str(loc.get("asr", "standard")).lower() == "hanafi" else 1
d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
D = (datetime(d.year, d.month, d.day, 12) - datetime(2000, 1, 1, 12)).days
g = math.radians((357.529 + 0.98560028 * D) % 360)
q = (280.459 + 0.98564736 * D) % 360
L = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)
e = math.radians(23.439 - 0.00000036 * D)
RA = math.degrees(math.atan2(math.cos(e) * math.sin(L), math.cos(L))) / 15 % 24
dec = math.asin(math.sin(e) * math.sin(L))
EqT = q / 15 - RA
EqT = (EqT + 12) % 24 - 12
noon = 12 + TZ - LNG / 15 - EqT
lat = math.radians(LAT)


def hour_angle(alt_deg):
    a = math.radians(alt_deg)
    x = (math.sin(a) - math.sin(lat) * math.sin(dec)) / (math.cos(lat) * math.cos(dec))
    if abs(x) > 1:
        return None  # الشمس لا تبلغ هذه الزاوية اليوم (خطوط العرض العالية)
    return math.degrees(math.acos(x)) / 15


# مراجعة ١٧ نوفمبر ٢٠٢٦: في خطوط العرض العالية صيفًا لا تنزل الشمس إلى زاوية الفجر أو العشاء، فكان acos يسقط
# بالخطأ ويتعطّل معه التقويم والأسئلة. فيُحسب حينئذٍ بقاعدة سُبع الليل: الفجر قبل الشروق بسُبع الليل، والعشاء بعد المغرب بمثله.
SUN = hour_angle(-0.833)
if SUN is None:  # شمسٌ لا تغرب أو لا تطلع
    SUN = 12.0 - 1 / 60 if math.sin(lat) * math.sin(dec) > 0 else 1 / 60


def deep(alt_deg):
    h = hour_angle(alt_deg)
    return h if h is not None else SUN + (24 - 2 * SUN) / 7


asr_alt = math.degrees(math.atan(1 / (ASR_FACTOR + math.tan(abs(lat - dec)))))
maghrib = noon + SUN + 1 / 60
isha = maghrib + float(ISHA_MIN) / 60 if ISHA_MIN else noon + deep(-ISHA)
t = {"الفجر": noon - deep(-FAJR), "الشروق": noon - SUN, "الظهر": noon + 2 / 60,
     "العصر": noon + (hour_angle(asr_alt) or SUN * 0.6), "المغرب": maghrib, "العشاء": isha}
fmt = lambda h: (datetime(d.year, d.month, d.day) + timedelta(minutes=round(h * 60))).strftime("%H:%M")
print(json.dumps({k: fmt(v) for k, v in t.items()}, ensure_ascii=False))
