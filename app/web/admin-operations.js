const opsForm = $('opsForm');
const opsResult = $('opsResult');

function renderOpsReport(report) {
  opsResult.replaceChildren();
  function add(tag, text, parent = opsResult) {
    const node = document.createElement(tag);
    node.textContent = text;
    parent.append(node);
    return node;
  }
  if (report.clarify) {
    add('p', report.clarify);
    if (report.mode) add('small', report.mode);
    return;
  }
  add('small', [report.scope, report.mode, new Date(report.checked_at).toLocaleString('zh-CN')].join(' · '));
  add('h2', report.title);
  add('p', report.answer);
  add('h3', '统计口径');
  add('p', report.definition);
  if (report.rows.length) {
    const scroll = add('div', '');
    scroll.className = 'table-scroll';
    const table = add('table', '', scroll);
    const head = table.createTHead().insertRow();
    for (const [, label] of report.columns) add('th', label, head);
    const body = table.createTBody();
    for (const record of report.rows) {
      const row = body.insertRow();
      for (const [key] of report.columns) add('td', record[key] ?? '无在售产品', row);
    }
  }
  const details = add('details', '');
  add('summary', '查看执行的 SQL 与绑定参数', details);
  add('pre', report.sql, details);
  add('p', '绑定参数　' + JSON.stringify(report.params), details);
}

opsForm.onsubmit = async event => {
  event.preventDefault();
  const button = $('opsSubmit');
  if (button.disabled) return;
  const question = $('opsQuestion').value.trim();
  if (!question) { $('opsQuestion').focus(); return; }
  button.disabled = true;
  opsResult.hidden = false;
  opsResult.textContent = '正在查询运营数据库…';
  try {
    const report = await api('/api/admin/operations/query', {method: 'POST',
      body: JSON.stringify({question, serviceDate: $('opsDate').value})});
    renderOpsReport(report);
  } catch (error) {
    opsResult.textContent = error.message;
  } finally {
    button.disabled = false;
  }
};

document.querySelectorAll('.ops-examples button').forEach(button => {
  button.onclick = () => {
    if ($('opsSubmit').disabled) return;
    $('opsQuestion').value = button.textContent;
    opsForm.requestSubmit();
  };
});
