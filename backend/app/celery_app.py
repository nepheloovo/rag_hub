"""Celery 应用与任务注册"""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "rag_zhongtai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    # macOS spawn 模式下 prefork 池触发 Celery fast_trace_task 上游 bug；
    # 本项目任务以网络 I/O 为主（OCR/Embedding/LLM API），线程池更合适。
    worker_pool="threads",
    worker_concurrency=4,
)
