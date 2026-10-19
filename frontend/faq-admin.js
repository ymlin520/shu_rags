const $ = s => document.querySelector(s);
const ADMIN_TOKEN_KEY = 'school-faq-admin-token';
const OFFICE_TOKEN_KEY = 'school-faq-office-token';   // 與處室回覆清單共用，登入一次兩邊都能用
const PAGE_SIZE = 50;
const FIELDS = ['id', 'category', 'question', 'answer', 'url', 'keywords', 'office', 'email', 'owner'];
const SEARCH_FIELDS = [...FIELDS, 'updated_at', 'update_note'];
const byId = (a, b) => String(a.id).localeCompare(String(b.id), 'en', { numeric: true });
const text = v => String(v || '');
const SORTS = {
  recent: (a, b) => text(b.updated_at).localeCompare(text(a.updated_at)) || byId(a, b),
  oldest: (a, b) => (text(a.updated_at) || '9').localeCompare(text(b.updated_at) || '9') || byId(a, b),
  id: byId,
  idDesc: (a, b) => byId(b, a),
  category: (a, b) => text(a.category).localeCompare(text(b.category), 'zh-Hant') || byId(a, b),
  office: (a, b) => text(a.office).localeCompare(text(b.office), 'zh-Hant') || byId(a, b),
};
const MY_OFFICE_KEY = 'school-faq-editor-office';
// role：admin 管理密碼（全部功能）；editor 各處室共用的編輯密碼（可改、可轉移所有題目，不能匯入）；
//       office 處室專屬登入碼（只看得到本單位）。admin 與 editor 都放在 X-Admin-Token，由後端分辨。
let role = localStorage.getItem(ADMIN_TOKEN_KEY) ? 'admin' : 'office';
let myOffice = '';
try { myOffice = localStorage.getItem(MY_OFFICE_KEY) || '' } catch { }
let token = localStorage.getItem(role === 'admin' ? ADMIN_TOKEN_KEY : OFFICE_TOKEN_KEY) || '';
let faqs = [], summary = {}, scope = { offices: [], all_offices: [] }, preview = null, source = 'url', page = 1, editingId = null;
const picked = new Set();
const tokenKey = () => role === 'admin' ? ADMIN_TOKEN_KEY : OFFICE_TOKEN_KEY;
const isOffice = () => role === 'office';
const canImport = () => role === 'admin';
const official = name => scope.all_offices.includes(name);

const esc = v => { const n = document.createElement('div'); n.textContent = v ?? ''; return n.innerHTML };
const headers = () => (role === 'office' ? { 'X-Office-Token': token }
  : { 'X-Admin-Token': token, ...(myOffice ? { 'X-Editor-Office': encodeURIComponent(myOffice) } : {}) });
const jsonHeaders = () => ({ ...headers(), 'Content-Type': 'application/json' });
const msg = (el, text, ok) => { const n = $(el); n.textContent = text; n.className = text ? (ok ? 'ok' : 'err') : '' };
const cut = (v, n) => { const t = String(v || '').replace(/\s+/g, ' '); return t.length > n ? t.slice(0, n) + '…' : t };
async function detail(response) { const d = await response.json().catch(() => ({})); return d.detail || `操作失敗（${response.status}）` }

/* ----------------------------------------------------------------- 讀取與統計 */

async function load() {
  const response = await fetch('/api/admin/faqs', { headers: headers() });
  if (!response.ok) { const e = new Error(await detail(response)); e.status = response.status; throw e }
  const data = await response.json();
  faqs = data.faqs; summary = data.summary;
  // 舊版後端沒有 scope：當成管理者，正式單位清單先用現有主責單位代替（後端重啟後就會是正式清單）
  scope = data.scope || { role: 'admin', office: '', offices: [], all_offices: summary.offices.map(x => x.name) };
  if (role !== 'office') role = scope.role;   // 管理密碼或共用密碼，由後端回報
  for (const id of [...picked]) if (!faqs.some(x => x.id === id)) picked.delete(id);
  renderRole(); renderSummary(); renderFilters(); renderOfficeBoard(); renderList();
}

function renderRole() {
  document.body.classList.toggle('office-mode', !canImport());
  $('#my-office-box').hidden = role !== 'editor';
  if (role === 'editor') {
    $('#my-office').innerHTML = '<option value="">請選擇…</option>' + scope.all_offices.map(v => `<option>${esc(v)}</option>`).join('');
    $('#my-office').value = scope.all_offices.includes(myOffice) ? myOffice : '';
  }
  $('#intro').innerHTML = isOffice()
    ? `<span class="who">目前登入：${esc(scope.office)}</span><br>只看得到、改得到本單位的常見問題；不屬於本單位的題目可以勾選後「轉移」給正確的單位。`
    : role === 'editor'
      ? '各處室共用的編輯帳號：可以修改所有常見問題，也可以把不屬於自己的題目勾選後「轉移」給正確的單位。修改紀錄會記下您選的單位。'
      : '匯入試算表、逐筆編輯 FAQ；存檔後前台分類與 AI 回答會立即使用新資料。';
  $('#back-link').hidden = role === 'editor';
  $('#back-link').href = isOffice() ? '/office' : '/admin';
  $('#back-link').textContent = isOffice() ? '處室回覆清單' : '詢問單後台';
  const mine = new Set(scope.offices);
  const targets = scope.all_offices.filter(x => !(isOffice() && mine.size === 1 && mine.has(x)));
  const current = $('#transfer-to').value;
  $('#transfer-to').innerHTML = '<option value="">選擇單位…</option>' + targets.map(v => `<option>${esc(v)}</option>`).join('');
  $('#transfer-to').value = targets.includes(current) ? current : '';
}

function renderSummary() {
  $('#stats').className = 'stats stats-4';
  $('#stats').innerHTML = `<article><span>常見問題總數</span><strong>${summary.total.toLocaleString()}</strong><small>已建立向量，前台可搜尋</small></article>
<article><span>分類數</span><strong>${summary.categories.length}</strong><small>${esc(summary.categories.slice(0, 2).map(x => `${x.name}（${x.total}）`).join('、')) || '尚未分類'}</small></article>
<article><span>主責單位</span><strong>${summary.offices.length}</strong><small>${esc(summary.offices.slice(0, 2).map(x => `${x.name}（${x.total}）`).join('、')) || '尚未填寫'}</small></article>
<article class="accent"><span>最後更新</span><strong style="font-size:20px">${esc(summary.updated_at || '—')}</strong><small>data/faq.csv（台灣時間）</small></article>`;
}

function fillOptions(select, values, keep) {
  const current = keep ? select.value : '';
  select.innerHTML = `<option value="">${select.dataset.all}</option>` + values.map(v => `<option>${esc(v)}</option>`).join('');
  select.value = values.includes(current) ? current : '';
}

function renderFilters() {
  const categories = summary.categories.map(x => x.name), offices = summary.offices.map(x => x.name);
  fillOptions($('#category-filter'), categories, true);
  fillOptions($('#office-filter'), offices, true);
  if (faqs.some(x => !officeOf(x))) $('#office-filter').insertAdjacentHTML('beforeend', `<option value="${NO_OFFICE}">未填主責單位</option>`);
  $('#category-list').innerHTML = categories.map(v => `<option value="${esc(v)}">`).join('');
  // 主責單位一律從正式單位挑；舊資料裡的非正式名稱只有管理者看得到，並標成「待轉移」
  $('#office-list').innerHTML = scope.all_offices.map(v => `<option value="${esc(v)}">`).join('');
  if (!isOffice() && faqs.some(isLegacy)) $('#office-filter').insertAdjacentHTML('beforeend', `<option value="${LEGACY}">待轉移（非正式單位名稱）</option>`);
  const owners = [...new Set(faqs.map(x => (x.owner || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-Hant'));
  $('#owner-list').innerHTML = owners.map(v => `<option value="${esc(v)}">`).join('');
}

/* ----------------------------------------------------------------- FAQ 清單 */

const NO_OFFICE = '__none__';   // 「未填主責單位」的篩選值
const LEGACY = '__legacy__';    // 「主責單位不是正式單位名稱」的篩選值（例如舊資料只寫「教務處」）
const officeOf = x => x.office || '';
const isLegacy = x => !!officeOf(x) && !official(officeOf(x));
const matchOffice = (x, office) => !office || (office === NO_OFFICE ? !officeOf(x) : office === LEGACY ? isLegacy(x) : officeOf(x) === office);

function filtered() {
  const keyword = $('#search').value.trim().toLowerCase();
  const category = $('#category-filter').value, office = $('#office-filter').value;
  return faqs.filter(x =>
    (!category || (x.category || '未分類') === category) && matchOffice(x, office) &&
    (!keyword || SEARCH_FIELDS.some(f => String(x[f] || '').toLowerCase().includes(keyword))));
}

/* --------------------------------------------------- 依主責單位瀏覽（處室選單） */

// 把單位歸到上層處室：先去掉「-」後面的窗口名，再抓到「處／室／中心／學院」為止
// 教務處-課程與選課 → 教務處；學務處生輔組 → 學務處；人事室 → 人事室；舍我紀念館 → 舍我紀念館
function groupOf(name) {
  const head = String(name).split('-')[0];
  const m = head.match(/^(.*?(?:處|室|中心|學院|電台))/);
  return m ? m[1] : head;
}

function renderOfficeBoard() {
  const counts = new Map();
  faqs.forEach(x => { const k = officeOf(x) || NO_OFFICE; counts.set(k, (counts.get(k) || 0) + 1) });
  const names = summary.offices.map(x => x.name).filter(n => n);
  for (const k of counts.keys()) if (k !== NO_OFFICE && !names.includes(k)) names.push(k);
  names.sort((a, b) => a.localeCompare(b, 'zh-Hant'));

  const groups = new Map();
  names.forEach(n => { const g = groupOf(n); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(n) });
  // 只有一個窗口的處室不另外開一區，統一收到最後的「其他單位」，免得標題比內容還多
  const solo = [];
  for (const [g, list] of [...groups]) if (list.length < 2) { solo.push(...list); groups.delete(g) }
  if (solo.length) groups.set('其他單位', solo.sort((a, b) => a.localeCompare(b, 'zh-Hant')));

  const current = $('#office-filter').value;
  const chip = (value, label, total) =>
    `<button type="button" class="office-chip${current === value ? ' active' : ''}" data-office="${esc(value)}">` +
    `<span>${esc(label)}</span><em>${total}</em></button>`;

  const legacy = faqs.filter(isLegacy).length;
  let html = `<div class="office-grid office-top">${chip('', isOffice() ? '本單位全部' : '全部單位', faqs.length)}` +
    (counts.get(NO_OFFICE) ? chip(NO_OFFICE, '未填主責單位', counts.get(NO_OFFICE)) : '') +
    (legacy && !isOffice() ? chip(LEGACY, '待轉移（非正式單位名稱）', legacy) : '') + '</div>';
  for (const [group, list] of groups) {
    const total = list.reduce((sum, n) => sum + (counts.get(n) || 0), 0);
    const label = n => (group === '其他單位' || n === group) ? n : n.replace(/^.*?-/, '') || n;
    html += `<div class="office-group"><h3>${esc(group)}<em>共 ${total} 題</em></h3><div class="office-grid">` +
      list.map(n => chip(n, label(n), counts.get(n) || 0)).join('') + '</div></div>';
  }
  $('#office-groups').innerHTML = html;

  const name = current === NO_OFFICE ? '未填主責單位' : current === LEGACY ? '待轉移（非正式單位名稱）' : current;
  $('#scope-bar').hidden = !current;
  $('#scope-name').textContent = name || '';
  $('#list-title').textContent = current ? `${name} 的常見問題` : '所有常見問題';
  $('#add').textContent = current && current !== NO_OFFICE && current !== LEGACY ? `＋ 在${name}新增一筆` : '＋ 新增一筆';
}

function pickOffice(value) {
  $('#office-filter').value = value;
  page = 1;
  renderOfficeBoard(); renderList();
}

function renderList() {
  const rows = filtered(), pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const sorter = SORTS[$('#sort').value]; if (sorter) rows.sort(sorter);
  page = Math.min(Math.max(1, page), pages);
  const slice = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  $('#count').textContent = rows.length === faqs.length ? `共 ${faqs.length} 筆` : `符合 ${rows.length} 筆／共 ${faqs.length} 筆`;
  $('#rows').innerHTML = slice.length ? slice.map(x => `<tr><td class="pick"><input type="checkbox" data-pick="${esc(x.id)}" ${picked.has(x.id) ? 'checked' : ''}></td><td class="id">${esc(x.id)}</td><td>${esc(x.category) || '<span class="muted">未分類</span>'}</td>
<td><span class="q">${esc(x.question)}</span><small class="a">${esc(cut(x.answer, 90))}</small></td><td><span class="${isLegacy(x) ? 'legacy-office' : ''}">${esc(x.office) || '—'}</span>${x.suggest ? `<small class="suggest">建議：${esc(x.suggest)}</small>` : ''}</td><td>${esc(x.owner) || '—'}</td>
<td class="when">${esc(x.updated_at) || '—'}</td><td class="note">${esc(x.update_note) || '—'}</td>
<td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">開啟 ↗</a>` : '—'}</td>
<td><button class="edit" data-edit="${esc(x.id)}" type="button">編輯 →</button></td></tr>`).join('')
    : '<tr><td colspan="10">沒有符合條件的常見問題</td></tr>';
  $('#pick-page').checked = slice.length > 0 && slice.every(x => picked.has(x.id));
  $('#page-info').textContent = `第 ${page} / ${pages} 頁`;
  renderTransferBar();
  $('#prev').disabled = page <= 1; $('#next').disabled = page >= pages;
}

/* ----------------------------------------------------------------- 匯入 */

async function runPreview() {
  const body = new FormData();
  if (source === 'file') {
    const file = $('#src-file').files[0];
    if (!file) return msg('#import-msg', '請先選擇檔案。', false);
    body.append('file', file);
  } else if (source === 'url') {
    if (!$('#src-url').value.trim()) return msg('#import-msg', '請先輸入試算表網址。', false);
    body.append('url', $('#src-url').value.trim());
  } else {
    if (!$('#src-text').value.trim()) return msg('#import-msg', '請先貼上資料。', false);
    body.append('text', $('#src-text').value);
  }
  $('#report').hidden = true;
  const button = $('#preview'); button.disabled = true; button.textContent = '讀取中…';
  msg('#import-msg', '正在讀取來源資料…', true);
  try {
    const response = await fetch('/api/admin/faqs/preview', { method: 'POST', headers: headers(), body });
    if (!response.ok) throw new Error(await detail(response));
    preview = await response.json();
    renderPreview();
    msg('#import-msg', `已讀取「${preview.source}」共 ${preview.rows.length} 列，確認下方內容後再按「確認匯入」。`, true);
  } catch (error) {
    preview = null; $('#preview-box').hidden = true;
    msg('#import-msg', error.message, false);
  } finally { button.disabled = false; button.textContent = '讀取並預覽' }
}

function renderPreview() {
  const { counts, rows, header, existing_total: existing } = preview;
  $('#preview-box').hidden = false;
  $('#counts').innerHTML = `<span class="create">新增 ${counts.create}</span><span class="update">更新既有 ${counts.update}${counts.same ? `（其中內容相同 ${counts.same}）` : ''}</span><span class="skip">略過 ${counts.skip}</span>` +
    (counts.similar ? `<span class="similar">相似提醒 ${counts.similar}</span>` : '') + (counts.warn ? `<span class="warn">編號衝突 ${counts.warn}</span>` : '') +
    `<span>目前知識庫 ${existing} 筆</span>`;
  $('#mapping').innerHTML = '對應到的欄位：' + FIELDS.filter(f => header[f]).map(f => `<code>${esc(header[f])}</code> → ${f}`).join('　') +
    (FIELDS.some(f => !header[f]) ? `　（未提供：${FIELDS.filter(f => !header[f]).join('、')}）` : '');
  $('#preview-rows').innerHTML = rows.map((x, index) => `<tr class="${x.action}${x.similar || x.warn ? ' flagged' : ''}">
<td class="pick">${x.action === 'skip' ? '' : `<input type="checkbox" data-row="${index}" ${x.warn ? '' : 'checked'}>`}</td><td>${x.row}</td>
<td class="id">${esc(x.id)}</td><td>${esc(cut(x.category, 14))}</td><td><span class="cell">${esc(x.question)}</span></td>
<td><span class="cell">${esc(cut(x.answer, 120))}</span></td><td>${esc(x.office)}</td><td>${esc(x.owner || '')}</td>
<td><b class="act ${x.action}">${x.action === 'create' ? '新增' : x.action === 'update' ? '更新' : '略過'}</b><small class="a">${esc(x.note)}</small>${x.similar ? `<small class="flag similar">⚠ ${esc(x.similar)}</small>` : ''}${x.related ? `<small class="flag related">相關舊題：${esc(x.related)}</small>` : ''}${x.warn ? `<small class="flag warn">⚠ ${esc(x.warn)}（預設不勾選）</small>` : ''}</td></tr>`).join('');
  $('#pick-all').checked = !rows.some(x => x.warn);
  msg('#commit-msg', '', true);
}

const pickedIndexes = () => [...document.querySelectorAll('#preview-rows [data-row]:checked')].map(input => Number(input.dataset.row));

function pickedRows() {
  return pickedIndexes().map(index => Object.fromEntries(FIELDS.map(f => [f, preview.rows[index][f]])));
}

async function commitImport() {
  const rows = pickedRows();
  if (!rows.length) return msg('#commit-msg', '請至少勾選一列。', false);
  const mode = document.querySelector('input[name=mode]:checked').value;
  const warning = mode === 'replace'
    ? `「完全取代」會刪掉目前知識庫的 ${preview.existing_total} 筆資料，只留下勾選的 ${rows.length} 筆。確定要繼續嗎？`
    : (() => {
      const creates = pickedIndexes().filter(index => preview.rows[index].action === 'create').length;
      return `確定匯入 ${rows.length} 筆？新增 ${creates} 筆、更新既有 ${rows.length - creates} 筆；更新的題目會記錄更新時間與更新內容。`;
    })();
  if (!confirm(warning)) return;
  const button = $('#commit'); button.disabled = true; button.textContent = '匯入中…';
  msg('#commit-msg', '正在寫入 CSV 並重新產生向量，資料量大時需要幾十秒，請不要關閉視窗。', true);
  try {
    const response = await fetch('/api/admin/faqs/import', { method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ rows, mode }) });
    if (!response.ok) throw new Error(await detail(response));
    const result = await response.json();
    await load();
    renderReport(result, preview);
    $('#preview-box').hidden = true; preview = null;
    msg('#import-msg', '匯入完成，逐筆結果列在下方。', true);
  } catch (error) {
    msg('#commit-msg', error.message, false);
  } finally { button.disabled = false; button.textContent = '確認匯入' }
}

function renderReport(result, plan) {
  const order = { '更新': 0, '新增': 1, '無變更': 2 }, tone = { '更新': 'update', '新增': 'create', '無變更': 'same' };
  const done = [...(result.report || [])].sort((a, b) => order[a.result] - order[b.result]);
  const imported = new Set(done.map(d => d.id));
  const skipped = plan.rows.filter(x => x.action === 'skip');
  const similar = plan.rows.filter(x => x.similar && imported.has(x.id));
  const total = name => done.filter(d => d.result === name).length;
  const line = (id, question, label, cls, note) => `<tr><td class="id">${esc(id)}</td><td>${esc(cut(question, 60))}</td><td><b class="act ${cls}">${label}</b></td><td>${esc(note)}</td></tr>`;
  $('#report-summary').innerHTML = `<strong>匯入完成（${esc(result.updated_at || '')}）</strong>：新增 ${total('新增')} 筆、更新 ${total('更新')} 筆、內容無變更 ${total('無變更')} 筆、略過 ${skipped.length} 筆` +
    `${similar.length ? `、相似提醒 ${similar.length} 筆` : ''}。知識庫現有 ${result.total} 筆${result.backup ? `，匯入前的資料已備份為 data/faq-backups/${esc(result.backup)}` : ''}。`;
  $('#report-rows').innerHTML = [
    ...done.map(d => line(d.id, d.question, d.result, tone[d.result] || 'same', d.note)),
    ...skipped.map(x => line(`第 ${x.row} 列`, x.question || '（沒有題目）', '略過', 'skip', x.note)),
    ...similar.map(x => line(x.id, x.question, '相似提醒', 'similar', x.similar)),
  ].join('') || '<tr><td colspan="4">沒有資料</td></tr>';
  $('#report').hidden = false;
  $('#report').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ----------------------------------------------------------------- 轉移給其他單位 */

function renderTransferBar() {
  $('#transfer-bar').hidden = !picked.size;
  $('#picked-count').textContent = picked.size;
  $('#apply-suggest').hidden = isOffice() || ![...picked].some(id => faqs.find(x => x.id === id)?.suggest);
}

async function transfer(ids, office) {
  const response = await fetch('/api/admin/faqs/transfer', { method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ ids, office }) });
  if (!response.ok) throw new Error(await detail(response));
  return (await response.json()).moved;
}

async function transferPicked() {
  const office = $('#transfer-to').value, ids = [...picked];
  if (!office) return msg('#transfer-msg', '請先選擇要轉移到哪個單位。', false);
  const leaving = isOffice() && !scope.offices.includes(office);
  if (!confirm(`確定把勾選的 ${ids.length} 題轉移給「${office}」？` + (leaving ? '\n轉移後這些題目會由對方單位維護，您將無法再看到或修改。' : ''))) return;
  await runTransfer(async () => transfer(ids, office), `已轉移給「${office}」`);
}

async function applySuggestions() {
  const groups = new Map();
  [...picked].map(id => faqs.find(x => x.id === id)).filter(x => x && x.suggest)
    .forEach(x => { if (!groups.has(x.suggest)) groups.set(x.suggest, []); groups.get(x.suggest).push(x.id) });
  const total = [...groups.values()].reduce((sum, ids) => sum + ids.length, 0);
  const lines = [...groups].map(([office, ids]) => `・${office}：${ids.length} 題`).join('\n');
  if (!confirm(`依建議單位轉移 ${total} 題（沒有建議的題目不會動）：\n${lines}\n\n建議是依題目關鍵字推測，轉移前請先確認。`)) return;
  await runTransfer(async () => { let moved = 0; for (const [office, ids] of groups) moved += await transfer(ids, office); return moved }, '已依建議單位轉移');
}

async function runTransfer(job, done) {
  const buttons = ['#transfer', '#apply-suggest'].map(s => $(s));
  buttons.forEach(b => { b.disabled = true });
  msg('#transfer-msg', '轉移中，正在更新向量…', true);
  try {
    const moved = await job();
    picked.clear();
    await load();
    msg('#transfer-msg', '', true);
    alert(`${done}，共 ${moved} 題。更新內容會記錄轉移前後的主責單位。`);
  } catch (error) { msg('#transfer-msg', error.message, false) } finally { buttons.forEach(b => { b.disabled = false }) }
}

/* ----------------------------------------------------------------- 單筆編輯 */

function openEditor(faq) {
  editingId = faq ? faq.id : null;
  const value = field => (faq ? faq[field] || '' : '');
  $('#edit-mode').textContent = faq ? `問題編號 ${faq.id}` : '新增';
  $('#edit-title').textContent = faq ? '編輯常見問題' : '新增常見問題';
  FIELDS.forEach(field => { $(`#f-${field}`).value = value(field) });
  // 新增時若正在看某個單位，先把主責單位填好，省得每次重打
  const scope = $('#office-filter').value;
  if (!faq && scope && scope !== NO_OFFICE && scope !== LEGACY) $('#f-office').value = scope;
  else if (!faq && role === 'editor' && myOffice) $('#f-office').value = myOffice;
  $('#delete').hidden = !faq;
  msg('#edit-msg', '', true);
  $('#editor').showModal();
  $('#f-question').focus();
}

async function saveEditor(event) {
  event.preventDefault();
  const payload = Object.fromEntries(FIELDS.map(field => [field, $(`#f-${field}`).value.trim()]));
  if (!payload.question || !payload.answer) return msg('#edit-msg', '問題與建議答案不可空白。', false);
  if (!payload.owner) { $('#f-owner').focus(); return msg('#edit-msg', '請填寫負責填寫人的姓名。', false) }
  if (isOffice()) {
    if (!payload.office) payload.office = scope.office;
    if (!official(payload.office)) { $('#f-office').focus(); return msg('#edit-msg', '主責單位請從清單選擇正式單位名稱。', false) }
    if (!scope.offices.includes(payload.office)) {
      if (!editingId) return msg('#edit-msg', '只能新增本單位的題目；要交給其他單位，請先存成本單位再用「轉移」。', false);
      if (!confirm(`主責單位改成「${payload.office}」等於把這題轉移給對方，存檔後您將無法再看到或修改。確定嗎？`)) return;
    }
  }
  const button = $('#edit-form .save'); button.disabled = true;
  msg('#edit-msg', '儲存中，正在更新向量…', true);
  try {
    const url = editingId ? `/api/admin/faqs/${encodeURIComponent(editingId)}` : '/api/admin/faqs';
    const response = await fetch(url, { method: editingId ? 'PUT' : 'POST', headers: jsonHeaders(), body: JSON.stringify(payload) });
    if (!response.ok) throw new Error(await detail(response));
    await load();
    $('#editor').close();
  } catch (error) { msg('#edit-msg', error.message, false) } finally { button.disabled = false }
}

async function removeFaq() {
  if (!editingId || !confirm(`確定刪除「${$('#f-question').value}」？此動作會同時移除向量資料。`)) return;
  msg('#edit-msg', '刪除中…', true);
  const response = await fetch(`/api/admin/faqs/${encodeURIComponent(editingId)}`, { method: 'DELETE', headers: headers() });
  if (!response.ok) return msg('#edit-msg', await detail(response), false);
  await load();
  $('#editor').close();
}

/* ----------------------------------------------------------------- 登入與事件 */

async function enterAdmin() {
  await load();
  localStorage.setItem(tokenKey(), token);
  if (role === 'editor' && myOffice && scope.all_offices.includes(myOffice) && !$('#office-filter').value) pickOffice(myOffice);
  $('#login').hidden = true; $('#app').hidden = false; $('#logout').hidden = false; $('#login-error').textContent = '';
}

// 共用編輯者選「我的單位」：記住選擇，並直接切到該單位的題目
function chooseMyOffice(value, jump) {
  myOffice = value;
  try { value ? localStorage.setItem(MY_OFFICE_KEY, value) : localStorage.removeItem(MY_OFFICE_KEY) } catch { }
  if (jump && value) pickOffice(value);
}

// 同一個輸入框：先當管理密碼／共用密碼試，不對再當處室登入碼試
async function login(value) {
  token = value;
  for (const next of ['admin', 'office']) {
    role = next;
    try { return await enterAdmin() } catch (error) { if (error.status !== 401 || next === 'office') throw error }
  }
}

async function download(path, filename) {
  if (!token) return alert('請先登入');
  const response = await fetch(path, { headers: headers() });
  if (!response.ok) return alert(await detail(response));
  const anchor = document.createElement('a');
  anchor.href = URL.createObjectURL(await response.blob());
  anchor.download = filename; anchor.click();
  URL.revokeObjectURL(anchor.href);
}

$('#login-form').onsubmit = async event => {
  event.preventDefault();
  try { await login($('#token').value) } catch (error) { $('#login-error').textContent = error.status === 401 ? '密碼不正確，請確認後再試一次' : error.message }
};
$('#logout').onclick = () => { localStorage.removeItem(tokenKey()); token = ''; location.reload() };

document.querySelectorAll('.tab').forEach(tab => tab.onclick = () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x === tab));
  source = tab.dataset.source;
  document.querySelectorAll('.source').forEach(panel => { panel.hidden = panel.dataset.panel !== source });
  msg('#import-msg', '', true);
});

$('#preview').onclick = runPreview;
$('#commit').onclick = commitImport;
$('#cancel').onclick = () => { $('#preview-box').hidden = true; preview = null; msg('#import-msg', '', true) };
$('#report-close').onclick = () => { $('#report').hidden = true };
$('#sort').onchange = () => { page = 1; renderList() };
$('#pick-all').onchange = event => document.querySelectorAll('#preview-rows [data-row]').forEach(input => { input.checked = event.target.checked });
$('#template').onclick = () => download('/api/admin/faqs/template.csv', 'faq-template.csv');
$('#export').onclick = () => download('/api/admin/faqs.csv', 'faq.csv');

$('#search').oninput = () => { page = 1; renderList() };
$('#category-filter').onchange = () => { page = 1; renderList() };
$('#office-filter').onchange = () => { page = 1; renderOfficeBoard(); renderList() };
$('#office-groups').onclick = event => { const b = event.target.closest('[data-office]'); if (b) pickOffice(b.dataset.office) };
$('#scope-clear').onclick = () => pickOffice('');
$('#prev').onclick = () => { page -= 1; renderList() };
$('#next').onclick = () => { page += 1; renderList() };
$('#add').onclick = () => openEditor(null);
$('#reindex').onclick = async () => {
  if (!confirm('重新計算所有常見問題的向量？資料多時需要一到數分鐘。')) return;
  const button = $('#reindex'); button.disabled = true; button.textContent = '重建中…';
  const response = await fetch('/api/admin/faqs/reindex', { method: 'POST', headers: headers() });
  button.disabled = false; button.textContent = '重建向量';
  alert(response.ok ? `已重建 ${(await response.json()).indexed} 筆向量。` : await detail(response));
};

$('#rows').onchange = event => {
  const box = event.target.closest('[data-pick]'); if (!box) return;
  box.checked ? picked.add(box.dataset.pick) : picked.delete(box.dataset.pick);
  renderList();
};
$('#pick-page').onchange = event => {
  document.querySelectorAll('#rows [data-pick]').forEach(box => { event.target.checked ? picked.add(box.dataset.pick) : picked.delete(box.dataset.pick) });
  renderList();
};
$('#pick-clear').onclick = () => { picked.clear(); msg('#transfer-msg', '', true); renderList() };
$('#transfer').onclick = transferPicked;
$('#my-office').onchange = event => chooseMyOffice(event.target.value, true);
$('#apply-suggest').onclick = applySuggestions;
$('#rows').onclick = event => {
  const button = event.target.closest('[data-edit]');
  if (button) openEditor(faqs.find(x => x.id === button.dataset.edit));
};
$('#edit-form').onsubmit = saveEditor;
$('#edit-close').onclick = () => $('#editor').close();
$('#delete').onclick = removeFaq;

$('#category-filter').dataset.all = '所有分類';
$('#office-filter').dataset.all = '所有主責單位';
if (token) enterAdmin().catch(error => {
  if (error.status === 401) localStorage.removeItem(tokenKey());
  token = '';
  $('#login').hidden = false; $('#app').hidden = true;
  $('#login-error').textContent = error.status === 401 ? '已儲存的登入資訊失效，請重新登入。' : error.message;
});
