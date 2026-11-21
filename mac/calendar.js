// تقويم «المذكّر» في تطبيق «التقويم»: نسخةُ عرضٍ للمواعيد والدروس والسكن. الأصل في Notion.
// الاستعمال: osascript -l JavaScript calendar.js sync /path/events.json [اسم التقويم]
// الملف: {"from":"YYYY-MM-DD","to":"YYYY-MM-DD","events":[{"key","title","start","end","allday","notes"}]}
// لا يمسّ إلّا الأحداث التي فيها سطر «مرجع: …» داخل المدى. وما أضافه صاحب النظام بيده لا يُمسّ.
ObjC.import('Foundation');
const CAL = 'المذكّر';
const REF = 'مرجع: ';

function readFile(p) { return $.NSString.stringWithContentsOfFileEncodingError(p, $.NSUTF8StringEncoding, null).js; }
function refOf(desc) {
  if (!desc) return null;
  const line = desc.split('\n').find(s => s.startsWith(REF));
  return line ? line.slice(REF.length).trim() : null;
}

function run(argv) {
  if (argv[0] !== 'sync') return 'الأمر: sync <ملف>';
  const app = Application('Calendar');
  // الوسيط الثالث اختياريّ: اسم التقويم (من config.json ← apple.calendar_name)، أو تقويمٌ آخر يُملأ بالطريقة نفسها.
  // ويُنشئه صاحب النظام في iCloud بيده.
  const NAME = argv[2] || CAL;
  let found = app.calendars.whose({ name: NAME })();
  // لا يُنشأ هنا: ما يُنشئه السكربت يكون «على الماك» فلا يُشارَك، فينشئه صاحب النظام في iCloud بيده.
  // وإن وُجد تقويمان بالاسم نفسه أُخذ الذي في iCloud (له وصف)، وإلّا الأخير.
  if (found.length > 1) found = [found[found.length - 1]];
  if (!found.length) return 'NO-CALENDAR';
  const cal = found[0];
  const data = JSON.parse(readFile(argv[1]));
  const from = new Date(data.from + 'T00:00:00');
  const to = new Date(data.to + 'T23:59:59');

  // أحداث الوكيل القائمة في المدى (ومعها ما قبله بيوم، لأنّ أحداث اليوم الكامل تبدأ منتصف الليل)
  const lo = new Date(from.getTime() - 864e5);
  const existing = {};
  cal.events.whose({ _and: [{ startDate: { _greaterThan: lo } }, { startDate: { _lessThan: to } }] })().forEach(ev => {
    const k = refOf(ev.description());
    if (!k) return;
    if (existing[k]) { app.delete(ev); return; } // نسخةٌ مكرّرة
    existing[k] = ev;
  });

  let added = 0, updated = 0, removed = 0, kept = 0;
  const want = new Set();
  data.events.forEach(e => {
    want.add(e.key);
    const start = new Date(e.start);
    // حدث اليوم الكامل: «التقويم» يعدّ يوم النهاية داخلًا فيه، فتُجعل النهاية يوم البداية نفسه
    const end = e.allday ? new Date(e.start) : new Date(e.end);
    const desc = (e.notes ? e.notes + '\n\n' : '') + REF + e.key;
    const ev = existing[e.key];
    if (ev) {
      const sameTime = e.allday ? (ev.alldayEvent() && ev.startDate().getTime() === start.getTime() &&
                                   ev.endDate().getTime() - start.getTime() < 864e5)
                                : (!ev.alldayEvent() && ev.startDate().getTime() === start.getTime() && ev.endDate().getTime() === end.getTime());
      const same = sameTime && ev.summary() === e.title && ev.description() === desc;
      if (same) { kept++; return; }
      ev.summary = e.title; ev.alldayEvent = !!e.allday;
      // نقل الحدث إلى ما بعد نهايته القديمة: تُضبط النهاية أوّلًا، وإلّا رفض «التقويم» بدايةً بعد النهاية فتعطّلت المزامنة كلّها (٢١ نوفمبر ٢٠٢٦)
      if (start.getTime() >= ev.endDate().getTime()) { ev.endDate = end; ev.startDate = start; } else { ev.startDate = start; ev.endDate = end; }
      ev.description = desc;
      updated++;
    } else {
      cal.events.push(app.Event({ summary: e.title, startDate: start, endDate: end, alldayEvent: !!e.allday, description: desc }));
      added++;
    }
  });
  Object.keys(existing).forEach(k => {
    const ev = existing[k];
    const s = ev.startDate();
    if (!want.has(k) && s >= lo && s <= to) { app.delete(ev); removed++; }
  });
  return JSON.stringify({ added, updated, removed, kept });
}
