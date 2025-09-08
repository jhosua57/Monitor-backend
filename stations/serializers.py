from rest_framework import serializers
from .models import Station, Container, ContainerAction, ActivityLog

class ContainerSerializer(serializers.ModelSerializer):
    cpu_percentage = serializers.SerializerMethodField()
    memory_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Container
        fields = '__all__'
    
    def get_cpu_percentage(self, obj):
        return round(obj.cpu_usage or 0, 2)
    
    def get_memory_percentage(self, obj):
        if obj.memory_usage and obj.memory_limit:
            return round((obj.memory_usage / obj.memory_limit) * 100, 2)
        return 0

class StationSerializer(serializers.ModelSerializer):
    containers = ContainerSerializer(many=True, read_only=True)
    container_count = serializers.SerializerMethodField()
    running_containers = serializers.SerializerMethodField()
    
    class Meta:
        model = Station
        fields = ['id', 'name', 'ip_address', 'ssh_user', 'compose_path', 
                  'is_connected', 'last_check', 'containers', 'container_count',
                  'running_containers', 'created_at', 'updated_at']
        extra_kwargs = {
            'ssh_password': {'write_only': True}
        }
    
    def get_container_count(self, obj):
        return obj.containers.count()
    
    def get_running_containers(self, obj):
        return obj.containers.filter(status='running').count()

class ContainerActionSerializer(serializers.ModelSerializer):
    container_name = serializers.CharField(source='container.name', read_only=True)
    station_name = serializers.CharField(source='container.station.name', read_only=True)
    
    class Meta:
        model = ContainerAction
        fields = '__all__'

class ActivityLogSerializer(serializers.ModelSerializer):
    station_name = serializers.CharField(source='station.name', read_only=True)
    container_name = serializers.CharField(source='container.name', read_only=True)
    
    class Meta:
        model = ActivityLog
        fields = '__all__'