import time
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services.business import metadata
def create(db, data, user):
    if not db.get(Dataset,data.dataset_id): raise HTTPException(404,'数据批次不存在')
    allowed={p['key']:p for p in metadata().get('parameters',[])}
    if set(data.params)-set(allowed): raise HTTPException(422,'包含未知分析参数')
    params={k:p['default'] for k,p in allowed.items()}
    params.update(data.params)
    for key,p in allowed.items():
        v=params[key]
        if p['type']=='number':
            try:
                v=float(v)
                if not (p.get('min',-1e9)<=v<=p.get('max',1e9)): raise ValueError()
                params[key]=v
            except (ValueError,TypeError): raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options',[])]:
            raise HTTPException(422,f'{p["label"]} 不是有效选项')
    now=time.time()
    j=Job(name=data.name, dataset_id=data.dataset_id, params=params, created_by=user.id,
          created_at=now, status='queued', attempt_no=0, queued_at=now)
    db.add(j); db.flush()
    return j
def retry(db, job_id):
    """失败后在原任务上重试；排队/执行中的重复点击幂等，不重复排队。"""
    j=db.get(Job,job_id)
    if not j: raise HTTPException(404,'分析任务不存在')
    if j.status=='completed': raise HTTPException(409,'已完成的任务无需重试')
    if j.status in ('queued','running'):
        return j  # 已有有效尝试在排队或执行，连续点击不产生新队列
    # failed -> 回到排队，保留历史 attempts，不清空错误直到下一次尝试结束
    now=time.time()
    j.status='queued'; j.worker_id=None; j.heartbeat_at=None; j.queued_at=now
    return j
def enqueue(job_id):
    try:
        r=Redis.from_url(REDIS_URL); r.rpush('analysis:queue',job_id); r.close()
    except Exception:
        pass # Redis 仅作唤醒通知，数据库排队状态才是权威兜底
