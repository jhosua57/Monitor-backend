from django.urls import path
from .consumers import StationStatsConsumer

websocket_urlpatterns = [
    path('ws/stations/<int:station_id>/stats/', StationStatsConsumer.as_asgi()),
]