import {JobStatus,AttemptStatus,AttemptReason} from '../../constants/enums.js';
import {esc,date} from '../../utils/dom.js';
export const status=v=>'<span class="status '+esc(v)+'">'+esc(JobStatus[v]||v)+'</span>';
export const attemptStatus=v=>'<span class="status attempt '+esc(v)+'">'+esc(AttemptStatus[v]||v)+'</span>';
export const attemptReason=v=>esc(AttemptReason[v]||v||'—');
// 接管徽标：当前或历史尝试发生过失联接管
export const takeoverBadge=j=>{
 const happened=j.taken_over||(j.attempts||[]).some(a=>a.status==='taken_over'||a.reason==='taken_over');
 return happened?'<span class="status takenover" title="原计算进程失联，已由其他进程接管">接管</span>':'';
};
// 一次尝试的时间线行
export const attemptRow=a=>'<tr><td>第 '+a.attempt_no+' 次</td><td>'+attemptReason(a.reason)+'</td><td>'+attemptStatus(a.status)+'</td><td>'+esc(date(a.started_at))+'</td><td>'+(a.finished_at?esc(date(a.finished_at)):'<span class="muted">进行中…</span>')+'</td><td class="attempt-error">'+esc(a.error||'')+'</td></tr>';
