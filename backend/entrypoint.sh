#!/bin/sh
# 等待数据库就绪并确保 pgvector 扩展存在，然后执行启动命令
set -e

echo "[entrypoint] waiting for database..."
python - <<'PY'
import time

from app.config import settings

url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
for i in range(60):
    try:
        import psycopg
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()
        print("[entrypoint] database ready, vector extension ensured")
        break
    except Exception as e:  # noqa: BLE001
        if i >= 59:
            raise
        print(f"[entrypoint] waiting ({i + 1}/60): {type(e).__name__}")
        time.sleep(2)
PY

exec "$@"
