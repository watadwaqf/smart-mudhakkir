#!/usr/bin/env python3 -I
"""يفحص المستودع كلّه قبل النشر، ويفشل (رمز خروج ١) إن وجد شيئًا خاصًّا:
  - معرّف Notion حقيقيًّا: ٣٢ حرفًا ستّ‑عشريًّا (بشرَطٍ أو بدونها)، ليس أصفارًا ولا حرفًا مكرّرًا.
  - بريدًا إلكترونيًّا.
  - رقم هاتف (دوليًّا بـ + أو 00، أو محلّيًّا مقسومًا، أو ثمانية أرقامٍ متّصلة).
  - مسار مجلّد مستخدمٍ في macOS (مجلّد البيت مكتوبًا باسم صاحبه، والصواب ~ أو متغيّر).
  - أيًّا من الكلمات المحظورة في mac/private_words.txt (كلمةٌ أو عبارةٌ في كلّ سطر، وما بعد # تعليق).
    وهذا الملفّ لا يُرفع (في .gitignore)، فكلّ ناشرٍ يكتب فيه أسماءه وبياناته هو.
الكلمات العربيّة تُطابَق بعد حذف التشكيل والتطويل، كلمةً تامّة تقبل قبلها «و/ف/ب/ل/ك» و«ال»
وبعدها «ة/ه/ي/ية»؛ واللاتينيّة تُطابَق جزءًا من النصّ بلا اعتبار لحالة الحروف.
الاستعمال: python3 -I mac/check_private.py [جذر المستودع]
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(HERE)
WORDS_FILE = os.path.join(HERE, "private_words.txt")
SKIP_DIRS = {".git", "state", "models", "voicememos", "telegram", "__pycache__", "node_modules"}
SKIP_FILES = {os.path.abspath(WORDS_FILE), os.path.join(HERE, "config.json"), os.path.join(HERE, "glossary.txt")}
TEXT_EXT = {".py", ".js", ".sh", ".md", ".json", ".txt", ".toml", ".yml", ".yaml", ".cfg", ".ini", ".html", ".css", ""}

HEX = r"[0-9a-fA-F]"
BOUND = r"[0-9a-fA-F-]"
NOTION_ID = re.compile(rf"(?<!{BOUND})({HEX}{{32}}|{HEX}{{8}}-{HEX}{{4}}-{HEX}{{4}}-{HEX}{{4}}-{HEX}{{12}})(?!{BOUND})")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w-])(?:\+|00(?=[1-9]))\d[\d \-]{6,14}\d(?![\w-])|(?<![\w-])\d{3}[ \-]\d{3,4}[ \-]\d{4}(?![\w-])|(?<![\w.-])\d{8}(?![\w.-])")
USERS = re.compile("/" + "Users/" + r"[^/\s\"'`]+")
TASHKEEL = re.compile(r"[ً-ْٰـ]")
AR_LETTER = r"ء-يٱ-ۓ"


def placeholder_like(h):
    h = h.replace("-", "").lower()
    return len(set(h)) <= 2  # أصفار، أو حرفٌ مكرّر، أو نمطٌ مثل abab…


def load_words():
    if not os.path.exists(WORDS_FILE):
        print(f"تنبيه: {os.path.relpath(WORDS_FILE, ROOT)} غير موجود؛ لن تُفحص الكلمات المحظورة.")
        return []
    out = []
    for line in open(WORDS_FILE, encoding="utf-8"):
        w = line.split("#", 1)[0].strip()
        if w:
            out.append(w)
    return out


def word_patterns(words):
    pats = []
    for w in words:
        n = TASHKEEL.sub("", w)
        if re.search(f"[{AR_LETTER}]", n):
            core = re.escape(n)
            if n.startswith("ال"):
                core = "(?:ال)?" + re.escape(n[2:])  # «الفلانيّ» تطابق «فلانيّ» و«والفلانيّ»
            p = rf"(?<![{AR_LETTER}])(?:[وفبلك])?(?:ال)?{core}(?:ة|ه|ي|ية)?(?![{AR_LETTER}])"
            pats.append((w, re.compile(p)))
        else:
            pats.append((w, re.compile(re.escape(n), re.I)))
    return pats


def files():
    for root, dirs, fs in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in fs:
            p = os.path.abspath(os.path.join(root, f))
            if p in SKIP_FILES or os.path.splitext(f)[1].lower() not in TEXT_EXT:
                continue
            yield p


def main():
    pats = word_patterns(load_words())
    hits = []
    for p in files():
        try:
            text = open(p, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        rel = os.path.relpath(p, ROOT)
        for i, line in enumerate(text.split("\n"), 1):
            norm = TASHKEEL.sub("", line)
            for m in NOTION_ID.finditer(line):
                if not placeholder_like(m.group(1)):
                    hits.append((rel, i, "معرّف Notion", m.group(1)))
            for m in EMAIL.finditer(line):
                hits.append((rel, i, "بريد", m.group(0)))
            for m in PHONE.finditer(line):
                hits.append((rel, i, "رقم هاتف", m.group(0)))
            for m in USERS.finditer(line):
                hits.append((rel, i, "مسار مستخدم", m.group(0)))
            for w, rx in pats:
                if rx.search(norm):
                    hits.append((rel, i, "كلمة محظورة", w))
    if hits:
        for rel, i, kind, what in hits:
            print(f"{rel}:{i}: {kind}: {what}")
        print(f"PRIVATE FAIL: {len(hits)} موضعًا")
        return 1
    print(f"PRIVATE OK: لا شيء خاصّ ({len(pats)} كلمةً محظورة فُحصت)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
