"""多 worker 并发接单的调度内核。

职责：
- 基于数据库条件 UPDATE 的原子领取，保证同一复盘同一时刻只被一个 worker 执行；
- 心跳租约：持续心跳的执行不会被抢走，失联超过 LEASE_TIMEOUT 才可被接管；
- 每次领取生成 attempt（fencing token），旧执行迟到的成功/失败一律不覆盖接管结果；
- 每次尝试（含首次排队、失败重试、失联接管）都落 job_attempts 留痕。
"""
import os
import socket
import time
import uuid
from sqlalchemy import select, update, or_, and_
from src.models import Job, JobAttempt
from src.constants.enums import LEASE_TIMEOUT, AttemptStatus, AttemptReason
from src.services.audit import record


def new_worker_id():
    return f'{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}'


def _load_job(db, job_id):
    """强制从数据库刷新的 Job 读取，避免 identity map 里 Core UPDATE 前的陈旧实例。"""
    return db.execute(
        select(Job).where(Job.id == job_id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def claim_next(db, worker_id, now):
    """原子领取下一个可执行任务。

    候选：排队中的任务，或心跳已超过租约超时的执行中任务。
    返回 (Job, JobAttempt)；没有可领取任务时返回 (None, None)。
    """
    stale_cutoff = now - LEASE_TIMEOUT
    candidates = list(db.execute(
        select(Job.id, Job.status, Job.attempt_no)
        .where(or_(
            Job.status == 'queued',
            and_(Job.status == 'running', Job.heartbeat_at < stale_cutoff),
        ))
        .order_by(Job.id.asc())
        .limit(5)
    ))
    for job_id, status, prev_attempt_no in candidates:
        next_no = prev_attempt_no + 1
        if status == 'queued':
            cond = and_(Job.id == job_id, Job.status == 'queued')
        else:
            cond = and_(Job.id == job_id, Job.status == 'running',
                        Job.heartbeat_at < stale_cutoff)
        claimed = db.execute(
            update(Job).where(cond).values(
                status='running', attempt_no=next_no, worker_id=worker_id,
                heartbeat_at=now)
        )
        if claimed.rowcount != 1:
            # 被并发 worker 抢先领取或租约刚被刷新，回滚后尝试下一个候选
            db.rollback()
            continue
        if status == 'running':
            # 接管：旧的在途尝试全部标记 taken_over，保留其原因与错误
            db.execute(
                update(JobAttempt)
                .where(JobAttempt.job_id == job_id,
                       JobAttempt.status == AttemptStatus.running)
                .values(status=AttemptStatus.taken_over, finished_at=now)
            )
            reason = AttemptReason.taken_over
        else:
            reason = AttemptReason.retry if prev_attempt_no > 0 else AttemptReason.queued
        attempt = JobAttempt(
            job_id=job_id, attempt_no=next_no, worker_id=worker_id,
            status=AttemptStatus.running, reason=reason,
            started_at=now, heartbeat_at=now)
        db.add(attempt)
        if reason == AttemptReason.taken_over:
            record(db, worker_id, 'job.taken_over',
                   {'id': job_id, 'attempt_no': next_no, 'previous_attempt': prev_attempt_no})
        db.commit()
        return _load_job(db, job_id), attempt
    return None, None


def heartbeat(db, job_id, attempt_no, worker_id, now):
    """续租。返回 False 说明租约已失效（被接管），调用方必须停止本次执行。"""
    touched = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.attempt_no == attempt_no,
               Job.worker_id == worker_id, Job.status == 'running')
        .values(heartbeat_at=now)
    )
    db.execute(
        update(JobAttempt)
        .where(JobAttempt.job_id == job_id, JobAttempt.attempt_no == attempt_no)
        .values(heartbeat_at=now)
    )
    db.commit()
    return touched.rowcount == 1


def finish_attempt(db, job_id, attempt_no, worker_id, now, result=None, error=None):
    """执行收尾，带 fencing 校验。

    只有当前仍持有租约（attempt_no/worker_id 匹配且任务仍在 running）的执行
    才能写入成功或失败；被接管后迟到的旧执行结果直接丢弃，返回 False。
    """
    j = _load_job(db, job_id)
    if (not j or j.attempt_no != attempt_no or j.worker_id != worker_id
            or j.status != 'running'):
        db.rollback()
        return False
    if error is not None:
        j.status = 'failed'
        j.error = (error or '')[:990]
        attempt_status = AttemptStatus.failed
    else:
        j.status = 'completed'
        j.result = result
        j.error = ''
        attempt_status = AttemptStatus.succeeded
    j.heartbeat_at = now
    j.finished_at = now
    db.execute(
        update(JobAttempt)
        .where(JobAttempt.job_id == job_id, JobAttempt.attempt_no == attempt_no)
        .values(status=attempt_status, error=(error or '')[:990], finished_at=now)
    )
    db.commit()
    return True


def list_attempts(db, job_id):
    return list(db.scalars(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id)
        .order_by(JobAttempt.attempt_no.asc())
    ))
