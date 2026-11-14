import {jobs} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {chart} from '../components/common/chart.js';
import {table} from '../components/common/table.js';
import {status,takeoverBadge,attemptRow} from '../components/common/status.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
const canWrite=()=>session.user.role!=='viewer';
function attemptsPanel(j){
 const list=j.attempts||[];
 if(!list.length)return '';
 return '<section class="panel"><div class="section-title"><h2>执行尝试</h2><span>每次领取、接管与结果均留痕 · 共 '+list.length+' 次</span></div><table class="attempt-table"><thead><tr><th>尝试</th><th>触发原因</th><th>状态</th><th>开始</th><th>结束</th><th>失败原因</th></tr></thead><tbody>'+list.map(attemptRow).join('')+'</tbody></table></section>';
}
function retryBar(j){
 if(j.status!=='failed')return '';
 const busy=j.status==='queued'||j.status==='running';
 return '<div class="retry-bar"><p class="warning">最近一次执行失败：'+esc(j.error||'未知原因')+'。可在原任务上重试，历史尝试与原因保留。</p>'+(canWrite()?'<button class="primary" id="retry-job" '+(busy?'disabled':'')+'>在原任务重试 ↻</button>':'<p class="hint">观察员无重试权限。</p>')+'</div>';
}
export async function results(id){
 workspace.jobs=await jobs.list();
 const j=id?await jobs.get(id):(workspace.jobs.find(x=>x.id===workspace.selectedJob)||workspace.jobs[0]);
 if(j&&!workspace.jobs.some(x=>x.id===j.id))workspace.jobs.push(j);
 if(!j)return heading('04 / REVIEW','结果复核','尚无分析结果。')+'<div class="empty">先到分析工作台，选择批次并提交一次计算。<a href="#/workbench">前往工作台 ↗</a></div>';
 workspace.selectedJob=j.id;const r=j.result||{};
 const head=heading('04 / REVIEW','结果复核与业务解释',j.name,'<button class="button" id="refresh-results">刷新结果 ↻</button>');
 const selector='<div class="result-selector"><label>分析记录<select id="select-job">'+workspace.jobs.map(x=>'<option value="'+x.id+'" '+(x.id===j.id?'selected':'')+'>'+esc(x.name)+' · '+esc(x.status)+'</option>').join('')+'</select></label>'+status(j.status)+takeoverBadge(j)+'<span>'+date(j.created_at)+'</span><span class="approval">'+(j.approved?'已获业务批准':'待负责人复核')+'</span></div>';
 // 仅 completed（有效执行发布的结果）才渲染结论；fencing 已保证 result 不被失联旧执行覆盖
 const body=j.status==='completed'
  ?'<section class="result-lead"><p class="eyebrow">COMPUTED FINDING</p><h2>'+esc(r.summary)+'</h2><div class="metrics">'+(r.metrics||[]).map(m=>'<div><span>'+esc(m.label)+'</span><strong>'+esc(fmt(m.value))+'<small>'+esc(m.unit||'')+'</small></strong></div>').join('')+'</div></section><section class="panel">'+chart(r.chart)+'</section><div class="two-columns"><section class="panel"><div class="section-title"><h2>业务解释</h2><span>由计算结果生成</span></div><ol class="questions">'+(r.findings||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ol>'+(r.warnings||[]).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+'</section><section class="method-sheet compact"><p class="eyebrow">REPRODUCIBILITY</p><h3>计算口径与参数</h3><p>'+esc(r.method)+'</p><pre>'+esc(JSON.stringify(j.params,null,2))+'</pre>'+(session.user.role==='admin'&&!j.approved?'<button class="primary" id="approve-job">批准此业务结论</button>':'')+'<p class="hint">仅批准结果可进入定时分发档案。</p></section></div><section class="panel"><div class="section-title"><h2>结果明细</h2><span>'+(r.table?.rows?.length||0)+' 行</span></div>'+table(r.table?.columns||[],r.table?.rows||[])+'</section>'
  :'<section class="panel empty">'+retryBar(j)+(j.status==='failed'?'':'<p>'+(j.status==='queued'?'任务已排队，等待计算进程领取。':'计算进程正在执行，持续心跳期间不会被接管；失联超时后将由其他进程接管。')+' 点击刷新查看最新进展。</p>')+'<a href="#/workbench">返回工作台 ↗</a></section>';
 return head+selector+body+attemptsPanel(j);
}
export function bindResults(refresh){
 document.querySelector('#refresh-results')?.addEventListener('click',refresh);
 document.querySelector('#select-job')?.addEventListener('change',e=>{workspace.selectedJob=Number(e.target.value);location.hash='#/results/'+e.target.value;});
 document.querySelector('#approve-job')?.addEventListener('click',async()=>{try{await jobs.approve(workspace.selectedJob);notify('已批准，可创建分发计划');await refresh();}catch(e){notify(e.message,true);}});
 const retryBtn=document.querySelector('#retry-job');
 if(retryBtn)retryBtn.addEventListener('click',async()=>{
   retryBtn.disabled=true; // 连续点击保护：请求在途时禁用，后端对排队/执行中也幂等
   try{const updated=await jobs.retry(workspace.selectedJob);
     const queued=updated.status==='queued'||updated.status==='running';
     notify(queued?'已在原任务排队，不会重复创建任务':'重试已提交');
     await refresh();
   }catch(e){notify(e.message,true);retryBtn.disabled=false;}
 });
}
