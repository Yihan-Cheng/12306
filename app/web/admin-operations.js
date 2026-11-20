const opsForm = $('opsForm');
const opsResult = $('opsResult');
const opsPrompts = document.querySelectorAll('.ops-examples button');

function renderOpsReport(report, question) {
  opsResult.replaceChildren();
  const mode = report.mode || '';
  const timestamp = report.checked_at && new Date(report.checked_at).toLocaleString('zh-CN');
  const metadata = [report.scope, mode, timestamp].filter(Boolean);
  if (metadata.length) analysisElement(opsResult, 'small', metadata.join(' · '), 'analysis-meta');
  analysisElement(opsResult, 'h2', report.clarify ? '请补充查询条件' : report.title);
  if (question !== report.title) analysisElement(opsResult, 'p', question, 'analysis-question');
  analysisElement(opsResult, 'p', report.clarify || report.answer, 'analysis-answer');
  if (report.clarify) return;

  if (report.rows.length) {
    analysisTable(opsResult, report.columns, report.rows, '无在售产品');
  } else {
    analysisElement(opsResult, 'p', '结果表为空', 'analysis-empty');
  }

  const evidence = analysisDetails(opsResult, '统计口径');
  analysisElement(evidence, 'p', report.definition);
  const query = analysisDetails(opsResult, '查看执行的 SQL 与绑定参数');
  analysisElement(query, 'pre', report.sql);
  analysisElement(query, 'p', '绑定参数　' + JSON.stringify(report.params));
}

opsForm.onsubmit = async event => {
  event.preventDefault();
  const button = $('opsSubmit');
  if (button.disabled) return;
  const question = $('opsQuestion').value.trim();
  if (!question) { $('opsQuestion').focus(); return; }
  button.disabled = true;
  opsPrompts.forEach(prompt => { prompt.disabled = true; });
  analysisMessage(opsResult, '正在分析问题并查询数据库…', 'loading');
  try {
    const report = await api('/api/admin/operations/query', {
      method: 'POST',
      body: JSON.stringify({question, serviceDate: $('opsDate').value})
    });
    renderOpsReport(report, question);
  } catch (error) {
    analysisMessage(opsResult, error.message, 'error');
  } finally {
    opsResult.setAttribute('aria-busy', 'false');
    button.disabled = false;
    opsPrompts.forEach(prompt => { prompt.disabled = false; });
  }
};

opsPrompts.forEach(button => {
  button.onclick = () => {
    $('opsQuestion').value = button.dataset.question;
    opsForm.requestSubmit();
  };
});
