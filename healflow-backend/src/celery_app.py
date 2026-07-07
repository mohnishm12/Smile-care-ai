from celery import Celery
from celery.schedules import crontab

from src.config import get_settings

settings = get_settings()

celery_app = Celery(
    "healflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["src.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_max_tasks_per_child=100,
    # Fail fast when the broker is down instead of hanging API requests —
    # publish attempts give up after ~2s and the caller treats it as best-effort.
    broker_transport_options={
        "max_retries": 1,
        "interval_start": 0,
        "interval_max": 1,
        "socket_timeout": 2,
        "socket_connect_timeout": 2,
    },
    task_publish_retry=False,
    broker_connection_max_retries=1,
    broker_connection_timeout=2,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "cleanup-expired-sessions": {
        "task": "src.tasks.cleanup_expired_sessions",
        "schedule": crontab(minute=0),  # hourly
    },
}
