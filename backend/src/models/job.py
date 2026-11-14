from sqlalchemy import String, JSON, Double, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(1000), default='')
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    # 调度归属：只有持租约（attempt_no 匹配）的 worker 才能写结果
    attempt_no: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    heartbeat_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    queued_at: Mapped[float | None] = mapped_column(Double, nullable=True)
class JobAttempt(Base):
    """同一复盘任务的每一次执行尝试，永久保留原因与结果。"""
    __tablename__ = 'job_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default='running')  # running/succeeded/failed/taken_over
    reason: Mapped[str] = mapped_column(String(120), default='')       # queued/retry/taken_over
    error: Mapped[str] = mapped_column(String(1000), default='')
    started_at: Mapped[float] = mapped_column(Double)
    heartbeat_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
