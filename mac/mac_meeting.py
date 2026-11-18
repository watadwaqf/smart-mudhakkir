#!/usr/bin/env python3 -I
"""وضع الاجتماع .
التسجيل الأطول من خمس دقائق (من «المذكّرات الصوتيّة» أو تيليجرام أو «قيّد بالصوت») لا يُفرّغه transcribe.sh مرّتين،
بل يكتب له مهمّةً في state/meetings/ ويطبع «MEETING». وهذا السكربت:
  --kick  يبدأ العامل في الخلفيّة إن لم يكن يعمل (يشغّله وكيل الماك في كلّ جولة، ولا ينتظره).
  --work  العامل: لكلّ مهمّة يفرّغ التسجيل مرّةً واحدة (بالمسرد)، ثمّ يكتب في «الوارد» عنصرًا
          «محضر اجتماع ينتظر الاستخلاص: …» والتفريغ الكامل في محتوى صفحته، فيستخلص منه وكيل الفرز
          الملخّص والقرارات والمطلوب منه ومن غيره، ويسأله سؤالًا واحدًا قبل أن يُنشئ له شيئًا (الدستور، «الاجتماعات»).
          ورسالة تيليجرام الصوتيّة يُحدَّث عنصرها القائم «تنتظر التفريغ» بدل إنشاء عنصرٍ جديد.
السطر الأخير: MEETING kicked|running|idle   أو   MEETING done=n fail=k
"""
import fcntl, glob, json, os, subprocess, sys, tempfile, time
import importlib.util

H = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mc", os.path.join(H, "mac_calendar.py"))
mc = importlib.util.module_from_spec(spec); spec.loader.exec_module(mc)
C = mc.C
STATE = C.STATE
QDIR = os.path.join(STATE, "meetings")
LOCK = os.path.join(STATE, "meeting.lock")
LOG = os.path.join(STATE, "meeting.log")
W = C.cfg["whisper"]
MODEL = os.path.expanduser(W["model"]) if os.path.isabs(os.path.expanduser(W["model"])) else os.path.join(C.path("models"), W["model"])
GLOSS = C.path("glossary")


def running():
    f = open(LOCK, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True, None
    return False, f


def kick():
    jobs = glob.glob(os.path.join(QDIR, "*.json"))
    busy, f = running()
    if busy:
        print(f"MEETING running pending={len(jobs)}"); return
    f.close()
    if not jobs:
        print("MEETING idle"); return
    subprocess.Popen(["/usr/bin/nohup", sys.executable, "-I", os.path.abspath(__file__), "--work"],
                     stdout=open(LOG, "a"), stderr=subprocess.STDOUT, start_new_session=True)
    print(f"MEETING kicked pending={len(jobs)}")


def transcribe(src, out):
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        subprocess.run([W["ffmpeg"], "-nostdin", "-loglevel", "error", "-y", "-i", src,
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav], check=True)
        prompt = open(GLOSS, encoding="utf-8").read() if os.path.exists(GLOSS) else ""
        subprocess.run([W["bin"], "-m", MODEL, "-l", W["language"], "-t", str(W["threads"]), "-np", "-nt",
                        "--prompt", prompt, "-f", wav, "-otxt", "-of", os.path.join(tmp, "out")],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(os.path.join(tmp, "out.txt"), out)


def blocks_of(text):
    paras, cur = [], ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(cur) + len(line) > 1800:
            paras.append(cur); cur = ""
        cur = (cur + " " + line).strip()
    if cur:
        paras.append(cur)
    return [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": p}}]}} for p in paras]


def write_inbox(tok, job, text):
    mins = round(job["secs"] / 60)
    title = f"محضر اجتماع ينتظر الاستخلاص: {job['when']} ({mins} دقيقة)"
    note = (f"اجتماع · فُرِّغ مرّةً واحدة من {job['kind']} {job['when']} ({mins} دقيقة). التفريغ الكامل في محتوى هذه الصفحة. "
            "يُستخلص بحسب قسم «الاجتماعات» في الدستور، ولا يُنشأ منه التزامٌ قبل تأكيد صاحب النظام.")
    page = None
    if job.get("tg_id"):
        found = mc.query_all(tok, mc.DB["inbox"], {"filter": {"property": "ملاحظة الوكيل", "rich_text": {"contains": job["tg_id"]}}})
        if found:
            page = found[0]["id"]
            old = mc.prop(found[0], "ملاحظة الوكيل") or ""
            mc_patch(tok, page, {"properties": {"النص": {"title": [{"text": {"content": title}}]},
                                                "ملاحظة الوكيل": {"rich_text": [{"text": {"content": (old + " · " + note)[:1990]}}]}}})
    if not page:
        src = {"تيليجرام": "تيليجرام"}.get(job["kind"], "زر الإجراءات")
        page = mc.notion(tok, "pages", {"parent": {"database_id": mc.DB["inbox"]}, "properties": {
            "النص": {"title": [{"text": {"content": title}}]}, "المصدر": {"select": {"name": src}},
            "الحال": {"select": {"name": "جديد"}}, "ملاحظة الوكيل": {"rich_text": [{"text": {"content": note}}]}}})["id"]
    bl = blocks_of(text)
    for i in range(0, len(bl), 90):
        mc_patch(tok, f"blocks/{page}/children", {"children": bl[i:i + 90]}, path_is_full=True)
    return page


def mc_patch(tok, path, body, path_is_full=False):
    url = "https://api.notion.com/v1/" + (path if path_is_full else "pages/" + path)
    r = subprocess.run(["curl", "-sS", "--max-time", "60", "-X", "PATCH", url, "-H", "Authorization: Bearer " + tok,
                        "-H", "Notion-Version: 2022-06-28", "-H", "Content-Type: application/json", "--data-binary", "@-"],
                       input=json.dumps(body), capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    if j.get("object") == "error":
        raise RuntimeError(j.get("message"))
    return j


def work():
    busy, lockf = running()
    if busy:
        print("MEETING running"); return
    tok = mc.token()
    done = fail = 0
    while True:
        jobs = sorted(glob.glob(os.path.join(QDIR, "*.json")))
        if not jobs:
            break
        jp = jobs[0]
        job = json.load(open(jp, encoding="utf-8"))
        try:
            print(time.strftime("%H:%M"), "يفرّغ", job["src"], flush=True)
            if not os.path.exists(job["out"]):
                transcribe(job["src"], job["out"])
            text = open(job["out"], encoding="utf-8").read()
            page = write_inbox(tok, job, text)
            os.replace(jp, jp + ".done")
            print(time.strftime("%H:%M"), "كُتب في الوارد", page, flush=True); done += 1
        except Exception as e:
            job["tries"] = job.get("tries", 0) + 1
            print(time.strftime("%H:%M"), "FAIL", str(e)[:200], flush=True); fail += 1
            if job["tries"] >= 3:
                os.replace(jp, jp + ".failed")
            else:
                json.dump(job, open(jp, "w", encoding="utf-8"), ensure_ascii=False)
            break
    print(f"MEETING done={done} fail={fail}")


if __name__ == "__main__":
    os.makedirs(QDIR, exist_ok=True)
    work() if "--work" in sys.argv else kick()
