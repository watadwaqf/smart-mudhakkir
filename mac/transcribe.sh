#!/bin/zsh
# يفرّغ التسجيلات محلّيًّا بنموذج Whisper (whisper.cpp)، ولا يُخرج الصوت من الماك.
# المسارات والنموذج واللغة من config.json (يقرؤها config.py --shell).
# لكلّ تسجيلٍ «X.m4a» بلا «X.txt» بجانبه: يُنزَّل من iCloud إن لزم، ثمّ يُفرَّغ إلى «X.txt»،
# ويُفرَّغ مرّةً ثانية بلا مسرد إلى «X.raw.txt» (المسرد يصحّح الأسماء لكنّه يُسقط الكلمات الأجنبيّة).
# يطبع سطرًا لكلّ تفريغٍ جديد:  NEW<TAB>اسم الملف<TAB>مسار النصّ   (وNEW-VM لمذكّرات Apple، وNEW-TG لتيليجرام)
# التسجيل يبقى كما هو، فهو الأصل.
setopt null_glob
HERE="${0:A:h}"
eval "$(/usr/bin/python3 -I "$HERE/config.py" --shell)" || { echo "ERROR: تعذّرت قراءة الإعدادات"; exit 1; }
DIR="${MUDHAKKIR_REC_DIR:-$MUD_REC_DIR}"
BASE="$MUD_BASE"
MODEL="$MUD_MODEL"
PROMPT=""
[[ -f "$MUD_GLOSSARY" ]] && PROMPT="$(cat "$MUD_GLOSSARY")"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[[ -f "$MODEL" ]] || { echo "ERROR: النموذج غير موجود: $MODEL"; exit 1; }
mkdir -p "$DIR"

# التسجيلات التي لم تنزل بعدُ من iCloud تظهر بأسماء مثل .X.m4a.icloud
for stub in "$DIR"/.*.m4a.icloud; do
  brctl download "$stub" 2>/dev/null
done
for i in {1..30}; do
  stubs=("$DIR"/.*.m4a.icloud)
  (( ${#stubs} == 0 )) && break
  sleep 2
done

transcribe() {  # $1 = ملفّ الصوت، $2 = مسار النصّ الناتج
  "$MUD_FFMPEG" -nostdin -loglevel error -y -i "$1" -ar 16000 -ac 1 -c:a pcm_s16le "$TMP/a.wav" || return 1
  if [[ -n "$PROMPT" ]]; then
    "$MUD_WHISPER" -m "$MODEL" -l "$MUD_LANG" -t "$MUD_THREADS" -np -nt --prompt "$PROMPT" -f "$TMP/a.wav" -otxt -of "$TMP/out" >/dev/null 2>&1 || return 1
  else
    "$MUD_WHISPER" -m "$MODEL" -l "$MUD_LANG" -t "$MUD_THREADS" -np -nt -f "$TMP/a.wav" -otxt -of "$TMP/out" >/dev/null 2>&1 || return 1
  fi
  mv "$TMP/out.txt" "$2"
  # تفريغٌ ثانٍ بلا مسرد: المسرد يصحّح الأسماء لكنّه يُسقط الكلمات الأجنبيّة والعامّيّة
  # (كلمةٌ مثل «إيفنت» تسقط فيبقى ما بعدها)، والوكيل يجمع بين التفريغين عند التصحيح.
  if [[ -n "$PROMPT" ]]; then
    "$MUD_WHISPER" -m "$MODEL" -l "$MUD_LANG" -t "$MUD_THREADS" -np -nt -f "$TMP/a.wav" -otxt -of "$TMP/raw" >/dev/null 2>&1 && mv "$TMP/raw.txt" "${2%.txt}.raw.txt"
  fi
  return 0
}

# ── المصدر الثاني: تطبيق «المذكّرات الصوتيّة» (زرّ الإجراءات ← مذكّرة صوتيّة) ──
# لا يُؤخذ إلّا ما سُجّل بعد بدء العمل بالنظام (voice_memos.cutoff_utc)، فالتسجيلات القديمة ليست للمذكّر.
VM="$MUD_VM"
VMOUT="$MUD_VMOUT"
CUTOFF="$MUD_VM_CUTOFF"   # بتوقيت UTC
if [[ -z "$MUDHAKKIR_REC_DIR" && "$MUD_VM_ENABLED" == 1 && -f "$VM/CloudRecordings.db" ]]; then
  mkdir -p "$VMOUT"
  # يُفتح التطبيق مخفيًّا ليزامن التسجيلات الجديدة وينزّلها، ثمّ يُغلق إن كان الوكيل هو الذي فتحه.
  # فإن كان صاحب النظام قد فتحه بنفسه فلا يُمسّ (كان يظهر في وجهه مع كلّ جولة).
  if ! pgrep -xq VoiceMemos; then
    open -g -j -b com.apple.VoiceMemos 2>/dev/null
    sleep 20
    osascript -e 'tell application id "com.apple.VoiceMemos" to quit' >/dev/null 2>&1 || pkill -x VoiceMemos 2>/dev/null
  fi
  sqlite3 -separator $'\t' "file:$VM/CloudRecordings.db?mode=ro" \
    "SELECT ZUNIQUEID, IFNULL(ZPATH,''), datetime(ZDATE+978307200,'unixepoch','localtime'), CAST(ZDURATION AS INT)
     FROM ZCLOUDRECORDING WHERE datetime(ZDATE+978307200,'unixepoch') > '$CUTOFF' ORDER BY ZDATE;" |
  while IFS=$'\t' read -r uid rel when secs; do
    out="$VMOUT/$uid.txt"
    [[ -f "$out" ]] && continue
    src="$VM/$rel"
    if [[ -z "$rel" || ! -f "$src" ]]; then echo "PENDING	مذكّرة صوتيّة $when	لم ينزل الملفّ إلى الماك بعد"; continue; fi
    if transcribe "$src" "$out"; then
      echo "NEW-VM	مذكّرة صوتيّة $when ($secs ث)	$out"
    else
      echo "FAIL	مذكّرة صوتيّة $when	whisper"
    fi
  done
fi

# ── المصدر الثالث: رسائل تيليجرام الصوتيّة (ينزّلها telegram_pull.py) ──
TG="$MUD_TG"
if [[ -z "$MUDHAKKIR_REC_DIR" && "$MUD_TG_ENABLED" == 1 && -d "$TG" ]]; then
  # (القائمة صريحةً لا بنمط zsh الموسّع، ليقرأها bash -n أيضًا؛ وnull_glob يُسقط ما لا يطابق)
  for f in "$TG"/*.oga "$TG"/*.ogg "$TG"/*.opus "$TG"/*.mp3 "$TG"/*.m4a "$TG"/*.mp4 "$TG"/*.wav; do
    b="${f:r}"
    [[ -f "$b.txt" ]] && continue
    if transcribe "$f" "$b.txt"; then echo "NEW-TG	${f:t}	$b.txt"; else echo "FAIL	${f:t}	whisper"; fi
  done
fi

# ── المصدر الأوّل: اختصار التسجيل (يحفظ في iCloud Drive) ──
for f in "$DIR"/*.m4a; do
  b="${f:r}"
  [[ -f "$b.txt" ]] && continue
  if transcribe "$f" "$b.txt"; then echo "NEW	${f:t}	$b.txt"; else echo "FAIL	${f:t}	whisper"; fi
done
