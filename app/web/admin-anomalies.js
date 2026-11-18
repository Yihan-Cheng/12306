const anomalyStatus = {anomaly:'发现异常', normal:'未触发规则', empty:'没有可检查座位',
  warming:'正在积累采样', unavailable:'采样暂不可用'};
let anomalyBusy = false;

function renderAnomalies(report) {
  const root = $('anomalyResult');
  root.replaceChildren();
  function add(tag, text, parent = root) {
    const el = document.createElement(tag);
    el.textContent = text;
    parent.append(el);
    return el;
  }
  function table(columns, rows) {
    const wrap = add('div', '');
    wrap.className = 'table-scroll';
    const tab = add('table', '', wrap);
    const head = tab.createTHead().insertRow();
    columns.forEach(([,name]) => add('th', name, head));
    const body = tab.createTBody();
    rows.forEach(record => {
      const row = body.insertRow();
      columns.forEach(([key]) => add('td', record[key] ?? '—', row));
    });
  }
  add('h2', report.source || '数据库检测快照');
  add('p', report.scope + ' · ' + new Date(report.checked_at).toLocaleString('zh-CN'));
  const inventory = report.inventory;
  add('h3', '库存一致性 · ' + anomalyStatus[inventory.status]);
  add('p', '核对 ' + inventory.checked_seats + ' 个座位，异常 ' + inventory.anomaly_count + ' 个。');
  add('p', inventory.definition);
  if (inventory.findings.length) table([
    ['run_id','运行ID'],['seat_id','座位ID'],['carriage_no','车厢'],['seat_no','座位'],
    ['actual_mask','库存位图'],['expected_mask','分配合并位图'],['segments','不一致区段序号'],['overlap','分配重叠']
  ], inventory.findings.map(row => ({...row, segments:row.differing_segments.join('、') || '—',
    overlap:row.overlapping_allocations ? '是' : '否'})));
  const buffer = report.buffer;
  add('h3', '订票缓冲 · ' + anomalyStatus[buffer.status]);
  add('p', buffer.message);
  add('p', buffer.definition);
  if (buffer.samples.length) table([
    ['captured_at','采样时间'],['queued','排队数'],['processing','处理中'],
    ['oldest_seconds','最老等待秒数'],['expired_leases','过期租约数'],['retried','重试请求数']
  ], buffer.samples);
  if (report.explanation) {
    add('h3', report.explanation.mode);
    add('p', report.explanation.text);
  }
}

async function runAnomalyCheck(explain = false, demo = false) {
  if (anomalyBusy) return;
  anomalyBusy = true;
  const buttons = document.querySelectorAll('#view-anomalies button');
  buttons.forEach(b => b.disabled = true);
  const result = $('anomalyResult');
  result.hidden = false;
  result.textContent = explain ? '正在检测并生成解释…' : '正在读取检测证据…';
  try {
    const report = demo ? await api('/api/admin/anomalies/demo') :
      await api('/api/admin/anomalies/check', {method:'POST', body:JSON.stringify({
        date:$('anomalyDate').value, train:$('anomalyTrain').value.trim(), explain})});
    renderAnomalies(report);
  } catch (error) {
    result.textContent = '检测未完成。' + error.message;
  } finally {
    anomalyBusy = false;
    buttons.forEach(b => b.disabled = false);
  }
}
$('anomalyForm').onsubmit = event => { event.preventDefault(); runAnomalyCheck(); };
$('anomalyExplain').onclick = () => { if ($('anomalyForm').reportValidity()) runAnomalyCheck(true); };
$('anomalyDemo').onclick = () => runAnomalyCheck(false, true);
