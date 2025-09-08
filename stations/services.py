import paramiko
import re
import json
import yaml
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class DockerService:
    """Servicio para interactuar con Docker en estaciones remotas"""
    
    def __init__(self, station):
        self.station = station
        self.ssh_client = None
    
    def _connect_ssh(self):
        """Establecer conexión SSH"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(
                self.station.ip_address,
                username=self.station.ssh_user,
                password=self.station.ssh_password,
                timeout=10
            )
            return True
        except Exception as e:
            logger.error(f"SSH connection failed to {self.station.ip_address}: {str(e)}")
            return False
    
    def _disconnect_ssh(self):
        """Cerrar conexión SSH"""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
    
    def _execute_command(self, command: str) -> Dict:
        """Ejecutar comando SSH"""
        if not self.ssh_client:
            if not self._connect_ssh():
                return {'success': False, 'output': '', 'error': 'SSH connection failed'}
        
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            
            return {
                'success': exit_status == 0,
                'output': output,
                'error': error,
                'exit_status': exit_status
            }
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            return {'success': False, 'output': '', 'error': str(e)}
    
    def test_connection(self) -> bool:
        """Probar conexión y disponibilidad de Docker"""
        if not self._connect_ssh():
            return False
        
        # Verificar que Docker esté disponible
        result = self._execute_command("docker --version")
        self._disconnect_ssh()
        
        return result['success']
    
    def get_containers(self) -> List[Dict]:
        """Obtener lista de contenedores"""
        command = "docker ps -a --format 'table {{.Names}}|{{.Status}}|{{.Image}}|{{.Ports}}|{{.ID}}|{{.CreatedAt}}' --no-trunc"
        result = self._execute_command(command)
        
        if not result['success']:
            raise Exception(f"Failed to get containers: {result['error']}")
        
        containers = []
        lines = result['output'].split('\n')
        
        # Omitir header
        if len(lines) > 1:
            for line in lines[1:]:
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 6:
                        name = parts[0].strip()
                        status = parts[1].strip()
                        image = parts[2].strip()
                        ports = parts[3].strip()
                        container_id = parts[4].strip()
                        created = parts[5].strip()
                        
                        # Determinar estado normalizado
                        if status.startswith('Up'):
                            normalized_status = 'running'
                        elif status.startswith('Exited'):
                            normalized_status = 'exited'
                        elif 'Paused' in status:
                            normalized_status = 'paused'
                        else:
                            normalized_status = 'unknown'
                        
                        containers.append({
                            'name': name,
                            'id': container_id,
                            'image': image,
                            'status': normalized_status,
                            'ports': ports,
                            'created': created
                        })
        
        self._disconnect_ssh()
        return containers
    
    def get_containers_stats(self) -> Dict:
        """Obtener estadísticas en tiempo real de contenedores"""
        command = "docker stats --no-stream --format 'table {{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}'"
        result = self._execute_command(command)
        
        if not result['success']:
            raise Exception(f"Failed to get container stats: {result['error']}")
        
        stats = {}
        lines = result['output'].split('\n')
        
        # Omitir header
        if len(lines) > 1:
            for line in lines[1:]:
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 5:
                        name = parts[0].strip()
                        cpu_percent = self._parse_percentage(parts[1].strip())
                        memory_usage = self._parse_memory(parts[2].strip())
                        network_io = self._parse_network_io(parts[3].strip())
                        
                        stats[name] = {
                            'cpu_percent': cpu_percent,
                            'memory_usage': memory_usage.get('usage', 0),
                            'memory_limit': memory_usage.get('limit', 0),
                            'network_rx': network_io.get('rx', 0),
                            'network_tx': network_io.get('tx', 0),
                        }
        
        self._disconnect_ssh()
        return stats
    
    def _parse_percentage(self, percentage_str: str) -> float:
        """Parsear porcentaje de CPU"""
        try:
            return float(percentage_str.replace('%', ''))
        except:
            return 0.0
    
    def _parse_memory(self, memory_str: str) -> Dict:
        """Parsear uso de memoria"""
        try:
            # Formato: "1.5GiB / 2GiB"
            parts = memory_str.split(' / ')
            if len(parts) == 2:
                usage = self._parse_size_to_bytes(parts[0])
                limit = self._parse_size_to_bytes(parts[1])
                return {'usage': usage, 'limit': limit}
        except:
            pass
        return {'usage': 0, 'limit': 0}
    
    def _parse_network_io(self, network_str: str) -> Dict:
        """Parsear I/O de red"""
        try:
            # Formato: "1.2MB / 800kB"
            parts = network_str.split(' / ')
            if len(parts) == 2:
                rx = self._parse_size_to_bytes(parts[0])
                tx = self._parse_size_to_bytes(parts[1])
                return {'rx': rx, 'tx': tx}
        except:
            pass
        return {'rx': 0, 'tx': 0}
    
    def _parse_size_to_bytes(self, size_str: str) -> int:
        """Convertir tamaño a bytes"""
        size_str = size_str.strip()
        multipliers = {
            'B': 1,
            'kB': 1024,
            'MB': 1024**2,
            'GB': 1024**3,
            'TB': 1024**4,
            'KiB': 1024,
            'MiB': 1024**2,
            'GiB': 1024**3,
            'TiB': 1024**4,
        }
        
        for unit, multiplier in multipliers.items():
            if size_str.endswith(unit):
                try:
                    value = float(size_str[:-len(unit)])
                    return int(value * multiplier)
                except:
                    break
        
        try:
            return int(float(size_str))
        except:
            return 0
    
    def execute_container_action(self, container_name: str, action: str) -> Dict:
        """Ejecutar acción en contenedor"""
        compose_dir = self.station.compose_path.rsplit('/', 1)[0]
        
        command_map = {
            'start': f"cd {compose_dir} && docker-compose up -d {container_name} 2>/dev/null || docker start {container_name}",
            'stop': f"docker stop {container_name}",
            'restart': f"docker restart {container_name}",
            'pause': f"docker pause {container_name}",
            'unpause': f"docker unpause {container_name}",
            'remove': f"docker stop {container_name} && docker rm -f {container_name}",
            'rebuild': f"cd {compose_dir} && docker-compose up --build -d {container_name} 2>/dev/null || (docker stop {container_name} && docker rm {container_name} && docker-compose up -d {container_name})"
        }
        
        if action not in command_map:
            return {'success': False, 'message': f'Unknown action: {action}'}
        
        result = self._execute_command(command_map[action])
        self._disconnect_ssh()
        
        if result['success']:
            return {'success': True, 'message': f'Action {action} completed successfully'}
        else:
            return {'success': False, 'message': result['error'] or 'Action failed'}
    
    def get_container_logs(self, container_name: str, lines: int = 100) -> str:
        """Obtener logs de contenedor"""
        compose_dir = self.station.compose_path.rsplit('/', 1)[0]
        command = f"cd {compose_dir} && docker-compose logs --tail={lines} {container_name} 2>/dev/null || docker logs --tail={lines} {container_name}"
        
        result = self._execute_command(command)
        self._disconnect_ssh()
        
        if result['success']:
            return result['output']
        else:
            raise Exception(f"Failed to get logs: {result['error']}")