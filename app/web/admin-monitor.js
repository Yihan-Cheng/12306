const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const labels = {FREE:'可售', PAID:'已支付', HOLD:'锁座中', WAITLIST:'候补兑现'};
const waitLabels = {WAITING:'候补中', MATCHING:'匹配中', MATCHED_HOLD:'正在兑现', FULFILLED:'已兑现', CANCELLED:'已取消', EXPIRED:'已过期'};
const pending = row => ['WAITING','MATCHING','MATCHED_HOLD'].includes(row.wait_status);
let selection = {runId:null, fromOrder:1, toOrder:'', seatTypeId:'', carriageNo:''};
let snapshot = null, timer = null, controller = null, generation = 0, paused = false;
let previous = null, changes = [], selectedSeat = null, lookupGeneration = 0;

async function api(path, signal) {
  const response = await fetch(path, {signal, cache:'no-store'});
  if (response.status === 401) { location.replace('/admin-login.html'); throw new Error('请先登录管理员'); }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '读取失败');
  return data;
}
function setStatus(text, stale=false) { $('connection').textContent=text; $('connection').classList.toggle('stale',stale); }
function options(id, values, value) {
  const markup = values.map(([key,label]) => `<option value="${escapeHtml(key)}">${escapeHtml(label)}</option>`).join('');
  if ($(id).innerHTML !== markup) $(id).innerHTML=markup;
  $(id).value=String(value ?? ''); $(id).disabled=false;
}
function invalidate() {
  generation++; clearTimeout(timer); controller?.abort(); controller=null;
  previous=null; changes=[];
  $('changes').innerHTML='<p class="empty">等待下一次座位或候补变化</p>';
  $('seatDialog').close(); selectedSeat=null;
}
async function findTrain(event) {
  event?.preventDefault();
  const trainNo=$('trainNo').value.trim().toUpperCase();
  if (!trainNo) return;
  const lookup=++lookupGeneration;
  invalidate(); $('findTrain').disabled=true;
  setStatus('正在查找车次…');
  try {
    const data=await api(`/api/admin/ai/options?q=${encodeURIComponent(trainNo)}`);
    if (lookup!==lookupGeneration) return;
    if (!data.runs.length) throw new Error('没有找到该在售车次，请输入完整车次号');
    const run=data.runs.find(r=>String(r.run_id)===String(selection.runId)) || data.runs[0];
    options('runSelect', data.runs.map(r=>[r.run_id,`${r.service_date} · ${r.train_no}`]),run.run_id);
    const firstClass=data.seat_types.find(s=>String(s.run_id)===String(run.run_id)&&s.seat_type_name==='一等座');
    selection={runId:run.run_id,fromOrder:1,toOrder:'',seatTypeId:firstClass?.seat_type_id || '',carriageNo:''};
    await refresh();
  } catch(error) {
    $('error').hidden=false; $('error').textContent=error.message;
    setStatus('车次未切换 · 保留上次数据',true);
  } finally { if (lookup===lookupGeneration) $('findTrain').disabled=false; }
}
function renderControls(data) {
  options('seatType',[['','全部席别'],...data.seat_types.map(s=>[s.seat_type_id,s.seat_type_name])],selection.seatTypeId);
  options('carriage',[['','全部车厢'],...data.carriages.map(n=>[n,`${n} 车`])],selection.carriageNo);
  options('fromStop',data.stops.slice(0,-1).map(s=>[s.station_order,s.station_name]),data.from_order);
  options('toStop',data.stops.filter(s=>s.station_order>data.from_order).map(s=>[s.station_order,s.station_name]),data.to_order);
}
function seatSignature(seat) { return JSON.stringify([seat.status,seat.occupants]); }
function recordChanges(data) {
  const current={seats:new Map(data.seats.map(s=>[s.seat_id,seatSignature(s)])), waits:new Map(data.waits.map(w=>[w.wait_request_id,w.wait_status]))};
  const changed=new Set();
  const now=new Date().toLocaleTimeString('zh-CN',{hour12:false});
  const add=text=>changes.unshift({time:now,text});
  if (previous) {
    for (const seat of data.seats) {
      if (previous.seats.has(seat.seat_id)&&previous.seats.get(seat.seat_id)!==current.seats.get(seat.seat_id)) {
        changed.add(seat.seat_id);
        const names=seat.occupants.filter(a=>a.in_interval).map(a=>a.passenger_name).join('、');
        add(`${seat.carriage_no}车 ${seat.seat_no} → ${labels[seat.status]}${names?' · '+names:''}`);
      }
    }
    for (const wait of data.waits) {
      if ((!previous.waits.has(wait.wait_request_id)&&pending(wait)) ||
          (previous.waits.has(wait.wait_request_id)&&previous.waits.get(wait.wait_request_id)!==wait.wait_status)) {
        add(`${(wait.passengers||[]).map(p=>p.passenger_name).join('、')} · ${waitLabels[wait.wait_status]||wait.wait_status}`);
      }
    }
  }
  previous=current; changes=changes.slice(0,20);
  $('changes').innerHTML=changes.length?changes.map(c=>`<div class="change"><time>${escapeHtml(c.time)}</time>${escapeHtml(c.text)}</div>`).join(''):'<p class="empty">等待下一次座位或候补变化</p>';
  return changed;
}
function seatMarkup(seat,changed) {
  const occupants=seat.occupants.filter(a=>a.in_interval);
  const names=occupants.map(a=>a.passenger_name).join('、');
  const caption=names || (seat.status==='FREE'?'等待抢票':'占用中');
  const hint=occupants.length?`${occupants[0].from_station_name} → ${occupants[0].to_station_name}${occupants.length>1?' 等':''}`:
    seat.occupants.length?'其他区间有乘客 · 本区间可售':'本区间可售';
  return `<button class="seat ${seat.status.toLowerCase()} ${changed.has(seat.seat_id)?'changed':''}" data-seat-id="${seat.seat_id}" aria-label="${escapeHtml(`${seat.carriage_no}车 ${seat.seat_no} ${labels[seat.status]} ${caption}`)}"><div><b>${escapeHtml(seat.seat_no)}</b><em>${labels[seat.status]}</em></div><strong title="${escapeHtml(caption)}">${escapeHtml(caption)}</strong><small>${escapeHtml(hint)}</small></button>`;
}
function waitMarkup(wait) {
  const names=(wait.passengers||[]).map(p=>p.passenger_name).join('、');
  const isPending=pending(wait);
  const status=wait.wait_status==='FULFILLED'&&wait.matched_order_status==='REFUNDED'?'兑现后已退票':waitLabels[wait.wait_status]||wait.wait_status;
  const preference=wait.position_code?`偏好 ${wait.position_code} · ${wait.allow_fallback?'可换其他位置':'不换位置'}`:'不限座位位置';
  const payment={PAID:'已预付',APPLIED:'预付款已用于车票',REFUNDED:'已退款'}[wait.payment_status]||'未预付';
  return `<article class="queue-item"><header><span>${escapeHtml(names||'乘客')}</span><span class="tag ${isPending?'':'success'}">${escapeHtml(status)}</span></header><p>${escapeHtml(wait.from_station_name)} → ${escapeHtml(wait.to_station_name)} · ${escapeHtml(wait.seat_type_name)}</p><p>${wait.passenger_count} 人 · ${escapeHtml(preference)}</p><small>${isPending?`席别队列 #${wait.queue_position} · `:''}${escapeHtml(payment)} · ${escapeHtml(String(wait.created_at).replace('T',' ').slice(5,19))}</small>${isPending&&wait.skip_count>=3?' <span class="tag protected">公平保护</span>':''}</article>`;
}
function render(data) {
  const changed=recordChanges(data), summary=data.summary;
  const from=data.stops.find(s=>s.station_order===data.from_order), to=data.stops.find(s=>s.station_order===data.to_order);
  const seatType=data.seat_types.find(s=>String(s.seat_type_id)===String(selection.seatTypeId))?.seat_type_name||'全部席别';
  $('routeTitle').textContent=`${data.run.train_no} · ${from.station_name} → ${to.station_name}`;
  $('scopeNote').textContent=`${data.run.service_date} · ${seatType} · ${selection.carriageNo?selection.carriageNo+' 车':'全部车厢'} · 座位按所选区间计算，候补显示相交区间的申请。`;
  $('updatedAt').textContent=String(data.run.captured_at).replace('T',' ').slice(11,19);
  for (const [id,key] of [['freeCount','free'],['paidCount','paid'],['heldCount','held'],['waitingCount','waiting_people'],['fulfilledCount','fulfilled_people']]) $(id).textContent=summary[key];
  $('totalCount').textContent=`共 ${summary.total} 席 · 可售 ${summary.free} 席`;
  const groups=new Map();
  for (const seat of data.seats) {
    const key=`${seat.carriage_no}-${seat.seat_type_id}`;
    if (!groups.has(key)) groups.set(key,[]);
    groups.get(key).push(seat);
  }
  $('seatGroups').innerHTML=[...groups.values()].map(seats=>`<section><div class="carriage-heading"><b>${seats[0].carriage_no} 车 · ${escapeHtml(seats[0].seat_type_name)}</b><span>${seats.filter(s=>s.status==='FREE').length} 可售 / ${seats.length} 席</span></div><div class="seat-grid">${seats.map(s=>seatMarkup(s,changed)).join('')}</div></section>`).join('')||'<p class="empty">当前范围没有配置座位</p>';
  const waiting=data.waits.filter(pending);
  $('queueCount').textContent=`${waiting.length} 单`;
  $('waitList').innerHTML=waiting.map(waitMarkup).join('')||'<p class="empty">目前无人候补</p>';
  const fulfilled=data.waits.filter(w=>w.wait_status==='FULFILLED').sort((a,b)=>Number(b.matched_order_id)-Number(a.matched_order_id)).slice(0,8);
  $('fulfilledList').innerHTML=fulfilled.map(waitMarkup).join('')||'<p class="empty">尚无候补兑现记录</p>';
  if ($('seatDialog').open) renderSeatDetails();
}
function renderSeatDetails() {
  const seat=snapshot?.seats.find(s=>s.seat_id===selectedSeat);
  if (!seat) { $('seatDialog').close(); return; }
  $('seatTitle').textContent=`${seat.carriage_no} 车 ${seat.seat_no} · ${seat.seat_type_name}`;
  $('seatDetails').innerHTML=`<p class="tag ${seat.status.toLowerCase()}">所选区间：${labels[seat.status]}</p>`+
    (seat.occupants.map(a=>`<article class="occupant"><strong>${escapeHtml(a.passenger_name)}</strong> <span class="tag">${a.is_ai?'AI 乘客':'用户'}</span><p>${escapeHtml(a.from_station_name)} → ${escapeHtml(a.to_station_name)}</p><p>${a.in_interval?'与所选区间重叠':'其他区间，本区间仍可售'} · ${a.allocation_status==='HOLD'?'锁座中':a.order_source==='WAITLIST'?'候补兑现':'已支付'}</p><small>订单 #${a.order_id} · ${escapeHtml(String(a.allocated_at).replace('T',' ').slice(0,19))}</small></article>`).join('')||'<p class="empty">该座位当前没有有效占用</p>');
}
async function refresh() {
  clearTimeout(timer);
  if (!selection.runId) return;
  const epoch=++generation;
  controller?.abort();
  const request=new AbortController(); controller=request;
  const timeout=setTimeout(()=>request.abort(),15000);
  try {
    const params=new URLSearchParams(Object.entries(selection).filter(([,v])=>v!==''&&v!==null));
    const data=await api(`/api/admin/live-inventory?${params}`,request.signal);
    if (epoch!==generation) return;
    snapshot=data; selection.toOrder=data.to_order;
    renderControls(data); render(data); $('error').hidden=true;
    setStatus(paused?'已暂停刷新':'● 实时更新中',paused);
  } catch(error) {
    if (epoch!==generation) return;
    $('error').hidden=false;
    $('error').textContent=`${error.name==='AbortError'?'读取超时':error.message}。当前显示的是上次成功读取的数据，正在重试。`;
    setStatus('数据未更新',true);
  } finally {
    clearTimeout(timeout);
    if (epoch===generation) {
      controller=null;
      if (!paused&&!document.hidden) timer=setTimeout(refresh,2000);
    }
  }
}
function changeFilter(key,value) { invalidate(); selection[key]=value; setStatus('正在切换筛选…'); refresh(); }
$('trainForm').onsubmit=findTrain;
$('runSelect').onchange=()=>{invalidate();selection={runId:$('runSelect').value,fromOrder:1,toOrder:'',seatTypeId:'',carriageNo:''};refresh();};
$('seatType').onchange=()=>{selection.carriageNo='';changeFilter('seatTypeId',$('seatType').value);};
$('carriage').onchange=()=>changeFilter('carriageNo',$('carriage').value);
$('fromStop').onchange=()=>{const from=Number($('fromStop').value);if(Number(selection.toOrder)<=from)selection.toOrder='';changeFilter('fromOrder',from);};
$('toStop').onchange=()=>changeFilter('toOrder',Number($('toStop').value));
$('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'恢复刷新':'暂停刷新';clearTimeout(timer);setStatus(paused?'已暂停刷新':'正在刷新…',paused);if(!paused)refresh();};
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{$('error').hidden=false;$('error').textContent='浏览器未允许全屏，请使用浏览器的全屏功能。';}};
document.addEventListener('fullscreenchange',()=>{$('fullscreen').textContent=document.fullscreenElement?'退出全屏':'全屏投放';});
document.addEventListener('visibilitychange',()=>{clearTimeout(timer);if(!document.hidden&&!paused)refresh();});
$('seatGroups').onclick=event=>{const button=event.target.closest('[data-seat-id]');if(!button)return;selectedSeat=Number(button.dataset.seatId);renderSeatDetails();$('seatDialog').showModal();};
$('closeSeat').onclick=()=>$('seatDialog').close();
$('seatDialog').onclick=event=>{if(event.target===$('seatDialog')){const r=$('seatDialog').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)$('seatDialog').close();}};
api('/api/admin/auth/session').then(()=>findTrain()).catch(error=>{setStatus('无法连接',true);$('error').hidden=false;$('error').textContent=error.message;});
