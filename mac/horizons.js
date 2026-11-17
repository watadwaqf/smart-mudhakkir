// قوائم الآفاق في «التذكيرات»: لكلّ أفقٍ قائمته، تُستبدل بنودها كلّها كلّ يوم بترتيبها.
// بنودها بلا تاريخٍ ولا تنبيه (للنظر في الويدجت فقط)، والتاريخ في أوّل العنوان.
// الاستعمال: osascript -l JavaScript horizons.js replace|sync <ملفّ JSON>   (sync: تدريجيّ يحفظ معرّفات البنود)
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
    if (argv[0] === 'sync') {
      // تحديثٌ تدريجيّ: كان الحذف وإعادة الإنشاء في النهار يُبقي في ويدجت الجوّال بنودًا زالت،
      // فيومض التعليم عليها ولا يثبت. الآن يبقى البند بمعرّفه، ويُحدَّث اسمه، ويُضاف الجديد، ويُحذف الزائل وحده.
      // والمعلَّم لا يُمسّ (يحصده mac_horizons.py). والترتيب الكامل يُعاد بالاستبدال مرّةً كلّ ليلة.
      const keyOf = (n, b) => { const m = (b || '').split('مرجع: ')[1]; return m ? m.trim() : 'عنوان:' + n; };
      const ids = list.reminders.id(), names = list.reminders.name(), bodies = list.reminders.body(), done = list.reminders.completed();
      const cur = {};
      ids.forEach((id, i) => { cur[keyOf(names[i], bodies[i])] = { id: id, name: names[i], body: bodies[i] || '', done: done[i] }; });
      const want = new Set(); let add = 0, upd = 0, del = 0;
      L.items.forEach(it => {
        const k = keyOf(it.title, it.notes); want.add(k); const c = cur[k];
        if (!c) { list.reminders.push(app.Reminder({ name: it.title, body: it.notes || '' })); add++; return; }
        if (c.done) return;
        const r = app.reminders.byId(c.id);
        if (c.name !== it.title) { r.name = it.title; upd++; }
        if (c.body !== (it.notes || '')) { r.body = it.notes || ''; upd++; }
      });
      Object.keys(cur).forEach(k => { if (!want.has(k)) { try { app.delete(app.reminders.byId(cur[k].id)); del++; } catch (e) {} } });
      out.push(L.name + ':' + L.items.length + '(+' + add + ' ~' + upd + ' -' + del + ')');
      return;
    }
    // استبدالٌ كامل بترتيبه: حذفٌ جماعيّ بأمرٍ واحد (الحذف بندًا بندًا بطيءٌ جدًّا)
    try { if (list.reminders.length > 0) app.delete(list.reminders); } catch (e) {}
    L.items.forEach(it => list.reminders.push(app.Reminder({ name: it.title, body: it.notes || '' })));
    out.push(L.name + ':' + L.items.length);
  });
  return out.join(' ');
}
