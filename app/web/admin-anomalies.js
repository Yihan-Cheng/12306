const anomalyStatus = {anomaly:'发现异常', normal:'未触发规则', empty:'没有可检查座位',
  warming:'正在积累采样', unavailable:'采样暂不可用'};
let anomalyBusy = false;

function diagnosticCard(parent, title, status, metrics) {
  const card = analysisElement(parent, 'section', '', 'admin-card analysis-card');
  analysisElement(card, 'h3', title);
  const label = analysisElement(card, 'small', anomalyStatus[status], 'analysis-status');
  label.dataset.state = status;
  const stats = analysisElement(card, 'dl', '', 'analysis-stats');
  for (const [name, value] of metrics) {
    const stat = analysisElement(stats, 'div');
    analysisElement(stat, 'dt', name);
    analysisElement(stat, 'dd', value ?? '—');
  }
  return card;
}

function renderQueueTrend(card, samples) {
  const chart = analysisElement(card, 'figure', '', 'analysis-chart');
  analysisElement(chart, 'figcaption', '排队请求数 · 最近 ' + samples.length + ' 次采样');
  const bars = analysisElement(chart, 'div', '', 'analysis-bars');
  // The adjacent table exposes the exact counts and sample times.
  bars.setAttribute('aria-hidden', 'true');
  const max = Math.max(1, ...samples.map(sample => sample.queued));
  for (const sample of samples) {
    const bar = analysisElement(bars, 'i');
    bar.style.height = (sample.queued / max * 100) + '%';
    bar.title = sample.captured_at + ' · ' + sample.queued + ' 条';
  }
}

function renderExplanationEvidence(summary, report, isModel) {
  const { inventory, buffer, explanation } = report;
  const evidence = analysisDetails(summary, '本次解读依据');
  evidence.className = 'anomaly-evidence';
  const source = isModel && explanation.model ? `模型 API · ${explanation.model}` : explanation.mode;
  analysisElement(evidence, 'p', `解读生成方式 · ${source}`, 'analysis-note');

  analysisElement(evidence, 'h4', '库存核对');
  const range = report.source ? '采用模拟库存样本' : '核对所选运营日和车次的全部现有运行座位';
  analysisElement(evidence, 'p', `${range}，共 ${inventory.checked_seats} 席。`
    + `位图不一致 ${inventory.mask_mismatch_count} 席，重叠分配 ${inventory.overlap_seat_count} 席，去重后异常 ${inventory.anomaly_count} 席。`);
  if (!report.source) analysisElement(evidence, 'p', '来源 · v_anomaly_seats 库存一致性视图', 'analysis-note');

  analysisElement(evidence, 'h4', '订票缓冲采样');
  const samples = buffer.samples;
  const sampleSource = report.source ? '模拟缓冲' : '全库订票缓冲';
  const rangeLabel = samples.length > 1 ? `（${samples[0].captured_at} 至 ${samples.at(-1).captured_at}）` : '';
  analysisElement(evidence, 'p', `${sampleSource}保留 ${samples.length} 次采样${rangeLabel}。${buffer.message}`);
  if (!report.source) analysisElement(evidence, 'p', '来源 · booking_request_buffer 订票缓冲表', 'analysis-note');
  if (samples.length) {
    analysisTable(evidence, [['captured_at', '最近采样时间'], ['queued', '排队数'], ['oldest_seconds', '最老等待（秒）']], samples.slice(-3));
  }
  if (isModel) analysisElement(evidence, 'p', '模型根据库存汇总、缓冲采样和规则说明生成解读。检测状态由程序按规则判定。', 'analysis-note');
}

function renderAnomalies(report) {
  const root = $('anomalyResult');
  root.replaceChildren();
  const summary = analysisElement(root, 'section', '', 'admin-card analysis-card');
  analysisElement(summary, 'h2', report.source || '数据库检测快照');
  analysisElement(summary, 'small', report.scope + ' · ' + new Date(report.checked_at).toLocaleString('zh-CN'), 'analysis-meta');
  if (report.explanation) {
    const { mode } = report.explanation;
    const isModel = mode.startsWith('模型');
    analysisElement(summary, 'h3', isModel ? '模型诊断' : '检测解读');
    if (isModel) analysisElement(summary, 'span', '模型 API', 'analysis-api-label');
    analysisElement(summary, 'p', report.explanation.text, 'analysis-answer');
    renderExplanationEvidence(summary, report, isModel);
  }

  const diagnostics = analysisElement(root, 'div', '', 'analysis-diagnostics');
  const inventory = report.inventory;
  const seats = diagnosticCard(diagnostics, '库存一致性', inventory.status, [
    ['检查座位', inventory.checked_seats], ['异常座位', inventory.anomaly_count],
    ['位图不一致', inventory.mask_mismatch_count], ['重叠分配', inventory.overlap_seat_count]
  ]);
  const inventoryEvidence = analysisDetails(seats, '库存规则与异常明细');
  analysisElement(inventoryEvidence, 'p', inventory.definition);
  if (inventory.findings.length) {
    analysisTable(inventoryEvidence, [
      ['run_id','运行 ID'], ['seat_id','座位 ID'], ['carriage_no','车厢'], ['seat_no','座位'],
      ['actual_mask','库存位图'], ['expected_mask','分配合并位图'], ['segments','不一致区段'], ['overlap','分配重叠']
    ], inventory.findings.map(row => ({...row, segments: row.differing_segments.join('、') || '—',
      overlap: row.overlapping_allocations ? '是' : '否'})));
    inventoryEvidence.open = true;
  }

  const buffer = report.buffer;
  const latest = buffer.samples.at(-1);
  const queue = diagnosticCard(diagnostics, '订票缓冲', buffer.status, [
    ['最近采样排队数', latest?.queued], ['最老等待（秒）', latest?.oldest_seconds],
    ['处理中', latest?.processing], ['过期处理租约', latest?.expired_leases]
  ]);
  analysisElement(queue, 'p', buffer.message, 'analysis-note');
  if (buffer.samples.length) renderQueueTrend(queue, buffer.samples);
  const queueEvidence = analysisDetails(queue, '积压规则与采样明细');
  analysisElement(queueEvidence, 'p', buffer.definition);
  if (buffer.samples.length) {
    analysisTable(queueEvidence, [
      ['captured_at','采样时间'], ['queued','排队数'], ['processing','处理中'],
      ['oldest_seconds','最老等待（秒）'], ['expired_leases','过期租约'], ['retried','重试请求']
    ], buffer.samples);
  }
}

async function runAnomalyCheck(explain = false, demo = false) {
  if (anomalyBusy) return;
  anomalyBusy = true;
  const buttons = document.querySelectorAll('#view-anomalies button');
  buttons.forEach(b => b.disabled = true);
  const result = $('anomalyResult');
  analysisMessage(result, explain ? '正在检测并生成解释…' : '正在读取检测证据…', 'loading');
  try {
    const report = demo ? await api('/api/admin/anomalies/demo') :
      await api('/api/admin/anomalies/check', {method:'POST', body:JSON.stringify({
        date:$('anomalyDate').value, train:$('anomalyTrain').value.trim(), explain})});
    renderAnomalies(report);
  } catch (error) {
    analysisMessage(result, error.message, 'error');
  } finally {
    result.setAttribute('aria-busy', 'false');
    anomalyBusy = false;
    buttons.forEach(b => b.disabled = false);
  }
}
$('anomalyForm').onsubmit = event => { event.preventDefault(); runAnomalyCheck(true); };
$('anomalyRun').onclick = () => { if ($('anomalyForm').reportValidity()) runAnomalyCheck(); };
$('anomalyDemo').onclick = () => runAnomalyCheck(false, true);
