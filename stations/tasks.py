from celery import shared_task
from django.utils import timezone
from .models import Station, Container, ActivityLog
from .services import DockerService
import logging

logger = logging.getLogger(__name__)

@shared_task
def monitor_stations():
    """Tarea periódica para monitorear todas las estaciones"""
    stations = Station.objects.all()
    
    for station in stations:
        try:
            docker_service = DockerService(station)
            
            # Verificar conexión
            is_connected = docker_service.test_connection()
            was_connected = station.is_connected
            
            station.is_connected = is_connected
            station.last_check = timezone.now()
            station.save()
            
            if is_connected and not was_connected:
                ActivityLog.objects.create(
                    station=station,
                    level='success',
                    message=f'Estación {station.name} reconectada'
                )
            elif not is_connected and was_connected:
                ActivityLog.objects.create(
                    station=station,
                    level='warning',
                    message=f'Estación {station.name} desconectada'
                )
            
            # Si está conectada, actualizar contenedores
            if is_connected:
                try:
                    containers_data = docker_service.get_containers()
                    
                    # Actualizar contenedores existentes
                    for container_data in containers_data:
                        container, created = Container.objects.update_or_create(
                            station=station,
                            name=container_data['name'],
                            defaults={
                                'container_id': container_data['id'],
                                'image': container_data['image'],
                                'status': container_data['status'],
                                'ports': container_data['ports'],
                                'created_time': container_data.get('created', '')
                            }
                        )
                        
                        if created:
                            ActivityLog.objects.create(
                                station=station,
                                container=container,
                                level='info',
                                message=f'Nuevo contenedor detectado: {container.name}'
                            )
                    
                    # Eliminar contenedores que ya no existen
                    existing_names = [c['name'] for c in containers_data]
                    removed_containers = station.containers.exclude(name__in=existing_names)
                    
                    for container in removed_containers:
                        ActivityLog.objects.create(
                            station=station,
                            level='warning',
                            message=f'Contenedor eliminado: {container.name}'
                        )
                        container.delete()
                        
                except Exception as e:
                    logger.error(f"Error updating containers for station {station.id}: {str(e)}")
                    ActivityLog.objects.create(
                        station=station,
                        level='error',
                        message=f'Error actualizando contenedores: {str(e)}'
                    )
        
        except Exception as e:
            logger.error(f"Error monitoring station {station.id}: {str(e)}")
            station.is_connected = False
            station.last_check = timezone.now()
            station.save()

@shared_task
def update_container_stats():
    """Actualizar estadísticas de contenedores cada minuto"""
    stations = Station.objects.filter(is_connected=True)
    
    for station in stations:
        try:
            docker_service = DockerService(station)
            stats = docker_service.get_containers_stats()
            
            for container_name, container_stats in stats.items():
                try:
                    container = station.containers.get(name=container_name)
                    container.cpu_usage = container_stats.get('cpu_percent', 0)
                    container.memory_usage = container_stats.get('memory_usage', 0)
                    container.memory_limit = container_stats.get('memory_limit', 0)
                    container.network_rx = container_stats.get('network_rx', 0)
                    container.network_tx = container_stats.get('network_tx', 0)
                    container.save()
                except Container.DoesNotExist:
                    continue
                    
        except Exception as e:
            logger.error(f"Error updating stats for station {station.id}: {str(e)}")
        