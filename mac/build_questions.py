"""يبني اختصار «أسئلة المذكّر»: يعرض كلّ سؤالٍ مفتوح في أيّ وقت (بلا مواعيد)، بالأولويّة ثمّ القِدَم، واحدًا واحدًا.
ولكلٍّ منها خياراته (بعد حذف ما كتبه الوكيل من خيارات الصوت مثل «سأذكرها بصوتي») مع «✍️ أكتب جوابي» و«🎙 أجيب بصوتي» و«⏭ لاحقًا» (يتخطّاه ويبقى معروضًا) و«⏹ أكتفي الآن».
الجواب والتأجيل يُكتبان في «الوارد» (إدراجٌ فقط)، والوكيل يطبّقهما في جولة الفرز التالية.
الاستعمال: python3 -I build_questions.py out.shortcut
  ثمّ: shortcuts sign --mode people-who-know-me --input out.shortcut --output «أسئلة المذكّر».shortcut
معرّفا مخزنَي «الوارد» و«الأسئلة» واسم اختصار المفتاح من config.json (db.inbox، db.questions، shortcuts.*).
"""
import importlib.util
import os
import plistlib
import sys
import uuid

_H = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("config", os.path.join(_H, "config.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
SC = C.cfg["shortcuts"]

OBJ = "￼"
INBOX_DB = C.db("inbox")
QUESTIONS_DB = C.db("questions")
KEY_ID = SC.get("key_shortcut_id") or ""
KEY_NAME = SC["key_shortcut_name"]
FOLDER = SC["recordings_folder"]
VOICE = "🎙 أجيب بصوتي"
WRITE = "✍️ أكتب جوابي"
LATER = "⏭ لاحقًا (تخطَّ)"
STOP = "⏹ أكتفي الآن"
LATER_OPTS = "غدًا|بعد ثلاثة أيّام|بعد أسبوع|بعد شهر"


def key_workflow():
    """مرجع اختصار «مفتاح المذكّر» (يعيد مفتاح Notion). المعرّف اختياريّ: إن لم يُضبط في الإعدادات
    (shortcuts.key_shortcut_id) يُشار إليه باسمه وحده."""
    w = {"workflowName": KEY_NAME, "isSelf": False}
    if KEY_ID:
        w["workflowIdentifier"] = KEY_ID
    return w


def U():
    return str(uuid.uuid4()).upper()


def out(uid, name):
    return {"OutputUUID": uid, "Type": "ActionOutput", "OutputName": name}


REPEAT_ITEM = {"Type": "Variable", "VariableName": "Repeat Item"}


def att(ref):
    return {"Value": ref, "WFSerializationType": "WFTextTokenAttachment"}


def ts(template, refs=()):
    ranges, pos, it = {}, 0, iter(refs)
    for ch in template:
        if ch == OBJ:
            ranges["{%d, 1}" % pos] = next(it)
        pos += len(ch.encode("utf-16-le")) // 2
    return {"Value": {"string": template, "attachmentsByRange": ranges}, "WFSerializationType": "WFTextTokenString"}


def A(identifier, **params):
    return {"WFWorkflowActionIdentifier": identifier, "WFWorkflowActionParameters": params}


def post(actions, key_id, url, body_template, refs):
    body_id, url_id = U(), U()
    actions += [
        A("is.workflow.actions.gettext", UUID=body_id, WFTextActionText=ts(body_template, refs)),
        A("is.workflow.actions.downloadurl", UUID=url_id, WFURL=url, WFHTTPMethod="POST", ShowHeaders=True,
          WFHTTPHeaders={"Value": {"WFDictionaryFieldValueItems": [
              {"WFItemType": 0, "WFKey": ts("Authorization"), "WFValue": ts("Bearer " + OBJ, [out(key_id, "Shortcut Result")])},
              {"WFItemType": 0, "WFKey": ts("Notion-Version"), "WFValue": ts("2022-06-28")},
              {"WFItemType": 0, "WFKey": ts("Content-Type"), "WFValue": ts("application/json")},
          ]}, "WFSerializationType": "WFDictionaryFieldValue"},
          WFHTTPBodyType="File", WFRequestVariable=att(out(body_id, "Text"))),
    ]
    return url_id


def get_key(actions, src, key):
    uid = U()
    actions.append(A("is.workflow.actions.getvalueforkey", UUID=uid, WFDictionaryKey=key, WFInput=att(src)))
    return out(uid, "Dictionary Value")


def first_plain(actions, src, path):
    arr = get_key(actions, src, path)
    item = U()
    actions.append(A("is.workflow.actions.getitemfromlist", UUID=item, WFItemSpecifier="First Item", WFInput=att(arr)))
    return get_key(actions, out(item, "Item from List"), "plain_text")


def inbox_body(text_tmpl, note_tmpl):  # noqa
    return ('{"parent":{"database_id":"%s"},"properties":{"النص":{"title":[{"text":{"content":"%s"}}]},'
            '"ملاحظة الوكيل":{"rich_text":[{"text":{"content":"%s"}}]},'
            '"المصدر":{"select":{"name":"أسئلة المذكّر"}},"الحال":{"select":{"name":"جديد"}}}}') % (INBOX_DB, text_tmpl, note_tmpl)


acts = []
key_id = U()
acts.append(A("is.workflow.actions.runworkflow", UUID=key_id, WFShowWorkflow=False, WFWorkflowName=KEY_NAME,
              WFWorkflow=key_workflow()))

q_url = post(acts, key_id, "https://api.notion.com/v1/databases/%s/query" % QUESTIONS_DB,
             '{"filter":{"property":"الحال","select":{"equals":"مفتوح"}},'
             '"sorts":[{"property":"الأولويّة","direction":"ascending"},{"timestamp":"created_time","direction":"ascending"}],"page_size":50}', [])
results = get_key(acts, out(q_url, "Contents of URL"), "results")

loop = U()
acts.append(A("is.workflow.actions.repeat.each", GroupingIdentifier=loop, WFControlFlowMode=0, WFInput=att(results)))
qid = get_key(acts, REPEAT_ITEM, "id")
qtext = first_plain(acts, REPEAT_ITEM, "properties.السؤال.title")
opts = first_plain(acts, REPEAT_ITEM, "properties.الخيارات.rich_text")

# الخيارات أجوبةٌ فقط (الدستور يمنع الوكيل من كتابة خيار صوتٍ أو تأجيل فيها)، ثمّ الأربعة الثابتة.
# وإن خلا السؤال من الخيارات عُرضت الثابتة وحدها، لئلّا يظهر سطرٌ فارغ.
# (لا تُستعمل «استبدال النصّ» هنا: جُرّبت فأفسدت التقسيم، فصار الاختصار يختار وحده.)
FIXED = WRITE + "|" + VOICE + "|" + LATER + "|" + STOP
g_opts = U()
t_with, t_fixed = U(), U()
OPTS_VAR = {"Type": "Variable", "VariableName": "خيارات السؤال"}
all_id, split_id, choice_id = U(), U(), U()
acts += [
    A("is.workflow.actions.conditional", GroupingIdentifier=g_opts, WFControlFlowMode=0, WFCondition=100,
      WFInput={"Type": "Variable", "Variable": att(opts)}),
    A("is.workflow.actions.gettext", UUID=t_with, WFTextActionText=ts(OBJ + "|" + FIXED, [opts])),
    A("is.workflow.actions.setvariable", WFVariableName="خيارات السؤال", WFInput=att(out(t_with, "Text"))),
    A("is.workflow.actions.conditional", GroupingIdentifier=g_opts, WFControlFlowMode=1),
    A("is.workflow.actions.gettext", UUID=t_fixed, WFTextActionText=ts(FIXED)),
    A("is.workflow.actions.setvariable", WFVariableName="خيارات السؤال", WFInput=att(out(t_fixed, "Text"))),
    A("is.workflow.actions.conditional", GroupingIdentifier=g_opts, WFControlFlowMode=2),
    A("is.workflow.actions.gettext", UUID=all_id, WFTextActionText=ts(OBJ, [OPTS_VAR])),
    A("is.workflow.actions.text.split", UUID=split_id, WFTextSeparator="Custom", WFTextCustomSeparator="|",
      text=att(out(all_id, "Text"))),
    A("is.workflow.actions.choosefromlist", UUID=choice_id, WFInput=att(out(split_id, "Split Text")),
      WFChooseFromListActionPrompt=ts(OBJ, [qtext])),
]
choice = out(choice_id, "Chosen Item")

g_voice, g_skip = U(), U()
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_voice, WFControlFlowMode=0, WFCondition=99,
              WFConditionalActionString="أجيب بصوتي", WFInput={"Type": "Variable", "Variable": att(choice)}))
# ── الجواب بالصوت: تسجيلٌ حتّى النقر، يُحفظ ويُفرَّغ على الماك كغيره ──
rec_id, date_id, save_id = U(), U(), U()
acts += [
    A("is.workflow.actions.recordaudio", UUID=rec_id, WFRecordingStart="Immediately", WFRecordingEnd="On Tap",
      WFRecordingCompression="Normal"),
    A("is.workflow.actions.format.date", UUID=date_id, WFDateFormatStyle="Custom", WFDateFormat="yyyy-MM-dd_HH-mm-ss",
      WFDate=ts(OBJ, [{"Type": "CurrentDate"}])),
    A("is.workflow.actions.documentpicker.save", UUID=save_id, WFAskWhereToSave=False, WFSaveFileOverwrite=False,
      WFInput=att(out(rec_id, "Recorded Audio")),
      WFFileDestinationPath=ts(FOLDER + "جواب_" + OBJ + ".m4a", [out(date_id, "Formatted Date")])),
]
post(acts, key_id, "https://api.notion.com/v1/pages",
     inbox_body("تسجيل صوتي ينتظر التفريغ: جواب_" + OBJ + ".m4a", "جواب عن السؤال " + OBJ + ": " + OBJ),
     [out(date_id, "Formatted Date"), qid, qtext])
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_voice, WFControlFlowMode=1))
# ── الجواب كتابةً ──
g_write, ask_id = U(), U()
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_write, WFControlFlowMode=0, WFCondition=99,
              WFConditionalActionString="أكتب جوابي", WFInput={"Type": "Variable", "Variable": att(choice)}))
acts.append(A("is.workflow.actions.ask", UUID=ask_id, WFInputType="Text", WFAskActionPrompt=ts(OBJ, [qtext])))
post(acts, key_id, "https://api.notion.com/v1/pages",
     inbox_body("جواب: " + OBJ, "جواب عن السؤال " + OBJ + ": " + OBJ), [out(ask_id, "Provided Input"), qid, qtext])
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_write, WFControlFlowMode=1))
# ── لاحقًا: تخطٍّ إلى السؤال التالي، ولا يُكتب شيء ──
g_later, g_stop = U(), U()
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_later, WFControlFlowMode=0, WFCondition=99,
              WFConditionalActionString="لاحقًا", WFInput={"Type": "Variable", "Variable": att(choice)}))
# («لاحقًا» يتخطّى السؤال إلى التالي ويبقيه معروضًا، فلا تأجيل ولا تاريخ.)
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_later, WFControlFlowMode=1))
# ── أكتفي الآن: ينتهي الاختصار، وتبقى الأسئلة للمرّة القادمة ──
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_stop, WFControlFlowMode=0, WFCondition=99,
              WFConditionalActionString="أكتفي", WFInput={"Type": "Variable", "Variable": att(choice)}))
acts.append(A("is.workflow.actions.notification", UUID=U(),
              WFNotificationActionBody="حسنًا. تبقى الأسئلة الباقية للمرّة القادمة.", WFNotificationActionSound=False))
acts.append(A("is.workflow.actions.exit", UUID=U()))
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_stop, WFControlFlowMode=1))
# ── الجواب باختيار ──
post(acts, key_id, "https://api.notion.com/v1/pages",
     inbox_body("جواب: " + OBJ, "جواب عن السؤال " + OBJ + ": " + OBJ), [choice, qid, qtext])
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_stop, WFControlFlowMode=2))
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_later, WFControlFlowMode=2))
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_write, WFControlFlowMode=2))
acts.append(A("is.workflow.actions.conditional", GroupingIdentifier=g_voice, WFControlFlowMode=2))
acts.append(A("is.workflow.actions.repeat.each", GroupingIdentifier=loop, WFControlFlowMode=2))

acts.append(A("is.workflow.actions.notification", UUID=U(),
              WFNotificationActionBody="انتهت الأسئلة. يطبّق الوكيل أجوبتك خلال دقائق، وما تخطّيته يبقى للمرّة القادمة.",
              WFNotificationActionSound=False))

wf = {
    "WFWorkflowActions": acts,
    "WFWorkflowClientVersion": "2607.0.2",
    "WFWorkflowMinimumClientVersion": 900,
    "WFWorkflowMinimumClientVersionString": "900",
    "WFWorkflowIcon": {"WFWorkflowIconStartColor": 1440408063, "WFWorkflowIconGlyphNumber": 59703},
    "WFWorkflowImportQuestions": [],
    "WFWorkflowInputContentItemClasses": [],
    "WFWorkflowOutputContentItemClasses": [],
    "WFWorkflowTypes": ["WatchKit"],
    "WFWorkflowHasShortcutInputVariables": False,
}
with open(sys.argv[1], "wb") as f:
    plistlib.dump(wf, f, fmt=plistlib.FMT_BINARY)
