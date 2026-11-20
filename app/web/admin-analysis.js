function analysisElement(parent, tag, text = '', className = '') {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  parent.append(node);
  return node;
}

function analysisTable(parent, columns, rows, emptyValue = '—') {
  const scroll = analysisElement(parent, 'div', '', 'table-scroll');
  scroll.tabIndex = 0;
  scroll.setAttribute('aria-label', '数据表，可横向滚动');
  const table = analysisElement(scroll, 'table');
  const head = table.createTHead().insertRow();
  for (const [, label] of columns) analysisElement(head, 'th', label).scope = 'col';
  const body = table.createTBody();
  for (const record of rows) {
    const row = body.insertRow();
    for (const [key] of columns) analysisElement(row, 'td', record[key] ?? emptyValue);
  }
}

function analysisDetails(parent, label) {
  const details = analysisElement(parent, 'details');
  analysisElement(details, 'summary', label);
  return details;
}

function analysisMessage(result, text, state) {
  result.hidden = false;
  result.replaceChildren();
  result.setAttribute('aria-busy', String(state === 'loading'));
  const card = analysisElement(result, 'div', '', 'analysis-card');
  const message = analysisElement(card, 'p', text, 'analysis-state');
  message.dataset.state = state;
  if (state === 'loading') result.scrollIntoView({block: 'nearest'});
}
