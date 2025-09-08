from django.db import models
from django.contrib.auth.models import User
import json

class Station(models.Model):
    name = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    ssh_user = models.CharField(max_length=50)
    ssh_password = models.CharField(max_length=100)  # En producción usar encriptación
    compose_path = models.CharField(max_length=200, default='/app/docker-compose.yml')
    is_connected = models.BooleanField(default=False)
    last_check = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        unique_together = ['ip_address', 'created_by']

    def __str__(self):
        return f"{self.name} ({self.ip_address})"

class Container(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('paused', 'Paused'),
        ('exited', 'Exited'),
        ('restarting', 'Restarting'),
        ('dead', 'Dead'),
    ]
    
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='containers')
    name = models.CharField(max_length=100)
    container_id = models.CharField(max_length=64)
    image = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    ports = models.TextField(blank=True)
    created_time = models.CharField(max_length=50, blank=True)
    
    # Campos para estadísticas en tiempo real
    cpu_usage = models.FloatField(null=True, blank=True)
    memory_usage = models.FloatField(null=True, blank=True)
    memory_limit = models.BigIntegerField(null=True, blank=True)
    network_rx = models.BigIntegerField(null=True, blank=True)
    network_tx = models.BigIntegerField(null=True, blank=True)
    
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['station', 'name']

    def __str__(self):
        return f"{self.name}@{self.station.name}"

class ContainerAction(models.Model):
    ACTION_CHOICES = [
        ('start', 'Start'),
        ('stop', 'Stop'),
        ('restart', 'Restart'),
        ('pause', 'Pause'),
        ('unpause', 'Unpause'),
        ('remove', 'Remove'),
        ('rebuild', 'Rebuild'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('executing', 'Executing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    
    container = models.ForeignKey(Container, on_delete=models.CASCADE)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    result_message = models.TextField(blank=True)
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    executed_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.action} on {self.container} - {self.status}"

class ActivityLog(models.Model):
    LOG_LEVELS = [
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]
    
    station = models.ForeignKey(Station, on_delete=models.CASCADE, null=True, blank=True)
    container = models.ForeignKey(Container, on_delete=models.CASCADE, null=True, blank=True)
    level = models.CharField(max_length=10, choices=LOG_LEVELS)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.level.upper()}] {self.message[:50]}..."