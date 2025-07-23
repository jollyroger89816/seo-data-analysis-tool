#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后台任务管理系统
支持任务队列、状态持久化、重试机制和进度追踪
"""

import os
import json
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import uuid

# 任务状态枚举
class TaskStatus(Enum):
    PENDING = "pending"          # 等待执行
    RUNNING = "running"          # 正在执行
    SUCCESS = "success"          # 执行成功
    FAILED = "failed"            # 执行失败
    CANCELLED = "cancelled"      # 已取消
    RETRY = "retry"              # 等待重试
    PAUSED = "paused"            # 已暂停

@dataclass
class TaskInfo:
    """任务信息数据结构"""
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    progress: int = 0
    total: int = 0
    current_item: str = ""
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3
    retry_delay: int = 75  # 重试间隔秒数（>70秒）
    next_retry_at: Optional[str] = None
    metadata: Dict[str, Any] = None
    results: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.results is None:
            self.results = []

class TaskManager:
    """后台任务管理器"""
    
    def __init__(self, tasks_dir: str = "tasks"):
        self.tasks_dir = os.path.abspath(tasks_dir)
        self.tasks_file = os.path.join(self.tasks_dir, "tasks.json")
        self.running_tasks: Dict[str, threading.Thread] = {}
        self.task_locks: Dict[str, threading.Lock] = {}
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.logger = logging.getLogger(__name__)
        
        # 创建任务存储目录
        os.makedirs(self.tasks_dir, exist_ok=True)
        
        # 初始化任务数据
        self.tasks: Dict[str, TaskInfo] = {}
        self.load_tasks()
        
        # 启动任务调度器
        self.scheduler_thread = threading.Thread(target=self._task_scheduler, daemon=True)
        self.scheduler_running = True
        self.scheduler_thread.start()
        
        self.logger.info("任务管理器已启动")
    
    def _task_scheduler(self):
        """任务调度器，处理重试和恢复任务"""
        while self.scheduler_running:
            try:
                current_time = datetime.now()
                
                # 检查需要重试的任务
                for task_id, task_info in self.tasks.items():
                    if task_info.status == TaskStatus.RETRY:
                        if task_info.next_retry_at:
                            retry_time = datetime.fromisoformat(task_info.next_retry_at)
                            if current_time >= retry_time:
                                self.logger.info(f"任务 {task_id} 开始重试")
                                self._execute_task(task_info)
                
                # 检查是否有未完成的任务需要恢复
                for task_id, task_info in self.tasks.items():
                    if (task_info.status == TaskStatus.RUNNING and 
                        task_id not in self.running_tasks):
                        self.logger.info(f"恢复未完成的任务 {task_id}")
                        self._execute_task(task_info)
                
                time.sleep(10)  # 每10秒检查一次
                
            except Exception as e:
                self.logger.error(f"任务调度器错误: {str(e)}")
                time.sleep(5)
    
    def create_task(self, task_type: str, metadata: Dict[str, Any] = None, 
                   max_retries: int = 3, retry_delay: int = 75) -> str:
        """创建新任务"""
        task_id = f"{task_type}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        task_info = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            max_retries=max_retries,
            retry_delay=retry_delay,
            metadata=metadata or {}
        )
        
        self.tasks[task_id] = task_info
        self.task_locks[task_id] = threading.Lock()
        self.save_tasks()
        
        self.logger.info(f"创建任务 {task_id}, 类型: {task_type}")
        return task_id
    
    def start_task(self, task_id: str, executor_func: Callable, *args, **kwargs) -> bool:
        """启动任务执行"""
        if task_id not in self.tasks:
            self.logger.error(f"任务 {task_id} 不存在")
            return False
        
        task_info = self.tasks[task_id]
        
        if task_info.status != TaskStatus.PENDING:
            self.logger.warning(f"任务 {task_id} 状态不是PENDING，无法启动")
            return False
        
        # 设置任务执行器
        task_info.metadata['executor_func'] = executor_func
        task_info.metadata['executor_args'] = args
        task_info.metadata['executor_kwargs'] = kwargs
        
        self._execute_task(task_info)
        return True
    
    def _execute_task(self, task_info: TaskInfo):
        """执行任务"""
        task_id = task_info.task_id
        
        if task_id in self.running_tasks:
            self.logger.warning(f"任务 {task_id} 正在运行中")
            return
        
        def task_worker():
            try:
                # 更新任务状态
                with self.task_locks[task_id]:
                    task_info.status = TaskStatus.RUNNING
                    task_info.started_at = datetime.now().isoformat()
                    task_info.updated_at = datetime.now().isoformat()
                    self.save_tasks()
                
                self.logger.info(f"任务 {task_id} 开始执行")
                
                # 获取执行器函数
                executor_func = task_info.metadata.get('executor_func')
                executor_args = task_info.metadata.get('executor_args', ())
                executor_kwargs = task_info.metadata.get('executor_kwargs', {})
                
                if not executor_func:
                    raise ValueError("未设置任务执行器")
                
                # 执行任务
                result = executor_func(task_info, *executor_args, **executor_kwargs)
                
                # 任务成功完成
                with self.task_locks[task_id]:
                    task_info.status = TaskStatus.SUCCESS
                    task_info.finished_at = datetime.now().isoformat()
                    task_info.updated_at = datetime.now().isoformat()
                    if result:
                        task_info.results = result
                    self.save_tasks()
                
                self.logger.info(f"任务 {task_id} 执行成功")
                
            except Exception as e:
                self.logger.error(f"任务 {task_id} 执行失败: {str(e)}")
                
                with self.task_locks[task_id]:
                    task_info.error_message = str(e)
                    task_info.updated_at = datetime.now().isoformat()
                    
                    # 检查是否需要重试
                    if task_info.retry_count < task_info.max_retries:
                        task_info.retry_count += 1
                        task_info.status = TaskStatus.RETRY
                        next_retry_time = datetime.now() + timedelta(seconds=task_info.retry_delay)
                        task_info.next_retry_at = next_retry_time.isoformat()
                        self.logger.info(f"任务 {task_id} 将在 {task_info.retry_delay} 秒后重试 "
                                       f"({task_info.retry_count}/{task_info.max_retries})")
                    else:
                        task_info.status = TaskStatus.FAILED
                        task_info.finished_at = datetime.now().isoformat()
                        self.logger.error(f"任务 {task_id} 达到最大重试次数，标记为失败")
                    
                    self.save_tasks()
            
            finally:
                # 清理运行中的任务记录
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
        
        # 启动任务线程
        thread = threading.Thread(target=task_worker, daemon=True)
        self.running_tasks[task_id] = thread
        thread.start()
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id not in self.tasks:
            return False
        
        task_info = self.tasks[task_id]
        
        with self.task_locks[task_id]:
            if task_info.status in [TaskStatus.PENDING, TaskStatus.RETRY]:
                task_info.status = TaskStatus.CANCELLED
                task_info.updated_at = datetime.now().isoformat()
                task_info.finished_at = datetime.now().isoformat()
                self.save_tasks()
                self.logger.info(f"任务 {task_id} 已取消")
                return True
            elif task_info.status == TaskStatus.RUNNING:
                task_info.status = TaskStatus.CANCELLED
                task_info.updated_at = datetime.now().isoformat()
                task_info.finished_at = datetime.now().isoformat()
                # 注意：正在运行的任务需要由执行器检查状态并自行停止
                self.save_tasks()
                self.logger.info(f"任务 {task_id} 已标记为取消")
                return True
        
        return False
    
    def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        if task_id not in self.tasks:
            return False
        
        task_info = self.tasks[task_id]
        
        with self.task_locks[task_id]:
            if task_info.status in [TaskStatus.PENDING, TaskStatus.RETRY]:
                task_info.status = TaskStatus.PAUSED
                task_info.updated_at = datetime.now().isoformat()
                self.save_tasks()
                self.logger.info(f"任务 {task_id} 已暂停")
                return True
        
        return False
    
    def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        if task_id not in self.tasks:
            return False
        
        task_info = self.tasks[task_id]
        
        with self.task_locks[task_id]:
            if task_info.status == TaskStatus.PAUSED:
                task_info.status = TaskStatus.PENDING
                task_info.updated_at = datetime.now().isoformat()
                self.save_tasks()
                self.logger.info(f"任务 {task_id} 已恢复")
                return True
        
        return False
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[TaskInfo]:
        """获取所有任务"""
        return list(self.tasks.values())
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[TaskInfo]:
        """根据状态获取任务"""
        return [task for task in self.tasks.values() if task.status == status]
    
    def get_tasks_by_type(self, task_type: str) -> List[TaskInfo]:
        """根据类型获取任务"""
        return [task for task in self.tasks.values() if task.task_type == task_type]
    
    def update_task_progress(self, task_id: str, progress: int, total: int = None, 
                           current_item: str = None, results: List[Dict[str, Any]] = None):
        """更新任务进度"""
        if task_id not in self.tasks:
            return False
        
        task_info = self.tasks[task_id]
        
        with self.task_locks[task_id]:
            task_info.progress = progress
            if total is not None:
                task_info.total = total
            if current_item is not None:
                task_info.current_item = current_item
            if results is not None:
                task_info.results = results
            task_info.updated_at = datetime.now().isoformat()
            self.save_tasks()
        
        return True
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        if task_id not in self.tasks:
            return False
        
        # 如果任务正在运行，先尝试取消
        if task_id in self.running_tasks:
            self.cancel_task(task_id)
            time.sleep(1)  # 等待取消完成
        
        del self.tasks[task_id]
        if task_id in self.task_locks:
            del self.task_locks[task_id]
        
        self.save_tasks()
        self.logger.info(f"任务 {task_id} 已删除")
        return True
    
    def cleanup_old_tasks(self, days: int = 7):
        """清理旧任务"""
        cutoff_time = datetime.now() - timedelta(days=days)
        tasks_to_delete = []
        
        for task_id, task_info in self.tasks.items():
            if task_info.status in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task_time = datetime.fromisoformat(task_info.updated_at)
                if task_time < cutoff_time:
                    tasks_to_delete.append(task_id)
        
        for task_id in tasks_to_delete:
            self.delete_task(task_id)
        
        self.logger.info(f"清理了 {len(tasks_to_delete)} 个旧任务")
        return len(tasks_to_delete)
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计信息"""
        stats = {
            'total': len(self.tasks),
            'pending': 0,
            'running': 0,
            'success': 0,
            'failed': 0,
            'cancelled': 0,
            'retry': 0,
            'paused': 0
        }
        
        for task_info in self.tasks.values():
            stats[task_info.status.value] += 1
        
        return stats
    
    def save_tasks(self):
        """保存任务到文件"""
        try:
            tasks_data = {}
            for task_id, task_info in self.tasks.items():
                tasks_data[task_id] = asdict(task_info)
                # 转换枚举为字符串
                tasks_data[task_id]['status'] = task_info.status.value
            
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存任务文件失败: {str(e)}")
    
    def load_tasks(self):
        """从文件加载任务"""
        try:
            if os.path.exists(self.tasks_file):
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    tasks_data = json.load(f)
                
                for task_id, task_dict in tasks_data.items():
                    # 转换字符串为枚举
                    task_dict['status'] = TaskStatus(task_dict['status'])
                    task_info = TaskInfo(**task_dict)
                    self.tasks[task_id] = task_info
                    self.task_locks[task_id] = threading.Lock()
                
                self.logger.info(f"加载了 {len(self.tasks)} 个任务")
        except Exception as e:
            self.logger.error(f"加载任务文件失败: {str(e)}")
    
    def shutdown(self):
        """关闭任务管理器"""
        self.scheduler_running = False
        if self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        self.executor.shutdown(wait=True)
        self.logger.info("任务管理器已关闭")

# 全局任务管理器实例
task_manager = TaskManager() 