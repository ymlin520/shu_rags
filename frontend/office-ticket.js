const $=s=>document.querySelector(s),ticketNo=decodeURIComponent(location.pathname.split('/').at(-1)),token=localStorage.getItem('school-faq-office-token')||'';const esc=v=>{const n=document.createElement('div');n.textContent=v??'';return n.innerHTML};let ticket;
function render(t){ticket=t;$('#loading').hidden=true;$('#content').hidden=false;$('#ticket-no').textContent=t.ticket_no;$('#badge').textContent=t.status;$('#office').textContent=t.department?`${t.office}／${t.department}`:t.office;$('#subject').textContent=t.subject;$('#description').textContent=t.description;$('#meta').textContent=`分類：${t.category} · ${t.created_at}`;$('#resolution').value=t.resolution||'';$('#transfer-office').value=t.office;renderSettle(t);$('#events').innerHTML=t.events.map(e=>`<div class="event"><strong>${esc(e.actor)}</strong><p>${esc(e.message)}</p><small>${esc(e.created_at)} · ${esc(e.office)}</small></div>`).join('')}
function renderSettle(t){const state=$('#settle-state'),button=$('#settle');
if(t.settled){state.textContent=`已核銷：${t.settled_at||''}${t.settled_by?'／'+t.settled_by:''}${t.settle_note?'（'+t.settle_note+'）':''}`;
state.className='done';button.textContent='取消核銷';button.className='undo'}
else{state.textContent='尚未核銷';state.className='';button.textContent='標記為已核銷';button.className=''}}
$('#settle').onclick=async()=>{const settled=!ticket.settled;
try{const r=await fetch(`/api/office/tickets/${encodeURIComponent(ticketNo)}/settle`,{method:'POST',
headers:{'X-Office-Token':token,'Content-Type':'application/json'},
body:JSON.stringify({settled,note:$('#settle-note').value.trim()})});
const d=await r.json();if(!r.ok)throw new Error(d.detail||'核銷失敗');
$('#settle-status').textContent=settled?'已標記為核銷':'已取消核銷';await load()}
catch(err){$('#settle-status').textContent=err.message}};
async function load(){if(!token)return location.href='/office';const r=await fetch(`/api/office/tickets/${encodeURIComponent(ticketNo)}`,{headers:{'X-Office-Token':token}}),d=await r.json();if(!r.ok){$('#loading').textContent=d.detail||'無法讀取詢問單';return}render(d)}async function save(body){const r=await fetch(`/api/office/tickets/${encodeURIComponent(ticketNo)}`,{method:'PATCH',headers:{'X-Office-Token':token,'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok)throw new Error(d.detail||'儲存失敗');return d}
$('#form').onsubmit=async e=>{e.preventDefault();try{await save({status:'已解決',office:ticket.office,assignee:'本處室承辦人',resolution:$('#resolution').value.trim()+($('#faq').checked?'\n[列入知識庫整理候選]':'')});$('#save-status').textContent='回覆已送出，詢問單已標記為已解決';await load()}catch(err){$('#save-status').textContent=err.message}};$('#transfer').onclick=async()=>{const office=$('#transfer-office').value;if(office===ticket.office)return alert('請選擇其他處室');try{await save({status:'待處理',office,assignee:'',resolution:$('#transfer-reason').value.trim()||`轉派至 ${office}`});alert('詢問單已轉出');location.href='/office'}catch(err){alert(err.message)}};load();
