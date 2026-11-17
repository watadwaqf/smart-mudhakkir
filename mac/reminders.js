// قناة عرض «المذكّر» في تطبيق التذكيرات. Notion هو الأصل، وهذه القائمة نسخةٌ للعرض والتعليم.
// الاستعمال:
//   osascript -l JavaScript reminders.js read                [--list=<اسم القائمة>]
//   osascript -l JavaScript reminders.js sync /path/items.json [--list=…] [--keep=بادئة1,بادئة2]
//   osascript -l JavaScript reminders.js upsert /path/items.json
//   osascript -l JavaScript reminders.js remove <مفتاح>
//   osascript -l JavaScript reminders.js prune <بادئة> <المفتاح الباقي>
// ملف sync: {"items":[{"key":"...","window":"بعد الظهر","title":"...","role":"العمل","notes":"...","time":"2026-01-07T12:30:00+03:00"}]}
// sync يزامن البنود التي أنشأها الوكيل (فيها سطر «مرجع:») مع بنود اليوم بترتيبها، تدريجيًّا.
// لا يمسّ البنود المعلَّمة، ولا البنود التي أضافها صاحب النظام بيده، ولا البنود التي يبدأ مفتاحها ببادئةٍ في --keep
// (بنودٌ تديرها أداةٌ خارجيّة؛ تُضبط في config.json ← external_prefixes).
// والسكربتات الطابعة (config.py ← osa) تمرّر --list و--keep تلقائيًّا.
ObjC.import('Foundation');
let LIST = 'المذكّر';  // ويُبدَّل بـ --list=<الاسم>
let KEEP = [];         // بادئات خارجيّة لا يحذفها sync: --keep=أ:,ب:
const REF = 'مرجع: ';

// العنوان قصيرٌ ليُقرأ كاملًا في الويدجت: النافذة رمز، والدور في الملاحظة لا في العنوان.
const WIN = { 'بعد الفجر': '🌅', 'بعد الظهر': '☀️', 'بعد العصر': '🌇', 'بعد العشاء': '🌙', 'بين العشاءين': '🕌', 'عاجل': '❗', 'سؤال': '❓' };
function nameOf(it) { const w = it.window ? (WIN[it.window] || it.window) + ' ' : ''; return w + it.title; }
function bodyOf(it) { return (it.role ? it.role + (it.notes ? ' · ' : '') : '') + (it.notes ? it.notes : '') + ((it.role || it.notes) ? '\n\n' : '') + REF + it.key; }

function readFile(p) {
  return $.NSString.stringWithContentsOfFileEncodingError(p, $.NSUTF8StringEncoding, null).js;
}

function getList(app) {
  const found = app.lists.whose({ name: LIST });
  if (found.length > 0) return found[0];
  const l = app.List({ name: LIST });
  app.lists.push(l);
  return app.lists.whose({ name: LIST })[0];
}

function refOf(body) {
  if (!body) return null;
  const line = body.split('\n').find(s => s.startsWith(REF));
  return line ? line.slice(REF.length).trim() : null;
}

function run(argv) {
  argv = argv.map(String);
  const li = argv.findIndex(a => a.startsWith('--list='));
  if (li >= 0) { LIST = argv[li].slice(7); }
  const ki = argv.findIndex(a => a.startsWith('--keep='));
  if (ki >= 0) { KEEP = argv[ki].slice(7).split(',').filter(s => s); }
  argv = argv.filter(a => !a.startsWith('--list=') && !a.startsWith('--keep='));
  const app = Application('Reminders');
  const list = getList(app);
  const cmd = argv[0];

  if (cmd === 'read') {
    // قراءةٌ دفعةً واحدة لكلّ خاصّيّة: سؤال التطبيق عن كلّ بندٍ على حدة كان يعلق
    const names = list.reminders.name();
    const bodies = list.reminders.body();
    const dones = list.reminders.completed();
    let dates;
    try { dates = list.reminders.completionDate(); } catch (e) { dates = names.map(() => null); }
    const out = names.map((n, i) => ({
      key: refOf(bodies[i]),
      title: n,
      completed: dones[i],
      completionDate: dones[i] && dates[i] ? new Date(dates[i]).toISOString() : null,
    }));
    return JSON.stringify(out, null, 1);
  }

  // لقطةٌ دفعةً واحدة: المعرّفات والمفاتيح والعلامات وتواريخ الإنجاز. سؤال التطبيق عن كلّ بندٍ على حدة كان يعلق.
  function snapshot() {
    const ids = list.reminders.id();
    const bodies = list.reminders.body();
    const dones = list.reminders.completed();
    let dates;
    try { dates = list.reminders.completionDate(); } catch (e) { dates = ids.map(() => null); }
    return ids.map((id, i) => ({ id: id, key: refOf(bodies[i]), done: dones[i], date: dates[i] ? new Date(dates[i]) : null }));
  }
  const byId = id => app.reminders.byId(id);

  if (cmd === 'sync') {
    // مزامنةٌ تدريجيّة: كان الحذف وإعادة الإنشاء في كلّ تغييرٍ يُعيد تنبيه ما فات وقته فيرنّ في غير وقته ويتكرّر.
    // الآن: ما لم يتغيّر يبقى كما هو، وما تغيّر عنوانه أو ملاحظته يُحدَّث بلا مساس بتنبيهه، والجديد يُضاف، والزائل يُحذف.
    // والبند الجديد الذي فات وقته يُضاف بلا تنبيه (يومه فقط)، فلا يرنّ متأخّرًا.
    // والموقوت يُضاف بـ dueDate لا alldayDueDate: بند اليوم الكامل يرنّ على منتصف الليل.
    const data = JSON.parse(readFile(argv[1]));
    const snap = snapshot();
    // قراءةٌ دفعةً واحدة لكلّ خاصّيّة: سؤال التطبيق عن كلّ بندٍ على حدة يعلق
    const names = list.reminders.name();
    const bodies = list.reminders.body();
    let alarms; try { alarms = list.reminders.remindMeDate(); } catch (e) { alarms = names.map(() => null); }
    const now = new Date();
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const doneToday = new Set(snap.filter(x => x.done && x.key && x.date && x.date >= today).map(x => x.key));
    const open = {};
    snap.forEach((x, i) => { if (!x.done && x.key) open[x.key] = { id: x.id, name: names[i], body: bodies[i], alarm: alarms[i] }; });
    const want = new Set();
    let added = 0, updated = 0, removed = 0, kept = 0;
    data.items.forEach(it => {
      const k = String(it.key);
      if (k.startsWith('أسئلة:') || k.startsWith('سؤال:')) return; // الأسئلة بندٌ واحد يديره mac_calendar.py
      want.add(k);
      if (doneToday.has(k)) return;
      const name = nameOf(it), body = bodyOf(it);
      const cur = open[k];
      if (cur) {
        let ch = false;
        if (cur.name !== name) { byId(cur.id).name = name; ch = true; }
        if (cur.body !== body) { byId(cur.id).body = body; ch = true; }
        // وقتٌ جديد في المستقبل (كتغيير موعد) يُحدَّث؛ والماضي لا يُمسّ
        if (it.time) {
          const t = new Date(it.time);
          const old = cur.alarm;
          if (t > now && (!old || new Date(old).getTime() !== t.getTime())) { const r = byId(cur.id); r.dueDate = t; r.remindMeDate = t; ch = true; }
        }
        ch ? updated++ : kept++;
        return;
      }
      const props = { name: name, body: body };
      if (it.time && new Date(it.time) > now) { props.dueDate = new Date(it.time); props.remindMeDate = new Date(it.time); }
      else props.alldayDueDate = today;
      list.reminders.push(app.Reminder(props));
      added++;
    });
    // بند «أسئلة:…» يديره mac_calendar.py، وبنود البادئات الخارجيّة (--keep) تديرها أداتها، فلا تُحذف هنا
    Object.keys(open).forEach(k => {
      if (want.has(k) || k.startsWith('أسئلة:') || KEEP.some(p => k.startsWith(p))) return;
      try { app.delete(byId(open[k].id)); removed++; } catch (e) {}
    });
    return JSON.stringify({ removed: removed, added: added, updated: updated, kept: kept });
  }

  if (cmd === 'upsert') {
    // يضيف بنودًا أو يحدّثها بمفاتيحها، ولا يمسّ غيرها. البند المعلَّم لا يُعاد إنشاؤه.
    const data = JSON.parse(readFile(argv[1]));
    const snap = snapshot();
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    let added = 0, updated = 0, skipped = 0;
    data.items.forEach(it => {
      const name = nameOf(it);
      const body = bodyOf(it);
      const same = snap.filter(x => x.key === it.key);
      if (same.some(x => x.done)) { skipped++; return; }
      if (same.length) {
        const r = byId(same[0].id);
        r.name = name; r.body = body;
        if (it.time) { r.dueDate = new Date(it.time); r.remindMeDate = new Date(it.time); }
        updated++;
      } else {
        const props = { name: name, body: body };
        if (it.time) { props.dueDate = new Date(it.time); props.remindMeDate = new Date(it.time); }
        else props.alldayDueDate = today;
        list.reminders.push(app.Reminder(props));
        added++;
      }
    });
    return JSON.stringify({ added: added, updated: updated, skipped_completed: skipped });
  }

  if (cmd === 'remove') {
    // يحذف البنود غير المعلَّمة التي مفتاحها argv[1] (نسخ عرضٍ فقط؛ الأصل في Notion)
    let removed = 0;
    snapshot().filter(x => !x.done && x.key === argv[1]).forEach(x => { app.delete(byId(x.id)); removed++; });
    return JSON.stringify({ removed: removed });
  }

  if (cmd === 'prune') {
    // يحذف البنود غير المعلَّمة التي يبدأ مفتاحها بـ argv[1] إلّا argv[2] (كبنود «أسئلة:» للأيّام الماضية)
    let removed = 0;
    snapshot().filter(x => !x.done && x.key && x.key.startsWith(argv[1]) && x.key !== argv[2])
              .forEach(x => { app.delete(byId(x.id)); removed++; });
    return JSON.stringify({ removed: removed });
  }

  return 'أمرٌ غير معروف. الأوامر: read، sync <ملف>، upsert <ملف>، remove <مفتاح>، prune <بادئة> <المفتاح الباقي>';
}
