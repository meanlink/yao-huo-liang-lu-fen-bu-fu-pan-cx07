from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Job
from src.schemas.job import JobInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import jobs
from src.services import scheduler
from src.services.audit import record
from src.utils.serialization import job_dict, attempt_dict
router=APIRouter(prefix='/jobs')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [job_dict(j) for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(100))]
@router.post('',status_code=201)
def create(data:JobInput,db=Depends(get_db),u=Depends(can_write)):
    j=jobs.create(db,data,u); record(db,u.email,'job.create',{'id':j.id,'params':j.params})
    db.commit(); jobs.enqueue(j.id); return job_dict(j)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'分析任务不存在')
    payload=job_dict(j)
    attempts=[attempt_dict(a) for a in scheduler.list_attempts(db,id)]
    payload['attempts']=attempts
    payload['taken_over']=any(a['status']=='taken_over' for a in attempts)
    return payload
@router.post('/{id}/retry')
def retry(id:int,db=Depends(get_db),u=Depends(can_write)):
    before=db.get(Job,id)
    if not before: raise HTTPException(404,'分析任务不存在')
    was_failed=before.status=='failed'
    j=jobs.retry(db,id)
    if was_failed:
        record(db,u.email,'job.retry',{'id':id,'attempt_no':j.attempt_no})
        db.commit(); jobs.enqueue(j.id)
    # queued/running 的重复点击幂等返回，不重复排队、不重复写审计
    payload=job_dict(j)
    attempts=[attempt_dict(a) for a in scheduler.list_attempts(db,id)]
    payload['attempts']=attempts
    payload['taken_over']=any(a['status']=='taken_over' for a in attempts)
    return payload
@router.post('/{id}/approve')
def approve(id:int,db=Depends(get_db),u=Depends(admin_only)):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'分析任务不存在')
    # 只有成功尝试（有效执行）发布的结果可被批准；fencing 已保证 result 不被旧执行覆盖
    if j.status!='completed' or not j.result:
        raise HTTPException(409,'仅有效执行发布的完成结果可以批准')
    j.approved=True; record(db,u.email,'job.approve',{'id':id}); db.commit()
    return job_dict(j)
