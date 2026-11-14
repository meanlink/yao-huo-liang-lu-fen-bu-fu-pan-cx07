from enum import Enum
class Role(str, Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'
class JobStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
class AttemptStatus(str, Enum):
    running = 'running'
    succeeded = 'succeeded'
    failed = 'failed'
    taken_over = 'taken_over'
class AttemptReason(str, Enum):
    queued = 'queued'        # 首次排队领取
    retry = 'retry'          # 失败后在原任务上重试
    taken_over = 'taken_over'  # 原 worker 失联，被接管
# worker 心跳间隔与租约超时（秒）
HEARTBEAT_INTERVAL = 5
LEASE_TIMEOUT = 30
