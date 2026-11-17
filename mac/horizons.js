// قوائم الآفاق في «التذكيرات»: لكلّ أفقٍ قائمته، تُستبدل بنودها كلّها كلّ يوم بترتيبها.
// بنودها بلا تاريخٍ ولا تنبيه (للنظر في الويدجت فقط)، والتاريخ في أوّل العنوان.
// الاستعمال: osascript -l JavaScript horizons.js replace <ملفّ JSON>
//   الملفّ: {"lists":[{"name":"🔭 الأسبوع","items":[{"title":"…","notes":"…"}]}]}
ObjC.import('Foundation');
function readFile(p) { return $.NSString.stringWithContentsOfFileEncodingError(p, $.NSUTF8StringEncoding, null).js; }
function run(argv) {
  const app = Application('Reminders');
  const data = JSON.parse(readFile(argv[1]));
  const out = [];
  data.lists.forEach(L => {
    let found = app.lists.whose({ name: L.name });
    let list;
    if (found.length > 0) list = found[0];
    else { app.lists.push(app.List({ name: L.name })); list = app.lists.whose({ name: L.name })[0]; }
    // حذفٌ جماعيّ بأمرٍ واحد: الحذف بندًا بندًا بطيءٌ جدًّا في «التذكيرات» (تجاوز خمس دقائق)
    try { if (list.reminders.length > 0) app.delete(list.reminders); } catch (e) {}
    L.items.forEach(it => list.reminders.push(app.Reminder({ name: it.title, body: it.notes || '' })));
    out.push(L.name + ':' + L.items.length);
  });
  return out.join(' ');
}
