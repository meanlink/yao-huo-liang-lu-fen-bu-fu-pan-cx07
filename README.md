# 窑火良率分布复盘

描述统计与稳健分布的真实业务分析小型项目。完整模拟客户、痛点、上下游、算法公式与一天工作剧本见 [BUSINESS.md](BUSINESS.md)。

## 模块与业务流程
数据接入（JSON/CSV、字段验证、批次指纹）→ 参数化分析（异步 Python worker）→ 结果复核（指标、图形、明细、解释、批准）→ 定时分发（本地收件箱、CSV/JSON、SHA256）；另有业务总览和审计轨迹。
三个贯穿全栈的实体：Dataset 数据批次、Job 分析任务、Report 分发计划；辅助 User、Audit、Delivery。

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18200；后端文档 http://localhost:19200/docs；数据库宿主端口 17700。
`SEED_DEMO=true` 自动幂等 seed；不覆盖用户修改。手动 seed 命令可重复执行。

## 演示账号与权限
|账号|密码|真实权限|
|---|---|---|
|admin@demo.local|Demo123!|接入、执行、批准、分发、暂停、读取与下载|
|analyst@demo.local|Demo123!|接入、执行、读取与下载；不能批准或安排分发|
|viewer@demo.local|Demo123!|只读与下载|

## 技术与本地开发
Python 3.12 / FastAPI / SQLAlchemy / NumPy / SciPy / scikit-learn；PostgreSQL 16；Redis 7；Nginx；原生 HTML CSS JavaScript ES modules（用户指定）。后端所有校验、持久化和算法在服务端。无前端打包步骤。
后端：安装 backend/requirements.txt，设置 DATABASE_URL、REDIS_URL、JWT_SECRET、ARTIFACT_DIR 后在 backend/ 执行 `python -m migrations.initial`、`python -m scripts.seed_demo`、`uvicorn src.main:app`，另开 `python -m src.worker`。前端使用带 /api 反向代理的 Nginx，直接打开 index.html 不支持 API。

## 目录与工程约定
backend/src/{models,schemas,services,routes,controllers,middlewares,constants,config,utils}；backend/scripts/seed_demo.py；backend/migrations/initial.py。
frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}。
Role 枚举：admin/analyst/viewer；JobStatus：queued/running/completed/failed；AttemptStatus：running/succeeded/failed/taken_over。后端 backend/src/constants/enums.py，前端 frontend/src/constants/enums.js；路由权限在 middlewares/auth.py；页面按相同角色控制操作入口。

## 多计算进程并发调度
可同时运行多个 worker（`docker compose up -d --scale worker=3`，或多次 `python -m src.worker`），通过数据库协同而非 Redis 队列去重：
- 原子领取：`scheduler.claim_next` 用条件 UPDATE 抢占，同一复盘同一时刻只被一个 worker 执行；Redis 仅作唤醒通知，SQL 排队状态是权威兜底。
- 心跳租约：执行中每 5 秒续租（`HEARTBEAT_INTERVAL`），持续心跳的任务不被抢；失联超过 30 秒（`LEASE_TIMEOUT`）才可被其他 worker 接管，启动新 worker 不再打断仍在运行的进程。
- Fencing 令牌：每次领取递增 `attempt_no` 并写 `job_attempts`；旧执行迟回的成功/失败因令牌不匹配被丢弃，不覆盖接管结果。
- 失败重试：失败后在原任务上 `POST /jobs/{id}/retry` 回到排队，连续点击幂等不重复排队；每次尝试（首次排队/失败重试/失联接管）及原因、错误均保留在 attempts。
- 结果门槛：仅 `completed` 且有结果（有效执行发布）才能批准；批准与定时简报只使用有效结果。多 worker 下到期简报也经原子领取，只投递一次。

## 环境变量与 Docker
COMPOSE_PROJECT_NAME=kiln-yield；FRONTEND_PORT=18200；BACKEND_PORT=19200；DB_PORT=17700；DB_PASSWORD、JWT_SECRET 见 .env.example；SEED_DEMO 默认 true。共享命名产物卷供后端下载与 worker 写入，数据库/Redis 各持久卷。
恰好五服务均有健康检查（worker 可水平扩容为多副本）。Redis 仅作唤醒通知，数据库原子领取 + 心跳租约才是排队与去重的权威；worker 按 next_run 原子领取并生成本地收件箱文件，多副本不会重复投递。周期 60 秒至 30 天。分发结果为批准分析的固定快照；若需新数据重新计算并建立新计划。当前不连接邮件或企业聊天。
错误响应、请求编号、Redis 每 IP 每分钟 240 次限流、JWT 和数据库操作审计。演示密钥与密码仅供本机模拟；生产部署前配置独立密钥与账号。

## 数据与验收
所有数据为固定随机种子生成的模拟业务数据，不能作为实际生产决策证据。项目独立算法、输入边界及业务局限详见 BUSINESS.md。测试与截图统一存放 ../../test-artifacts/gb-1001/，源码不含日志/截图/测试报告。
清理本项目演示数据：`docker compose down -v --remove-orphans`（会删除本项目命名卷）。

## License
MIT，见 LICENSE。
