import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'docker_monitor.settings')

app = Celery('docker_monitor')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Configuración de Celery
app.conf.update(
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/0',
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Programación de tareas
app.conf.beat_schedule = {
    'monitor-stations': {
        'task': 'stations.tasks.monitor_stations',
        'schedule': 60.0,  # cada 60 segundos
    },
    'update-container-stats': {
        'task': 'stations.tasks.update_container_stats',
        'schedule': 30.0,  # cada 30 segundos
    },
}

app.autodiscover_tasks()