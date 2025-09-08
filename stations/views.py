from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from .models import Station, Container, ContainerAction, ActivityLog
from .serializers import (
    StationSerializer, ContainerSerializer, 
    ContainerActionSerializer, ActivityLogSerializer
)
from .services import DockerService
import logging

logger = logging.getLogger(__name__)

class StationViewSet(viewsets.ModelViewSet):
    serializer_class = StationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Station.objects.filter(created_by=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Probar conexión SSH con la estación"""
        station = self.get_object()
        docker_service = DockerService(station)
        
        try:
            is_connected = docker_service.test_connection()
            station.is_connected = is_connected
            station.last_check = timezone.now()
            station.save()
            
            if is_connected:
                # Crear log de actividad
                ActivityLog.objects.create(
                    station=station,
                    level='success',
                    message=f'Conexión exitosa con {station.name}',
                    created_by=request.user
                )
                return Response({'connected': True, 'message': 'Conexión exitosa'})
            else:
                return Response(
                    {'connected': False, 'message': 'No se pudo conectar'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"Error testing connection to {station.ip_address}: {str(e)}")
            return Response(
                {'connected': False, 'message': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def refresh_containers(self, request, pk=None):
        """Refrescar contenedores de la estación"""
        station = self.get_object()
        docker_service = DockerService(station)
        
        try:
            containers_data = docker_service.get_containers()
            
            with transaction.atomic():
                # Limpiar contenedores existentes
                station.containers.all().delete()
                
                # Crear nuevos contenedores
                for container_data in containers_data:
                    Container.objects.create(
                        station=station,
                        name=container_data['name'],
                        container_id=container_data['id'],
                        image=container_data['image'],
                        status=container_data['status'],
                        ports=container_data['ports'],
                        created_time=container_data.get('created', '')
                    )
                
                station.is_connected = True
                station.last_check = timezone.now()
                station.save()
                
                ActivityLog.objects.create(
                    station=station,
                    level='info',
                    message=f'Contenedores actualizados: {len(containers_data)} encontrados',
                    created_by=request.user
                )
            
            return Response({
                'message': f'Se encontraron {len(containers_data)} contenedores',
                'count': len(containers_data)
            })
            
        except Exception as e:
            logger.error(f"Error refreshing containers for {station.ip_address}: {str(e)}")
            station.is_connected = False
            station.save()
            
            ActivityLog.objects.create(
                station=station,
                level='error',
                message=f'Error actualizando contenedores: {str(e)}',
                created_by=request.user
            )
            
            return Response(
                {'message': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Obtener estadísticas en tiempo real de la estación"""
        station = self.get_object()
        docker_service = DockerService(station)
        
        try:
            stats = docker_service.get_containers_stats()
            
            # Actualizar estadísticas en la base de datos
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
            
            return Response(stats)
            
        except Exception as e:
            logger.error(f"Error getting stats for {station.ip_address}: {str(e)}")
            return Response(
                {'message': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ContainerViewSet(viewsets.ModelViewSet):
    serializer_class = ContainerSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Container.objects.filter(station__created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def execute_action(self, request, pk=None):
        """Ejecutar acción en el contenedor"""
        container = self.get_object()
        action_type = request.data.get('action')
        
        if action_type not in ['start', 'stop', 'restart', 'pause', 'unpause', 'remove', 'rebuild']:
            return Response(
                {'message': 'Acción no válida'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Crear registro de acción
        container_action = ContainerAction.objects.create(
            container=container,
            action=action_type,
            status='pending',
            executed_by=request.user
        )
        
        try:
            docker_service = DockerService(container.station)
            result = docker_service.execute_container_action(container.name, action_type)
            
            if result['success']:
                container_action.status = 'success'
                container_action.result_message = result['message']
                
                # Actualizar estado del contenedor
                if action_type == 'start':
                    container.status = 'running'
                elif action_type == 'stop':
                    container.status = 'stopped'
                elif action_type == 'pause':
                    container.status = 'paused'
                elif action_type == 'remove':
                    container.delete()
                    container_action.save()
                    return Response({'message': 'Contenedor eliminado exitosamente'})
                
                container.save()
                
                ActivityLog.objects.create(
                    station=container.station,
                    container=container,
                    level='success',
                    message=f'Acción {action_type} ejecutada en {container.name}',
                    created_by=request.user
                )
                
            else:
                container_action.status = 'failed'
                container_action.result_message = result['message']
                
                ActivityLog.objects.create(
                    station=container.station,
                    container=container,
                    level='error',
                    message=f'Error ejecutando {action_type} en {container.name}: {result["message"]}',
                    created_by=request.user
                )
            
            container_action.completed_at = timezone.now()
            container_action.save()
            
            return Response({
                'success': result['success'],
                'message': result['message']
            })
            
        except Exception as e:
            container_action.status = 'failed'
            container_action.result_message = str(e)
            container_action.completed_at = timezone.now()
            container_action.save()
            
            logger.error(f"Error executing {action_type} on {container.name}: {str(e)}")
            return Response(
                {'message': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """Obtener logs del contenedor"""
        container = self.get_object()
        lines = request.query_params.get('lines', 100)
        
        try:
            docker_service = DockerService(container.station)
            logs = docker_service.get_container_logs(container.name, lines)
            
            return Response({'logs': logs})
            
        except Exception as e:
            logger.error(f"Error getting logs for {container.name}: {str(e)}")
            return Response(
                {'message': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = ActivityLog.objects.filter(
            station__created_by=self.request.user
        ).select_related('station', 'container')
        
        # Filtros opcionales
        station_id = self.request.query_params.get('station')
        level = self.request.query_params.get('level')
        
        if station_id:
            queryset = queryset.filter(station_id=station_id)
        
        if level:
            queryset = queryset.filter(level=level)
        
        return queryset[:100]  # Limitar a 100 registros más recientes