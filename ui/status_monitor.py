"""
状态监控器
实时跟踪和报告系统运行状态
"""

import time
import asyncio
import psutil
import platform
import os
import logging
import subprocess
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

from core import AccountManager, MonitorEngine
from utils.singleton import Singleton
from utils.logger import get_logger


@dataclass
class PerformanceMetrics:
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_usage_percent: float
    network_sent_mb: float
    network_recv_mb: float


@dataclass
class MonitoringStats:
    total_messages_processed: int
    messages_per_minute: float
    active_monitors: int
    successful_forwards: int
    failed_forwards: int
    ai_calls_made: int
    avg_processing_time_ms: float


@dataclass
class SystemStatus:
    uptime: str
    start_time: datetime
    current_time: datetime
    status: str
    version: str
    
    performance: PerformanceMetrics
    
    monitoring: MonitoringStats
    
    total_accounts: int
    active_accounts: int
    connected_accounts: int
    invalid_accounts: int


class StatusMonitor(metaclass=Singleton):
    
    def __init__(self):
        self.start_time = datetime.now()
        self.logger = get_logger(__name__)
        
        self.message_count = 0
        self.forward_success_count = 0
        self.forward_fail_count = 0
        self.ai_call_count = 0
        self.processing_times: List[float] = []
        
        self.last_network_stats = None
        self.system_platform = platform.system().lower()
        
        self.message_timestamps: List[float] = []
        
        self._initialize_system_monitoring()
        
        self.logger.info(f"状态监控器初始化完成 - 系统: {self.system_platform}")
    
    def _initialize_system_monitoring(self):
        try:
            self.last_network_stats = psutil.net_io_counters()
            self.logger.debug("网络监控初始化成功")
            
            if self.system_platform == 'linux':
                self._check_linux_permissions()
                
        except Exception as e:
            self.logger.warning(f"系统监控初始化时出现问题: {e}")
            self.last_network_stats = None
    
    def _check_linux_permissions(self):
        try:
            critical_paths = ['/', '/proc', '/sys']
            for path in critical_paths:
                if os.path.exists(path) and os.access(path, os.R_OK):
                    self.logger.debug(f"路径 {path} 可访问")
                else:
                    self.logger.warning(f"路径 {path} 不可访问或不存在")
                    
            try:
                psutil.cpu_count()
                psutil.virtual_memory()
                self.logger.debug("psutil基本功能检查通过")
            except Exception as psutil_error:
                self.logger.warning(f"psutil功能检查失败: {psutil_error}")
                
        except Exception as e:
            self.logger.warning(f"Linux权限检查失败: {e}")
    
    def get_uptime(self) -> str:
        uptime = datetime.now() - self.start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}天 {hours}小时 {minutes}分钟"
        elif hours > 0:
            return f"{hours}小时 {minutes}分钟"
        else:
            return f"{minutes}分钟"
    
    def record_message_processed(self, processing_time_ms: float = None):
        self.message_count += 1
        current_time = time.time()
        self.message_timestamps.append(current_time)
        
        if processing_time_ms is not None:
            self.processing_times.append(processing_time_ms)
            if len(self.processing_times) > 100:
                self.processing_times.pop(0)
        
        cutoff_time = current_time - 3600
        self.message_timestamps = [ts for ts in self.message_timestamps if ts > cutoff_time]
    
    def record_forward_result(self, success: bool):
        if success:
            self.forward_success_count += 1
        else:
            self.forward_fail_count += 1
    
    def record_ai_call(self):
        self.ai_call_count += 1
    
    def get_messages_per_minute(self) -> float:
        if not self.message_timestamps:
            return 0.0
        
        current_time = time.time()
        minute_ago = current_time - 60
        recent_messages = [ts for ts in self.message_timestamps if ts > minute_ago]
        
        return len(recent_messages)
    
    def get_performance_metrics(self) -> PerformanceMetrics:
        try:
            if self.system_platform == 'linux':
                cpu_percent = self._get_linux_cpu_info()
                memory_percent, memory_used_mb, memory_total_mb = self._get_linux_memory_info()
                disk_usage_percent = self._get_linux_disk_info()
                network_sent_mb, network_recv_mb = self._get_linux_network_info()
                
            else:
                cpu_percent = self._get_generic_cpu_info()
                memory_percent, memory_used_mb, memory_total_mb = self._get_generic_memory_info()
                disk_usage_percent = self._get_generic_disk_info()
                network_sent_mb, network_recv_mb = self._get_generic_network_info()
            
            cpu_percent = max(0.0, min(100.0, cpu_percent))
            memory_percent = max(0.0, min(100.0, memory_percent))
            disk_usage_percent = max(0.0, min(100.0, disk_usage_percent))
            memory_used_mb = max(0.0, memory_used_mb)
            memory_total_mb = max(1.0, memory_total_mb)
            network_sent_mb = max(0.0, network_sent_mb)
            network_recv_mb = max(0.0, network_recv_mb)
            
            return PerformanceMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
                disk_usage_percent=disk_usage_percent,
                network_sent_mb=network_sent_mb,
                network_recv_mb=network_recv_mb
            )
            
        except Exception as e:
            self.logger.error(f"获取性能指标时发生严重错误: {e}")
            return PerformanceMetrics(
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                memory_total_mb=1024.0,
                disk_usage_percent=0.0,
                network_sent_mb=0.0,
                network_recv_mb=0.0
            )
    
    def get_monitoring_stats(self) -> MonitoringStats:
        monitor_engine = MonitorEngine()
        engine_stats = monitor_engine.get_statistics()
        
        avg_processing_time = 0.0
        if self.processing_times:
            avg_processing_time = sum(self.processing_times) / len(self.processing_times)
        
        return MonitoringStats(
            total_messages_processed=self.message_count,
            messages_per_minute=self.get_messages_per_minute(),
            active_monitors=engine_stats['total_monitors'],
            successful_forwards=self.forward_success_count,
            failed_forwards=self.forward_fail_count,
            ai_calls_made=self.ai_call_count,
            avg_processing_time_ms=avg_processing_time
        )
    
    async def get_account_stats(self) -> tuple[int, int, int, int]:
        account_manager = AccountManager()
        accounts = account_manager.list_accounts()
        
        total = len(accounts)
        active = 0
        connected = 0
        invalid = 0
        
        for acc in accounts:
            is_valid, status = await acc.check_validity()
            if is_valid:
                if acc.monitor_active:
                    active += 1
                if acc.is_connected():
                    connected += 1
            else:
                invalid += 1
        
        return total, active, connected, invalid
    
    async def get_system_status(self) -> SystemStatus:
        current_time = datetime.now()
        total_accounts, active_accounts, connected_accounts, invalid_accounts = await self.get_account_stats()
        
        if total_accounts == 0:
            status = "未配置"
        elif active_accounts == 0:
            status = "已停止"
        elif invalid_accounts > 0:
            status = "部分失效"
        elif connected_accounts < total_accounts:
            status = "部分连接"
        else:
            status = "运行中"
        
        return SystemStatus(
            uptime=self.get_uptime(),
            start_time=self.start_time,
            current_time=current_time,
            status=status,
            version="2.0.0",
            performance=self.get_performance_metrics(),
            monitoring=self.get_monitoring_stats(),
            total_accounts=total_accounts,
            active_accounts=active_accounts,
            connected_accounts=connected_accounts,
            invalid_accounts=invalid_accounts
        )
    
    async def get_status_dict(self) -> Dict[str, Any]:
        status = await self.get_system_status()
        return asdict(status)
    
    async def get_health_check(self) -> Dict[str, Any]:
        status = await self.get_system_status()
        performance = status.performance
        
        health_score = 100
        warnings = []
        
        if performance.cpu_percent > 80:
            health_score -= 20
            warnings.append("CPU使用率过高")
        elif performance.cpu_percent > 60:
            health_score -= 10
            warnings.append("CPU使用率较高")
        
        if performance.memory_percent > 90:
            health_score -= 25
            warnings.append("内存使用率过高")
        elif performance.memory_percent > 75:
            health_score -= 15
            warnings.append("内存使用率较高")
        
        if status.connected_accounts < status.total_accounts:
            health_score -= 15
            warnings.append("部分账号未连接")
        
        total_forwards = status.monitoring.successful_forwards + status.monitoring.failed_forwards
        if total_forwards > 0:
            success_rate = status.monitoring.successful_forwards / total_forwards
            if success_rate < 0.8:
                health_score -= 20
                warnings.append("转发成功率较低")
        
        if health_score >= 90:
            health_status = "优秀"
        elif health_score >= 70:
            health_status = "良好"
        elif health_score >= 50:
            health_status = "一般"
        else:
            health_status = "需要关注"
        
        return {
            "health_score": max(0, health_score),
            "health_status": health_status,
            "warnings": warnings,
            "timestamp": datetime.now().isoformat()
        }
    
    async def generate_daily_report(self) -> Dict[str, Any]:
        status = await self.get_system_status()
        
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "uptime": status.uptime,
            "messages_processed": status.monitoring.total_messages_processed,
            "successful_forwards": status.monitoring.successful_forwards,
            "failed_forwards": status.monitoring.failed_forwards,
            "ai_calls": status.monitoring.ai_calls_made,
            "avg_processing_time": status.monitoring.avg_processing_time_ms,
            "peak_cpu": max(status.performance.cpu_percent, 0),
            "peak_memory": max(status.performance.memory_percent, 0),
            "active_monitors": status.monitoring.active_monitors
        } 

    def _get_linux_cpu_info(self) -> float:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            if cpu_percent == 0.0 or cpu_percent > 100.0:
                cpu_percent = psutil.cpu_percent(interval=0.5)
                
            if cpu_percent == 0.0:
                try:
                    with open('/proc/loadavg', 'r') as f:
                        load_avg = float(f.readline().split()[0])
                        cpu_count = psutil.cpu_count() or 1
                        cpu_percent = min(100.0, (load_avg / cpu_count) * 100)
                except Exception:
                    pass
                    
            return max(0.0, min(100.0, cpu_percent))
            
        except Exception as e:
            self.logger.warning(f"Linux CPU信息获取失败: {e}")
            return 0.0
    
    def _get_linux_memory_info(self) -> tuple[float, float, float]:
        try:
            memory = psutil.virtual_memory()
            return (
                memory.percent,
                memory.used / (1024 * 1024),
                memory.total / (1024 * 1024)
            )
        except Exception as e:
            self.logger.warning(f"Linux内存信息获取失败: {e}")
            try:
                with open('/proc/meminfo', 'r') as f:
                    lines = f.readlines()
                    mem_info = {}
                    for line in lines:
                        if ':' in line:
                            key, value = line.split(':', 1)
                            mem_info[key.strip()] = int(value.strip().split()[0]) * 1024
                    
                    total = mem_info.get('MemTotal', 1024*1024*1024)
                    available = mem_info.get('MemAvailable', mem_info.get('MemFree', total//2))
                    used = total - available
                    
                    percent = (used / total) * 100
                    return (
                        percent,
                        used / (1024 * 1024),
                        total / (1024 * 1024)
                    )
            except Exception:
                pass
            
            return (0.0, 0.0, 1024.0)
    
    def _get_linux_disk_info(self) -> float:
        try:
            mount_points = ['/', '/home', '/var', '/tmp']
            
            for mount_point in mount_points:
                try:
                    if os.path.exists(mount_point) and os.access(mount_point, os.R_OK):
                        disk = psutil.disk_usage(mount_point)
                        return (disk.used / disk.total) * 100
                except Exception:
                    continue
            
            try:
                import shutil
                total, used, free = shutil.disk_usage('/')
                return (used / total) * 100
            except Exception:
                pass
                
            try:
                import subprocess
                result = subprocess.run(['df', '/'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) >= 2:
                        fields = lines[1].split()
                        if len(fields) >= 5:
                            used_percent = fields[4].rstrip('%')
                            return float(used_percent)
            except Exception:
                pass
                
            return 0.0
            
        except Exception as e:
            self.logger.warning(f"Linux磁盘信息获取失败: {e}")
            return 0.0
    
    def _get_linux_network_info(self) -> tuple[float, float]:
        try:
            current_network = psutil.net_io_counters()
            
            if current_network and self.last_network_stats:
                sent_diff = max(0, current_network.bytes_sent - self.last_network_stats.bytes_sent)
                recv_diff = max(0, current_network.bytes_recv - self.last_network_stats.bytes_recv)
                
                self.last_network_stats = current_network
                
                return (
                    sent_diff / (1024 * 1024),
                    recv_diff / (1024 * 1024)
                )
            else:
                if current_network:
                    self.last_network_stats = current_network
                return (0.0, 0.0)
                
        except Exception as e:
            self.logger.warning(f"Linux网络信息获取失败: {e}")
            try:
                self.last_network_stats = psutil.net_io_counters()
            except Exception:
                pass
            return (0.0, 0.0) 

    def _get_generic_cpu_info(self) -> float:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            if cpu_percent == 0.0:
                cpu_percent = psutil.cpu_percent(interval=0.5)
            return max(0.0, min(100.0, cpu_percent))
        except Exception as e:
            self.logger.warning(f"通用CPU信息获取失败: {e}")
            return 0.0
    
    def _get_generic_memory_info(self) -> tuple[float, float, float]:
        try:
            memory = psutil.virtual_memory()
            return (
                memory.percent,
                memory.used / (1024 * 1024),
                memory.total / (1024 * 1024)
            )
        except Exception as e:
            self.logger.warning(f"通用内存信息获取失败: {e}")
            return (0.0, 0.0, 1024.0)
    
    def _get_generic_disk_info(self) -> float:
        try:
            if self.system_platform == 'windows':
                disk_path = 'C:\\'
            else:
                disk_path = '/'
            
            disk = psutil.disk_usage(disk_path)
            return (disk.used / disk.total) * 100
        except Exception as e:
            self.logger.warning(f"通用磁盘信息获取失败: {e}")
            return 0.0
    
    def _get_generic_network_info(self) -> tuple[float, float]:
        try:
            current_network = psutil.net_io_counters()
            
            if current_network and self.last_network_stats:
                sent_diff = max(0, current_network.bytes_sent - self.last_network_stats.bytes_sent)
                recv_diff = max(0, current_network.bytes_recv - self.last_network_stats.bytes_recv)
                
                self.last_network_stats = current_network
                
                return (
                    sent_diff / (1024 * 1024),
                    recv_diff / (1024 * 1024)
                )
            else:
                if current_network:
                    self.last_network_stats = current_network
                return (0.0, 0.0)
                
        except Exception as e:
            self.logger.warning(f"通用网络信息获取失败: {e}")
            return (0.0, 0.0) 