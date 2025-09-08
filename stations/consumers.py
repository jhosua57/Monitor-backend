import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Station
from .services import DockerService
import asyncio
import logging

logger = logging.getLogger(__name__)

class StationStatsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.station_id = self.scope['url_route']['kwargs']['station_id']
        self.station_group_name = f'station_{self.station_id}'
        
        # Join station group
        await self.channel_layer.group_add(
            self.station_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Start sending stats
        self.send_stats_task = asyncio.create_task(self.send_stats_periodically())
    
    async def disconnect(self, close_code):
        # Leave station group
        await self.channel_layer.group_discard(
            self.station_group_name,
            self.channel_name
        )
        
        # Cancel stats task
        if hasattr(self, 'send_stats_task'):
            self.send_stats_task.cancel()
    
    async def send_stats_periodically(self):
        """Enviar estadísticas cada 5 segundos"""
        while True:
            try:
                stats = await self.get_station_stats()
                await self.send(text_data=json.dumps({
                    'type': 'stats_update',
                    'data': stats
                }))
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error sending stats: {str(e)}")
                await asyncio.sleep(10)
    
    @database_sync_to_async
    def get_station_stats(self):
        """Obtener estadísticas de la estación"""
        try:
            station = Station.objects.get(id=self.station_id)
            docker_service = DockerService(station)
            return docker_service.get_containers_stats()
        except Exception as e:
            logger.error(f"Error getting stats for station {self.station_id}: {str(e)}")
            return {}