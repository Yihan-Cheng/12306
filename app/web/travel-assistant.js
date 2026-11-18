// Recheck the selected leg using the existing passenger booking flow.
async function openAssistantLeg(leg, plan, button) {
  button.disabled = true;
  try {
    const start = locations.find(s => String(s.station_id) === String(leg.from_station_id));
    const end = locations.find(s => String(s.station_id) === String(leg.to_station_id));
    if (!start || !end) throw new Error('车站列表尚未加载，请刷新后重试');
    const query = new URLSearchParams({
      fromCity: start.city, fromStation: start.station_id, toCity: end.city, toStation: end.station_id,
      date: plan.date, passengers: plan.people
    });
    const rows = await api('/api/search/scoped-direct?' + query);
    const seat = rows.find(r => String(r.run_id) === String(leg.run_id) &&
                                String(r.seat_type_id) === String(leg.seat_type_id));
    if (!seat || Number(seat.available_seats) < plan.people) {
      throw new Error('这段行程的余票已变化，请重新规划');
    }
    const live = await api('/api/availability?' + new URLSearchParams({
      runId: seat.run_id, fromOrder: seat.from_order, toOrder: seat.to_order, seatTypeId: seat.seat_type_id
    }));
    if (Number(live.available_seats) < plan.people) throw new Error('这段行程的余票已变化，请重新规划');
    seat.available_seats = live.available_seats;
    for (const [prefix, station] of [['from', start], ['to', end]]) {
      $(prefix + 'City').value = station.city;
      updateStationOptions(prefix);
      $(prefix + 'Station').value = station.station_id;
    }
    lastSearch = rows;
    groupTrains();
    $('resultRoute').textContent = start.station_name + ' — ' + end.station_name;
    $('resultSummary').textContent = '列车时刻与实时余票 · 共 ' + trainGroups.length + ' 趟';
    selectBookingSeat(seat.run_id, seat.seat_type_id);
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

function showTravelPlan(plan) {
  const result = $('assistantResult');
  result.replaceChildren();
  function append(parent, tag, content, className) {
    const el = document.createElement(tag);
    el.textContent = content;
    if (className) el.className = className;
    parent.append(el);
    return el;
  }
  append(result, 'p', [plan.summary, plan.answer].filter(Boolean).join('。'));
  append(result, 'small', [plan.mode, plan.checked_at && '余票查询于 ' + plan.checked_at,
    plan.options.length > 0 && plan.ranking].filter(Boolean).join(' · '), 'assistant-meta');
  for (const opt of plan.options) {
    const card = append(result, 'article', '', 'assistant-option');
    const kind = opt.legs.length === 1 ? '直达' : '换乘 1 次 · ' + opt.legs[0].to_station_name + '站等候 ' + opt.transfer_minutes + ' 分钟';
    append(card, 'h3', kind + ' · 每人 ¥' + opt.price +
      (plan.people > 1 ? ' · ' + plan.people + '人合计 ¥' + opt.group_price : ''));
    for (const [i, leg] of opt.legs.entries()) {
      append(card, 'p', leg.train_no + '　' + leg.from_station_name + ' ' + timeOnly(leg.departure_at) +
        ' → ' + leg.to_station_name + ' ' + timeOnly(leg.arrival_at) +
        (String(leg.arrival_at).slice(0, 10) !== plan.date ? '（' + String(leg.arrival_at).slice(0, 10) + '）' : '') +
        '　' + leg.seat_type_name + ' · ¥' + leg.amount + ' · 余 ' + leg.available_seats + ' 张');
      const label = opt.legs.length > 1 ? '确认第 ' + (i + 1) + ' 段本人车票' : '确认本人车票';
      const button = append(card, 'button', label);
      button.type = 'button';
      button.onclick = () => openAssistantLeg(leg, plan, button);
    }
  }
  if (plan.options.length && (plan.people > 1 || plan.options.some(opt => opt.legs.length > 1))) {
    append(result, 'p', '购票页每次确认一位乘客的一段行程。同行乘客请分别购票，换乘需分别确认两段。');
  }
}

$('assistantExample').onclick = () => {
  $('travelQuestion').value = $('travelQuestion').placeholder;
  $('travelQuestion').focus();
};
$('assistantForm').onsubmit = async event => {
  event.preventDefault();
  const question = $('travelQuestion').value.trim();
  if (!question || $('askAssistant').disabled) return;
  $('askAssistant').disabled = true;
  $('assistantResult').textContent = '正在查询行程和区间余票…';
  try {
    const plan = await api('/api/travel-assistant', {method: 'POST', body: JSON.stringify({question})});
    showTravelPlan(plan);
  } catch (error) {
    $('assistantResult').textContent = '行程查询失败。' + error.message;
  } finally {
    $('askAssistant').disabled = false;
  }
};
