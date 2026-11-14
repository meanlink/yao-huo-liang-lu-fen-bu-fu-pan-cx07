from sqlalchemy import inspect, text, Float, String, Integer
from sqlalchemy.schema import CreateColumn
from sqlalchemy.dialects import postgresql, sqlite
from src.config.database import Base, engine
from src import models

# 老版本 jobs 表需要补齐的调度列（多 worker 租约/接管）
_JOB_ADDED_COLUMNS = {
    'attempt_no': Integer(),
    'worker_id': String(80),
    'heartbeat_at': Float(),
    'queued_at': Float(),
}


def _column_ddl(column, dialect):
    return str(CreateColumn(column).compile(dialect=dialect))


def _add_missing_columns(conn, table, columns):
    existing = {c['name'] for c in inspect(conn).get_columns(table)}
    dialect = conn.dialect
    for name, col_type in columns.items():
        if name not in existing:
            col = models.Job.__table__.c[name]
            ddl = _column_ddl(col, dialect)
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {ddl}'))


def migrate():
    Base.metadata.create_all(engine)
    # create_all 不会修改已存在的表，老库需要幂等补列
    with engine.begin() as conn:
        if inspect(conn).has_table('jobs'):
            _add_missing_columns(conn, 'jobs', _JOB_ADDED_COLUMNS)


if __name__ == '__main__':
    migrate()
