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
// والسكربتات الطابعة (config.py ← osa) تمرّر --list و--keep و--pages تلقائيًّا.
ObjC.import('Foundation');
let LIST = 'المذكّر';  // ويُبدَّل بـ --list=<الاسم>
let KEEP = [];         // بادئات خارجيّة لا يحذفها sync: --keep=أ:,ب:
const REF = 'مرجع: ';

// العنوان قصيرٌ ليُقرأ كاملًا في الويدجت: النافذة رمز، والدور في الملاحظة لا في العنوان.
const WIN = { 'بعد الفجر': '🌅', 'بعد الظهر': '☀️', 'بعد العصر': '🌇', 'بعد العشاء': '🌙', 'بين العشاءين': '🕌', 'عاجل': '❗', 'سؤال': '❓' };
function nameOf(it) { const w = it.window ? (WIN[it.window] || it.window) + ' ' : ''; return w + it.title; }
// الملاحظة سطرٌ مفيد أو لا شيء: لا دور ولا «مرجع:» فيها. والمرجع (مفتاح البند في Notion) يُحفظ في جدولٍ عند الماك
// (<state>/remkeys.json: معرّف التذكير ← المفتاح)، وما بقي فيه سطر «مرجع:» من قبل يُقرأ منه مرّةً ويُنقل إلى الجدول.
// ومسار الحالة من MUD_STATE (يمرّره config.py ← osa).
function bodyOf(it) { return it.notes ? String(it.notes).trim() : ''; }
const ENV = $.NSProcessInfo.processInfo.environment;
const STATE_DIR = ENV.objectForKey('MUD_STATE').isNil() ? $('~/.smart-mudhakkir').stringByExpandingTildeInPath.js : ENV.objectForKey('MUD_STATE').js;
const MAPFILE = STATE_DIR + '/remkeys.json';
let MAP = null;
function loadMap() { if (MAP) return MAP; try { MAP = JSON.parse($.NSString.stringWithContentsOfFileEncodingError(MAPFILE, $.NSUTF8StringEncoding, null).js) || {}; } catch (e) { MAP = {}; } return MAP; }
function saveMap() { if (!MAP) return; $.NSFileManager.defaultManager.createDirectoryAtPathWithIntermediateDirectoriesAttributesError(STATE_DIR, true, $(), null); $(JSON.stringify(MAP)).writeToFileAtomicallyEncodingError(MAPFILE, true, $.NSUTF8StringEncoding, null); }
function keyOf(id, body) { const m = loadMap(); if (m[id]) return m[id]; const k = refOf(body); if (k) m[id] = k; return k; }
function pushItem(app, list, props, key) { const r = app.Reminder(props); list.reminders.push(r); loadMap()[r.id()] = String(key); return r; }

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

// صفحات اليوم: الويدجت لا يتّسع إلّا لنحو اثني عشر بندًا، فتُوزَّع أمور اليوم على القائمة ثمّ «… ٢» ثمّ «… ٣»
// بترتيب أوقات الصلاة. ولا ينتقل بندٌ قائم بين الصفحات (النقل حذفٌ وإعادة إنشاء: يومض في الويدجت، وكان بطيئًا جدًّا)،
// والجديد يدخل أوّل صفحةٍ فيها متّسع. يُفعَّل بـ --pages=N (config.json ← apple.pages)، وread وsync يجمعان الصفحات.
let PAGES = null;
let CAP = 12;
const AR_DIGITS = '٠١٢٣٤٥٦٧٨٩';
const RANK = { 'عاجل': 0, 'بعد الفجر': 1, 'بعد الظهر': 2, 'بعد العصر': 3, 'بين العشاءين': 4, 'بعد العشاء': 5 };
function rankOf(it) {
  if (it.window in RANK) return RANK[it.window];
  if (it.time) { const h = new Date(it.time).getHours() + new Date(it.time).getMinutes() / 60; return h < 12 ? 1 : h < 15 ? 2 : h < 17.5 ? 3 : h < 19.5 ? 4 : 5; }
  return 3;
}

function pagedRun(app, cmd, argv) {
  const lists = PAGES.map(n => { const f = app.lists.whose({ name: n }); if (f.length > 0) return f[0]; app.lists.push(app.List({ name: n })); return app.lists.whose({ name: n })[0]; });
  const all = [];
  lists.forEach((l, li) => {
    const ids = l.reminders.id(), names = l.reminders.name(), bodies = l.reminders.body(), dones = l.reminders.completed();
    let dates, alarms;
    try { dates = l.reminders.completionDate(); } catch (e) { dates = ids.map(() => null); }
    try { alarms = l.reminders.remindMeDate(); } catch (e) { alarms = ids.map(() => null); }
    ids.forEach((id, i) => all.push({ li: li, id: id, name: names[i], body: bodies[i] || '', key: keyOf(id, bodies[i]), done: dones[i], date: dates[i] ? new Date(dates[i]) : null, alarm: alarms[i] }));
  });
  if (cmd === 'read') {
    return JSON.stringify(all.map(x => ({ key: x.key, title: x.name, completed: x.done,
      completionDate: x.done && x.date ? x.date.toISOString() : null, page: x.li + 1 })), null, 1);
  }
  const data = JSON.parse(readFile(argv[1]));
  const now = new Date(); const today = new Date(); today.setHours(0, 0, 0, 0);
  const keep = k => k.startsWith('أسئلة:') || k.startsWith('سؤال:') || KEEP.some(p => k.startsWith(p));
  const doneToday = new Set(all.filter(x => x.done && x.key && x.date && x.date >= today).map(x => x.key));
  const items = data.items.map((it, i) => Object.assign({ _i: i }, it)).filter(it => !keep(String(it.key)))
    .sort((a, b) => rankOf(a) - rankOf(b) || a._i - b._i);
  const want = new Set(items.map(it => String(it.key)));
  let added = 0, updated = 0, removed = 0, kept = 0, moved = 0;
  const byId = (li, id) => lists[li].reminders.byId(id);  // البحث داخل القائمة أسرع كثيرًا من البحث في التطبيق كلّه
  // ما لم يعد في القائمة يُحذف
  all.forEach(x => {
    if (x.done || !x.key || keep(x.key) || want.has(x.key)) return;
    try { app.delete(byId(x.li, x.id)); removed++; } catch (e) {} x.gone = true;
  });
  const open = {}; const fixed = PAGES.map(() => 0);
  all.forEach(x => { if (x.done || x.gone) return; if (x.key && !keep(x.key)) open[x.key] = x; else fixed[x.li]++; });
  // الصفحة المستهدفة لكلّ بند: بالترتيب، اثنا عشر في كلّ صفحة (مع ما فيها من بنودٍ ليست للوكيل كبند الأسئلة)
  const load = fixed.slice();
  const target = {};
  items.forEach(it => { const k = String(it.key); if (doneToday.has(k)) return;
    let li = load.findIndex(n => n < CAP); if (li < 0) li = PAGES.length - 1; target[k] = li; load[li]++; });
  items.forEach(it => {
    const k = String(it.key);
    if (!(k in target)) return;
    const name = nameOf(it), body = bodyOf(it); let cur = open[k];
    // في النهار لا يُنقل بندٌ قائم؛ وفي إعادة التوزيع يُنقل ما كانت صفحته غير صفحته وحده
    // لا يُنقل بندٌ قائم أبدًا (١٨ نوفمبر ٢٠٢٦): نقل البنود صباحًا تجاوز ساعةً في «التذكيرات» فتعطّلت المزامنة. والجديد يُوضع في صفحته بالترتيب.
    if (cur) {
      let ch = false; const r = byId(cur.li, cur.id);
      if (cur.name !== name) { r.name = name; ch = true; }
      if (cur.body !== body) { r.body = body; ch = true; }
      if (it.time) { const t = new Date(it.time); if (t > now && (!cur.alarm || new Date(cur.alarm).getTime() !== t.getTime())) { r.dueDate = t; r.remindMeDate = t; ch = true; } }
      ch ? updated++ : kept++;
      return;
    }
    const li = (() => { const cnt = PAGES.map((_, i) => fixed[i] + Object.values(open).filter(o => o.li === i).length); const j = cnt.findIndex(n => n < CAP); return j < 0 ? PAGES.length - 1 : j; })();
    const props = { name: name, body: body };
    if (it.time && new Date(it.time) > now) { props.dueDate = new Date(it.time); props.remindMeDate = new Date(it.time); }
    else props.alldayDueDate = today;
    pushItem(app, lists[li], props, k); added++;
    open[k] = { li: li };
  });
  const pages = PAGES.map((_, i) => fixed[i] + Object.values(open).filter(o => o.li === i).length);
  return JSON.stringify({ removed: removed, added: added, moved: moved, updated: updated, kept: kept, pages: pages });
}

function run(argv) { try { return runInner(argv); } finally { saveMap(); } }

function runInner(argv) {
  argv = argv.map(String);
  const li = argv.findIndex(a => a.startsWith('--list='));
  if (li >= 0) { LIST = argv[li].slice(7); }
  const ki = argv.findIndex(a => a.startsWith('--keep='));
  if (ki >= 0) { KEEP = argv[ki].slice(7).split(',').filter(s => s); }
  const pi = argv.findIndex(a => a.startsWith('--pages='));
  const ci = argv.findIndex(a => a.startsWith('--cap='));
  if (ci >= 0) CAP = parseInt(argv[ci].slice(6)) || 12;
  if (pi >= 0) { const n = parseInt(argv[pi].slice(8)) || 1; if (n > 1) PAGES = Array.from({ length: n }, (_, i) => i ? LIST + ' ' + String(i + 1).replace(/\d/g, d => AR_DIGITS[d]) : LIST); }
  argv = argv.filter(a => !a.startsWith('--list=') && !a.startsWith('--keep=') && !a.startsWith('--pages=') && !a.startsWith('--cap='));
  const app = Application('Reminders');
  const list = getList(app);
  const cmd = argv[0];
  if (PAGES && (cmd === 'read' || cmd === 'sync')) return pagedRun(app, cmd, argv);

  if (cmd === 'read') {
    // قراءةٌ دفعةً واحدة لكلّ خاصّيّة: سؤال التطبيق عن كلّ بندٍ على حدة كان يعلق
    const ids = list.reminders.id();
    const names = list.reminders.name();
    const bodies = list.reminders.body();
    const dones = list.reminders.completed();
    let dates;
    try { dates = list.reminders.completionDate(); } catch (e) { dates = names.map(() => null); }
    const out = names.map((n, i) => ({
      key: keyOf(ids[i], bodies[i]),
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
    return ids.map((id, i) => ({ id: id, key: keyOf(id, bodies[i]), done: dones[i], date: dates[i] ? new Date(dates[i]) : null }));
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
      pushItem(app, list, props, it.key);
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
      // لا يُمسّ البند إلّا بما تغيّر، ولا يُعاد ضبط تنبيهه إلّا إلى وقتٍ جديدٍ في المستقبل:
      // إعادة ضبطه في كلّ جولة (ومنه «بعد دقيقة» لموعدٍ قريب) كانت تُرنّه مرّةً كلّ عشر دقائق.
      const now = new Date();
      if (same.length) {
        const r = byId(same[0].id);
        let ch = false;
        if (r.name() !== name) { r.name = name; ch = true; }
        if ((r.body() || '') !== body) { r.body = body; ch = true; }
        if (it.time) {
          const t = new Date(it.time); let old = null; try { old = r.remindMeDate(); } catch (e) {}
          if (t > now && (!old || new Date(old).getTime() !== t.getTime())) { r.dueDate = t; r.remindMeDate = t; ch = true; }
        }
        if (ch) updated++; else skipped++;
      } else {
        const props = { name: name, body: body };
        if (it.time && new Date(it.time) > now) { props.dueDate = new Date(it.time); props.remindMeDate = new Date(it.time); }
        else if (it.time && now - new Date(it.time) < 30 * 60000) { const t = new Date(now.getTime() + 60000); props.dueDate = t; props.remindMeDate = t; }
        else props.alldayDueDate = today;
        pushItem(app, list, props, it.key);
        added++;
      }
    });
    return JSON.stringify({ added: added, updated: updated, unchanged_or_done: skipped });
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
