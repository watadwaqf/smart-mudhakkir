"""يبني اختصار «قيّد بالصوت»: يسجّل الصوت حتّى تنقر، ويحفظه في iCloud Drive، ويكتب في «الوارد» سطرًا ينتظر التفريغ.
الاستعمال: python3 -I build_voice.py out.shortcut  ثمّ  shortcuts sign --mode people-who-know-me --input out.shortcut --output «قيّد بالصوت».shortcut
معرّف «الوارد» واسم اختصار المفتاح ومجلّد التسجيلات من config.json.
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
KEY_ID = SC.get("key_shortcut_id") or ""
KEY_NAME = SC["key_shortcut_name"]
FOLDER = SC["recordings_folder"]


def key_workflow():
    """مرجع اختصار «مفتاح المذكّر» (يعيد مفتاح Notion). المعرّف اختياريّ: إن لم يُضبط في الإعدادات
    (shortcuts.key_shortcut_id) يُشار إليه باسمه وحده."""
    w = {"workflowName": KEY_NAME, "isSelf": False}
    if KEY_ID:
        w["workflowIdentifier"] = KEY_ID
    return w


def new_uuid():
    return str(uuid.uuid4()).upper()


def output_ref(action_uuid, name):
    return {"OutputUUID": action_uuid, "Type": "ActionOutput", "OutputName": name}


def attachment(ref):
    return {"Value": ref, "WFSerializationType": "WFTextTokenAttachment"}


def token_string(template, refs=()):
    ranges, pos, it = {}, 0, iter(refs)
    for ch in template:
        if ch == OBJ:
            ranges["{%d, 1}" % pos] = next(it)
        pos += len(ch.encode("utf-16-le")) // 2
    return {"Value": {"string": template, "attachmentsByRange": ranges},
            "WFSerializationType": "WFTextTokenString"}


def action(identifier, **params):
    return {"WFWorkflowActionIdentifier": identifier, "WFWorkflowActionParameters": params}


key_id, rec_id, date_id, save_id = new_uuid(), new_uuid(), new_uuid(), new_uuid()
body_id, url_id, val_id, group = new_uuid(), new_uuid(), new_uuid(), new_uuid()
stamp = output_ref(date_id, "Formatted Date")

body = ('{"parent":{"database_id":"%s"},"properties":{"النص":{"title":[{"text":{"content":"تسجيل صوتي ينتظر التفريغ: %s.m4a"}}]},'
        '"المصدر":{"select":{"name":"زر الإجراءات"}},"الحال":{"select":{"name":"جديد"}}}}') % (INBOX_DB, OBJ)

actions = [
    action("is.workflow.actions.recordaudio", UUID=rec_id,
           WFRecordingStart="Immediately", WFRecordingEnd="On Tap", WFRecordingCompression="Normal"),
    action("is.workflow.actions.format.date", UUID=date_id, WFDateFormatStyle="Custom",
           WFDateFormat="yyyy-MM-dd_HH-mm-ss", WFDate=token_string(OBJ, [{"Type": "CurrentDate"}])),
    action("is.workflow.actions.documentpicker.save", UUID=save_id, WFAskWhereToSave=False,
           WFSaveFileOverwrite=False, WFInput=attachment(output_ref(rec_id, "Recorded Audio")),
           WFFileDestinationPath=token_string(FOLDER + OBJ + ".m4a", [stamp])),
    action("is.workflow.actions.runworkflow", UUID=key_id, WFShowWorkflow=False, WFWorkflowName=KEY_NAME,
           WFWorkflow=key_workflow()),
    action("is.workflow.actions.gettext", UUID=body_id, WFTextActionText=token_string(body, [stamp])),
    action("is.workflow.actions.downloadurl", UUID=url_id, WFURL="https://api.notion.com/v1/pages",
           WFHTTPMethod="POST", ShowHeaders=True,
           WFHTTPHeaders={"Value": {"WFDictionaryFieldValueItems": [
               {"WFItemType": 0, "WFKey": token_string("Authorization"),
                "WFValue": token_string("Bearer " + OBJ, [output_ref(key_id, "Shortcut Result")])},
               {"WFItemType": 0, "WFKey": token_string("Notion-Version"), "WFValue": token_string("2022-06-28")},
               {"WFItemType": 0, "WFKey": token_string("Content-Type"), "WFValue": token_string("application/json")},
           ]}, "WFSerializationType": "WFDictionaryFieldValue"},
           WFHTTPBodyType="File", WFRequestVariable=attachment(output_ref(body_id, "Text"))),
    action("is.workflow.actions.getvalueforkey", UUID=val_id, WFDictionaryKey="id",
           WFInput=attachment(output_ref(url_id, "Contents of URL"))),
    action("is.workflow.actions.conditional", GroupingIdentifier=group, WFControlFlowMode=0, WFCondition=100,
           WFInput={"Type": "Variable", "Variable": attachment(output_ref(val_id, "Dictionary Value"))}),
    action("is.workflow.actions.notification", UUID=new_uuid(), WFNotificationActionBody="قُيِّد التسجيل",
           WFNotificationActionSound=True),
    action("is.workflow.actions.conditional", GroupingIdentifier=group, WFControlFlowMode=1),
    action("is.workflow.actions.notification", UUID=new_uuid(),
           WFNotificationActionBody="حُفظ التسجيل، ولم يصل إلى الوارد. سيجده الوكيل في مجلّد التسجيلات.",
           WFNotificationActionSound=True),
    action("is.workflow.actions.conditional", GroupingIdentifier=group, WFControlFlowMode=2),
]

wf = {
    "WFWorkflowActions": actions,
    "WFWorkflowClientVersion": "2607.0.2",
    "WFWorkflowMinimumClientVersion": 900,
    "WFWorkflowMinimumClientVersionString": "900",
    "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4282601983, "WFWorkflowIconGlyphNumber": 59511},
    "WFWorkflowImportQuestions": [],
    "WFWorkflowInputContentItemClasses": [],
    "WFWorkflowOutputContentItemClasses": [],
    "WFWorkflowTypes": ["WatchKit"],
    "WFWorkflowHasShortcutInputVariables": False,
}

with open(sys.argv[1], "wb") as f:
    plistlib.dump(wf, f, fmt=plistlib.FMT_BINARY)
