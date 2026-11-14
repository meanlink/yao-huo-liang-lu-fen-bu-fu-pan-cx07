import time, os, csv, io, hashlib, json
from fastapi import HTTPException
from sqlalchemy import select, update
from src.models import Job, Report, Delivery
from src.config.settings import ARTIFACT_DIR
def claim_due(db, now):
    """原子领取一个到期计划：条件 UPDATE 推进 next_run，多 worker 下只被领取一次。

    用实时到期条件（next_run<=now）而非快照读出的具体值做锁，
    与任务领取同构，避免快照隔离下并发事务用旧值重复匹配。
    """
    rows=list(db.execute(
        select(Report.id).where(Report.enabled==True, Report.next_run<=now)
        .order_by(Report.id.asc()).limit(1)
    ))
    if not rows:
        return None
    rid=rows[0][0]
    interval=db.get(Report,rid).interval_seconds
    moved=db.execute(
        update(Report).where(Report.id==rid, Report.enabled==True, Report.next_run<=now)
        .values(next_run=now+interval)
    )
    if moved.rowcount!=1:
        db.rollback()
        return None
    db.commit()
    return db.get(Report,rid)
def create(db, data):
    j=db.get(Job,data.job_id)
    if not j or j.status!='completed' or not j.result or not j.approved:
        raise HTTPException(409,'请先选择已完成且获批准的有效分析结果')
    r=Report(name=data.name, job_id=j.id, destination=data.destination, interval_seconds=data.interval_seconds, next_run=time.time()+data.delay_seconds, enabled=True)
    db.add(r); db.flush()
    return r
def deliver(db, report):
    j=db.get(Job,report.job_id)
    # 仅有效执行发布的结果可进入简报；fencing 保证 result 不被失联旧执行覆盖
    if not j or j.status!='completed' or not j.result or not j.approved: return
    out=io.StringIO()
    out.write('\ufeff')
    table=j.result.get('table',{})
    cols=table.get('columns',[])
    writer=csv.writer(out)
    def safe(v):
        if isinstance(v,(int,float)) and not isinstance(v,bool): return v
        text=str(v)
        return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
    writer.writerow([safe(c['label']) for c in cols])
    for row in table.get('rows',[]): writer.writerow([safe(row.get(c['key'],'')) for c in cols])
    data=out.getvalue().encode('utf-8')
    delivery=Delivery(report_id=report.id, created_at=time.time(), checksum=hashlib.sha256(data).hexdigest(), filename='', destination=report.destination)
    db.add(delivery); db.flush()
    delivery.filename=f'report-{report.id}-delivery-{delivery.id}.csv'
    os.makedirs(ARTIFACT_DIR,exist_ok=True)
    with open(os.path.join(ARTIFACT_DIR,delivery.filename),'wb') as f:f.write(data)
    with open(os.path.join(ARTIFACT_DIR,delivery.filename+'.json'),'w') as f: json.dump({'job':j.name,'params':j.params,'result':j.result,'checksum':delivery.checksum},f,ensure_ascii=False,allow_nan=False)
    return delivery
