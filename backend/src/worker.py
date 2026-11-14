import json
import logging
import threading
import time
from pathlib import Path

from redis import Redis

from src.config.database import Session
from src.config.settings import REDIS_URL
from src.constants.enums import HEARTBEAT_INTERVAL
from src.models import Dataset, Report
from src.services import scheduler, reports
from src.services.business import analyze
from src.services.reports import deliver
from src.services.audit import record

logging.basicConfig(level=logging.INFO)


class Heartbeat(threading.Thread):
    """独立线程续租：计算本身阻塞也不影响心跳，租约失效后自动停止。"""

    def __init__(self, worker_id, job_id, attempt_no):
        super().__init__(daemon=True)
        self.worker_id = worker_id
        self.job_id = job_id
        self.attempt_no = attempt_no
        self.alive = True
        self.lease_valid = True

    def run(self):
        while self.alive and self.lease_valid:
            time.sleep(HEARTBEAT_INTERVAL)
            if not self.alive:
                break
            try:
                with Session() as db:
                    self.lease_valid = scheduler.heartbeat(
                        db, self.job_id, self.attempt_no, self.worker_id, time.time())
            except Exception:
                logging.exception('Heartbeat failed')
        if not self.lease_valid:
            logging.warning('Lease lost for job %s attempt %s', self.job_id, self.attempt_no)

    def stop(self):
        self.alive = False


def execute(worker_id):
    """从数据库原子领取一个任务并执行；Redis 只负责唤醒，领取以数据库为准。"""
    with Session() as db:
        job, attempt = scheduler.claim_next(db, worker_id, time.time())
        if not job:
            return None  # 通知可能失效或重复，原子领取保证同一复盘不会被两个 worker 重复执行
        # 会话关闭后对象会分离，先把标量字段取出来
        job_id, dataset_id, attempt_no = job.id, job.dataset_id, attempt.attempt_no
        params = job.params
        reason = attempt.reason
    hb = Heartbeat(worker_id, job_id, attempt_no)
    hb.start()
    try:
        with Session() as db:
            record(db, worker_id,
                   'job.taken_over' if reason == 'taken_over' else 'job.taken',
                   {'id': job_id, 'attempt_no': attempt_no, 'reason': reason})
            db.commit()
        try:
            with Session() as db:
                d = db.get(Dataset, dataset_id)
                result = analyze(d.records, params)
            json.dumps(result, allow_nan=False)
            outcome, error = result, None
        except Exception as e:
            logging.exception('Analysis failed')
            outcome, error = None, str(e)[:990]
        # 收尾前先停心跳，避免与最终写入竞争；fencing 校验由 finish_attempt 保证
        hb.stop()
        hb.join(timeout=2)
        with Session() as db:
            accepted = scheduler.finish_attempt(
                db, job_id, attempt_no, worker_id, time.time(),
                result=outcome, error=error)
            if accepted:
                action = 'job.completed' if error is None else 'job.failed'
                detail = {'id': job_id, 'attempt_no': attempt_no}
                if error:
                    detail['error'] = error
                record(db, worker_id, action, detail)
                db.commit()
            else:
                logging.warning('Stale attempt %s of job %s discarded by fencing',
                                attempt_no, job_id)
    finally:
        hb.stop()
    return job_id


def run_due_reports():
    # 多 worker 下用原子领取，避免同一到期简报被重复投递
    now = time.time()
    with Session() as db:
        report = reports.claim_due(db, now)
    if not report:
        return
    rid = report.id
    with Session() as db:
        r = db.get(Report, rid)
        try:
            d = deliver(db, r)
            if d:
                record(db, 'worker', 'report.delivered', {'id': r.id, 'delivery': d.id})
                db.commit()
            else:
                # 结果不再有效（如未批准）：保持推进后的下一个周期，避免反复空转
                db.rollback()
        except Exception:
            logging.exception('Report delivery failed')
            db.rollback()
            # 投递异常：让计划重新到期，下一轮立即重试
            with Session() as db2:
                db2.get(Report, rid).next_run = now
                db2.commit()


def main():
    worker_id = scheduler.new_worker_id()
    logging.info('Worker starting: %s', worker_id)
    # 多 worker 并存：启动时不再无条件重置 running，失联任务由心跳租约超时后接管
    r = Redis.from_url(REDIS_URL, socket_timeout=3)
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            r.blpop('analysis:queue', timeout=1)  # 仅作唤醒信号
            execute(worker_id)                   # 无通知时也会走数据库兜底领取
            run_due_reports()
        except Exception:
            logging.exception('Worker retry')
            time.sleep(2)


if __name__ == '__main__':
    main()
