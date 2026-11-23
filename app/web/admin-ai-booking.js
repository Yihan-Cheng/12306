const aiPreviewForm = $('aiPreviewForm');
const aiPreviewResult = $('aiPreviewResult');
const aiPreviewExamples = document.querySelectorAll('[data-ai-example]');

function renderAiPreview(preview) {
  aiPreviewResult.replaceChildren();
  const { target, task } = preview;
  analysisElement(aiPreviewResult, 'span', '模型 API', 'analysis-api-label');
  analysisElement(aiPreviewResult, 'h2', task ? '压测任务预览' : '区间余票');
  if (target) {
    analysisElement(aiPreviewResult, 'p', `${target.service_date} · ${target.train_no} · ${target.origin} → ${target.destination} · ${target.seat_type_name}`);
    analysisElement(aiPreviewResult, 'p', `当前可售 ${target.available_seats} 张`, 'analysis-answer');
  } else {
    analysisElement(aiPreviewResult, 'p', '全库随机选择在售产品');
  }

  if (task) {
    const items = [['模拟乘客', `${task.users} 人`], ['并发线程', task.concurrency],
      ['自动支付率', `${task.payRate}%`], ['无票时', task.waitlist ? '加入候补' : '不加入候补']];
    if (task.reserveSeats !== undefined) items.push(['目标预留', `${task.reserveSeats} 张`]);
    const stats = analysisElement(aiPreviewResult, 'dl', '', 'analysis-stats');
    for (const [label, value] of items) {
      const item = analysisElement(stats, 'div');
      analysisElement(item, 'dt', label);
      analysisElement(item, 'dd', value);
    }
  }

  const evidence = analysisDetails(aiPreviewResult, '查看只读 SQL 与绑定参数');
  analysisElement(evidence, 'pre', preview.sql);
  analysisElement(evidence, 'p', '绑定参数　' + JSON.stringify(preview.params));

  if (task) {
    analysisElement(aiPreviewResult, 'p', '启动后会创建模拟乘客和订单，并影响演示库存。', 'analysis-note');
    const start = analysisElement(aiPreviewResult, 'button', '确认并启动任务', 'analysis-button primary');
    start.type = 'button';
    start.onclick = async () => {
      start.disabled = true;
      try {
        const job = await submitAiJob(task);
        start.remove();
        analysisElement(aiPreviewResult, 'p', `任务 ${job.job_id} 已启动`);
      } catch (error) {
        toast(error.message, true);
        start.disabled = false;
      }
    };
  }
}

aiPreviewForm.oninput = () => {
  aiPreviewResult.hidden = true;
  aiPreviewResult.replaceChildren();
};

aiPreviewForm.onsubmit = async event => {
  event.preventDefault();
  const prompt = $('aiPrompt');
  const day = $('aiPreviewDate');
  const submit = $('aiPreviewSubmit');
  if (submit.disabled) return;
  const question = prompt.value.trim();
  if (!question) { prompt.focus(); return; }
  const serviceDate = day.value;
  const controls = [prompt, day, submit, ...aiPreviewExamples];
  controls.forEach(control => { control.disabled = true; });
  analysisMessage(aiPreviewResult, '正在解析需求并核对数据库…', 'loading');
  try {
    const response = await api('/api/admin/ai/preview', {
      method: 'POST', body: JSON.stringify({question, serviceDate})
    });
    if (response.clarify) analysisMessage(aiPreviewResult, response.clarify, 'error');
    else renderAiPreview(response);
  } catch (error) {
    analysisMessage(aiPreviewResult, error.message, 'error');
  } finally {
    aiPreviewResult.setAttribute('aria-busy', 'false');
    controls.forEach(control => { control.disabled = false; });
  }
};

for (const button of aiPreviewExamples) {
  button.onclick = () => {
    $('aiPrompt').value = button.dataset.aiExample;
    aiPreviewForm.requestSubmit();
  };
}
