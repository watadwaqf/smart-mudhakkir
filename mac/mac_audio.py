#!/usr/bin/env python3 -I
"""يُرفق الصوت الأصليّ بما صار إليه (بإذن صاحب النظام: الصوت في Notion ليسمعه من التذكير فيتذكّر ما أراد).
يعمل إن كان audio.enabled في config.json (الافتراض نعم).
لكلّ عنصرٍ في «الوارد» فُرِّغ من صوت (مذكّرة صوتيّة، أو تسجيل الاختصار، أو صوت تيليجرام) وصُنِّف،
ولم يُرفق صوته بعد: يرفع المقطع إلى Notion، ويضعه كتلة صوتٍ في صفحة العنصر وفي كلّ التزامٍ في «صار إلى»،
ويكتب في «ملاحظة الوكيل» «🎧 أُرفق الصوت»، ويحفظ في state/audio_links.json أيّ الالتزامات لها صوت
(فيضيف mac_marks.py إلى ملاحظة بندها في التذكيرات رابط «🎧 اسمع كلامك»).
بلا ذكاءٍ اصطناعيّ، بمفتاح Notion الخاصّ بالماك. السطر الأخير: AUDIO attached=n pending=m [fail=k]
"""
import importlib.util, json, os, re, sqlite3, subprocess, sys
from datetime import date, timedelta

H = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mc", os.path.join(H, "mac_calendar.py"))
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)
C = mc.C
STATE = C.STATE
LINKS = os.path.join(STATE, "audio_links.json")
MARK = "🎧 أُرفق الصوت"
VM = C.path("voice_memos_app")
REC = C.path("recordings")
TG = C.path("telegram_audio")
FFMPEG = C.cfg["whisper"]["ffmpeg"]
KEEP_DAYS = int(C.cfg["audio"].get("keep_days_unlinked") or 7)
AR2EN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def find_audio(note):
    """يعيّن ملفّ الصوت من «ملاحظة الوكيل» بالعلامة التي كتبها التفريغ."""
    n = note.translate(AR2EN)
    m = re.search(r"مذكّرة صوتيّة (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", n)
    if m and os.path.exists(os.path.join(VM, "CloudRecordings.db")):
        con = sqlite3.connect(f"file:{VM}/CloudRecordings.db?mode=ro", uri=True)
        row = con.execute("SELECT ZPATH FROM ZCLOUDRECORDING WHERE datetime(ZDATE+978307200,'unixepoch','localtime')=?",
                          (m.group(1),)).fetchone()
        con.close()
        if row and row[0] and os.path.exists(os.path.join(VM, row[0])):
            return os.path.join(VM, row[0])
    m = re.search(r"tg:(\d+)", n)
    if m:
        for f in os.listdir(TG) if os.path.isdir(TG) else []:
            if re.match(rf"tgc?_{m.group(1)}\.(oga|ogg|opus|mp3|m4a|mp4|wav)$", f):
                return os.path.join(TG, f)
    m = re.search(r"([\w\-_]+\.m4a)", n)
    if m and os.path.exists(os.path.join(REC, m.group(1))):
        return os.path.join(REC, m.group(1))
    return None


def curl(args, data=None):
    r = subprocess.run(["curl", "-sS", "--max-time", "120"] + args, input=data, capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    if j.get("object") == "error":
        raise RuntimeError(j.get("message"))
    return j


def upload(tok, path):
    # Notion يرفض امتداد m4a، فيُحوَّل كلّ مقطعٍ إلى mp3 (صغيرٌ ويعمل في كلّ تطبيق)
    mp3 = os.path.join(STATE, "upload.mp3")
    r = subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-i", path,
                        "-ac", "1", "-b:a", "48k", mp3], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg " + r.stderr[:80])
    path, ctype, name = mp3, "audio/mpeg", "voice.mp3"
    hdr = ["-H", "Authorization: Bearer " + tok, "-H", "Notion-Version: 2022-06-28"]
    fu = curl(["-X", "POST", "https://api.notion.com/v1/file_uploads"] + hdr + ["-H", "Content-Type: application/json",
              "--data-binary", "@-"], json.dumps({"mode": "single_part", "filename": name, "content_type": ctype}))
    curl(["-X", "POST", f"https://api.notion.com/v1/file_uploads/{fu['id']}/send"] + hdr +
         ["-F", f"file=@{path};type={ctype};filename={name}"])
    return fu["id"]


def attach(tok, page_id, fid, caption):
    body = {"children": [{"type": "audio", "audio": {"type": "file_upload", "file_upload": {"id": fid},
                                                     "caption": [{"type": "text", "text": {"content": caption}}]}}]}
    curl(["-X", "PATCH", f"https://api.notion.com/v1/blocks/{page_id}/children", "-H", "Authorization: Bearer " + tok,
          "-H", "Notion-Version: 2022-06-28", "-H", "Content-Type: application/json", "--data-binary", "@-"],
         json.dumps(body))


def main():
    if not C.cfg["audio"].get("enabled", True):
        print("AUDIO OFF"); return 0
    tok = mc.token()
    if not tok:
        print("AUDIO NO-KEY"); return 3
    links = json.load(open(LINKS, encoding="utf-8")) if os.path.exists(LINKS) else {}
    since = (date.today() - timedelta(days=14)).isoformat()
    rows = mc.query_all(tok, mc.DB["inbox"], {"filter": {"and": [
        {"timestamp": "created_time", "created_time": {"on_or_after": since}},
        {"property": "ملاحظة الوكيل", "rich_text": {"contains": "فُرِّغ من"}}]}})
    attached = pending = fail = 0
    changed = False
    for p in rows:
        note = mc.prop(p, "ملاحظة الوكيل") or ""
        if MARK in note or mc.prop(p, "الحال") not in ("صُنِّف", "أُهمل"):
            if MARK not in note:
                pending += 1
            continue
        path = find_audio(note)
        if not path:
            pending += 1
            continue
        try:
            targets = [p["id"]] + [r["id"] for r in p["properties"].get("صار إلى", {}).get("relation", [])]
            when = p["created_time"][:10]
            for t in targets:
                fid = upload(tok, path)  # كلّ رفعٍ يُستعمل مرّةً واحدة
                attach(tok, t, fid, f"🎧 كلامك الأصليّ ({when})")
                if t != p["id"]:
                    links[t.replace("-", "")] = "https://www.notion.so/" + t.replace("-", "")
            mc_patch = {"properties": {"ملاحظة الوكيل": {"rich_text": [{"text": {"content": (note + " · " + MARK)[:1990]}}]}}}
            curl(["-X", "PATCH", "https://api.notion.com/v1/pages/" + p["id"], "-H", "Authorization: Bearer " + tok,
                  "-H", "Notion-Version: 2022-06-28", "-H", "Content-Type: application/json", "--data-binary", "@-"],
                 json.dumps(mc_patch))
            attached += 1
            changed = changed or len(targets) > 1
        except Exception as e:
            fail += 1
            print("AUDIO FAIL", p["id"], str(e)[:120])
    if changed:
        json.dump(links, open(LINKS, "w", encoding="utf-8"), ensure_ascii=False)
        vp = os.path.join(STATE, "list_version")
        if os.path.exists(vp):
            os.remove(vp)  # لتعيد mac_marks.py المزامنة فيظهر رابط «🎧» في الملاحظة
    try:
        removed = cleanup(tok, links)
    except Exception as e:
        removed = "FAIL " + str(e)[:80]
    print(f"AUDIO attached={attached} pending={pending} removed={removed}" + (f" fail={fail}" if fail else ""))
    return 0


DONE = ("منجز", "معتذر عنه")
GONE = "🗑 حُذف الصوت"


def drop_audio(tok, page_id):
    """يحذف كتل «🎧 كلامك الأصليّ» من الصفحة (والمقطع الأصليّ باقٍ في «المذكّرات الصوتيّة» على الجوّال)."""
    n = 0
    for b in mc.notion(tok, f"blocks/{page_id}/children?page_size=100").get("results", []):
        cap = "".join(x.get("plain_text", "") for x in (b.get("audio") or {}).get("caption", []))
        if b.get("type") == "audio" and cap.startswith("🎧 كلامك الأصليّ"):
            curl(["-X", "DELETE", "https://api.notion.com/v1/blocks/" + b["id"], "-H", "Authorization: Bearer " + tok,
                  "-H", "Notion-Version: 2022-06-28"])
            n += 1
    return n


def cleanup(tok, links):
    """حفظًا لمساحة Notion: إذا تمّت الالتزامات التي صار إليها المدخل (منجز أو معتذر عنه) حُذف صوته منها
    ومن صفحته في الوارد. وما لم يصر إلى التزام (تدريب، أو جواب، أو أُهمل) يُحذف صوته بعد KEEP_DAYS أيّام
    (audio.keep_days_unlinked، الافتراض سبعة). مرّةً في الساعة. والأصل باقٍ في «المذكّرات الصوتيّة» على الجوّال."""
    stamp = os.path.join(STATE, "audio_cleanup")
    import time
    if os.path.exists(stamp) and time.time() - os.path.getmtime(stamp) < 3600:
        return "later"
    rows = mc.query_all(tok, mc.DB["inbox"], {"filter": {"and": [
        {"property": "ملاحظة الوكيل", "rich_text": {"contains": MARK}},
        {"property": "ملاحظة الوكيل", "rich_text": {"does_not_contain": GONE}}]}})
    status, removed, old = {}, 0, (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    for p in rows:
        targets = [r["id"] for r in p["properties"].get("صار إلى", {}).get("relation", [])]
        for t in targets:
            if t not in status:
                try:
                    pg = mc.notion(tok, "pages/" + t)
                    status[t] = "منجز" if pg.get("archived") or pg.get("in_trash") else (mc.prop(pg, "الحال") or "")
                except Exception:
                    status[t] = "منجز"  # صفحةٌ لم تعد موجودة
        if targets:
            if not all(status[t] in DONE for t in targets):
                continue
        elif p["created_time"][:10] > old:
            continue
        for t in targets + [p["id"]]:
            removed += drop_audio(tok, t)
            links.pop(t.replace("-", ""), None)
        note = mc.prop(p, "ملاحظة الوكيل") or ""
        curl(["-X", "PATCH", "https://api.notion.com/v1/pages/" + p["id"], "-H", "Authorization: Bearer " + tok,
              "-H", "Notion-Version: 2022-06-28", "-H", "Content-Type: application/json", "--data-binary", "@-"],
             json.dumps({"properties": {"ملاحظة الوكيل": {"rich_text": [{"text": {"content": (note + " · " + GONE + " " + date.today().isoformat())[:1990]}}]}}}))
    json.dump(links, open(LINKS, "w", encoding="utf-8"), ensure_ascii=False)
    open(stamp, "w").write(date.today().isoformat())
    return removed


if __name__ == "__main__":
    sys.exit(main())
