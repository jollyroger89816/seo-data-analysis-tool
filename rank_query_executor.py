#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排名查询任务执行器
支持后台任务系统的排名查询功能
"""

import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from task_manager import TaskInfo, TaskStatus, task_manager
from session_manager import session_manager
import requests
import random
from urllib.parse import quote


class RankQueryExecutor:
    """排名查询任务执行器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def query_chinaz_rank(self, domain: str, keyword: str, api_key: str) -> Dict[str, Any]:
        """
        查询站长之家排名
        """
        try:
            # 构建请求URL
            url = f"https://apidatav2.chinaz.com/CallAPI/BaiduRank"
            
            # 请求参数
            params = {
                'key': api_key,
                'url': domain,
                'word': keyword
            }
            
            # 发送请求
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # 解析响应
            data = response.json()
            
            if data.get('StateCode') == 1:
                # 成功获取数据
                result_data = data.get('Result', {})
                
                # 提取排名信息
                if result_data.get('RankNum', 0) > 0:
                    rank_num = result_data.get('RankNum', 0)
                    
                    # 转换排名显示格式
                    if rank_num == 0:
                        rank_display = "未上榜"
                    elif 1 <= rank_num <= 3:
                        rank_display = f"1页第{rank_num}名"
                    else:
                        page = (rank_num - 1) // 10 + 1
                        position = rank_num % 10
                        if position == 0:
                            position = 10
                        rank_display = f"{page}页第{position}名"
                    
                    return {
                        'rank': rank_display,
                        'rank_num': rank_num,
                        'title': result_data.get('Title', ''),
                        'url': result_data.get('Url', ''),
                        'site_count': result_data.get('AllNum', 0),
                        'success': True
                    }
                else:
                    return {
                        'rank': '未找到',
                        'rank_num': 0,
                        'title': '',
                        'url': '',
                        'site_count': result_data.get('AllNum', 0),
                        'success': True
                    }
            else:
                # API返回错误
                error_msg = data.get('Message', '查询失败')
                return {
                    'rank': '查询失败',
                    'rank_num': 0,
                    'title': '',
                    'url': '',
                    'site_count': 0,
                    'success': False,
                    'error': error_msg
                }
                
        except requests.exceptions.Timeout:
            return {
                'rank': '查询超时',
                'rank_num': 0,
                'title': '',
                'url': '',
                'site_count': 0,
                'success': False,
                'error': '查询超时'
            }
        except requests.exceptions.RequestException as e:
            return {
                'rank': '网络错误',
                'rank_num': 0,
                'title': '',
                'url': '',
                'site_count': 0,
                'success': False,
                'error': f'网络错误: {str(e)}'
            }
        except Exception as e:
            return {
                'rank': '查询异常',
                'rank_num': 0,
                'title': '',
                'url': '',
                'site_count': 0,
                'success': False,
                'error': f'查询异常: {str(e)}'
            }
    
    def execute_rank_query_task(self, task_info: TaskInfo) -> List[Dict[str, Any]]:
        """
        执行排名查询任务
        """
        try:
            # 获取任务参数
            keywords_data = task_info.metadata.get('keywords_data', [])
            api_key = task_info.metadata.get('api_key', '')
            
            if not keywords_data:
                raise ValueError("缺少关键词数据")
            
            if not api_key:
                raise ValueError("缺少API密钥")
            
            total_queries = len(keywords_data)
            results = []
            successful_queries = 0
            failed_queries = 0
            
            # 更新任务开始状态
            task_manager.update_task_progress(
                task_info.task_id, 
                progress=0, 
                total=total_queries,
                current_item="开始排名查询..."
            )
            
            self.logger.info(f"开始执行排名查询任务 {task_info.task_id}，总数量: {total_queries}")
            
            for i, keyword_item in enumerate(keywords_data):
                # 检查任务是否被取消
                current_task = task_manager.get_task(task_info.task_id)
                if current_task and current_task.status == TaskStatus.CANCELLED:
                    self.logger.info(f"任务 {task_info.task_id} 已被取消")
                    break
                
                try:
                    # 获取查询参数
                    domain = keyword_item.get('domain', '')
                    keyword = keyword_item.get('final_keyword', '')
                    url = keyword_item.get('url', '')
                    
                    if not domain or not keyword:
                        self.logger.warning(f"跳过无效的查询项: {keyword_item}")
                        continue
                    
                    # 更新当前处理项
                    current_item = f"查询: {keyword} (第{i+1}/{total_queries}个)"
                    task_manager.update_task_progress(
                        task_info.task_id,
                        progress=i,
                        current_item=current_item
                    )
                    
                    self.logger.info(f"查询排名: {domain} - {keyword}")
                    
                    # 执行查询
                    rank_result = self.query_chinaz_rank(domain, keyword, api_key)
                    
                    # 构建结果项
                    result_item = {
                        'index': i + 1,
                        'id': keyword_item.get('id', ''),
                        'url': url,
                        'keywords': keyword_item.get('keywords', ''),
                        'title': keyword_item.get('title', ''),
                        'domain': domain,
                        'final_keyword': keyword,
                        'previous_uv': keyword_item.get('previous_uv', 0),
                        'current_uv': keyword_item.get('current_uv', 0),
                        'decline_amount': keyword_item.get('decline_amount', 0),
                        'decline_rate': keyword_item.get('decline_rate', 0),
                        'rank': rank_result.get('rank', '未找到'),
                        'rank_num': rank_result.get('rank_num', 0),
                        'rank_title': rank_result.get('title', ''),
                        'rank_url': rank_result.get('url', ''),
                        'site_count': rank_result.get('site_count', 0),
                        'query_time': datetime.now().isoformat(),
                        'success': rank_result.get('success', False),
                        'error': rank_result.get('error', None)
                    }
                    
                    results.append(result_item)
                    
                    # 统计成功/失败数量
                    if rank_result.get('success', False):
                        successful_queries += 1
                    else:
                        failed_queries += 1
                        self.logger.warning(f"查询失败: {keyword} - {rank_result.get('error', '未知错误')}")
                    
                    # 更新任务进度和结果
                    task_manager.update_task_progress(
                        task_info.task_id,
                        progress=i + 1,
                        current_item=f"已完成 {i+1}/{total_queries} 个查询",
                        results=results
                    )
                    
                    # 添加延时避免API限制
                    delay = random.uniform(1.0, 2.0)
                    time.sleep(delay)
                    
                except Exception as e:
                    self.logger.error(f"查询第 {i+1} 个关键词时出错: {str(e)}")
                    failed_queries += 1
                    
                    # 添加失败记录
                    result_item = {
                        'index': i + 1,
                        'id': keyword_item.get('id', ''),
                        'url': keyword_item.get('url', ''),
                        'keywords': keyword_item.get('keywords', ''),
                        'title': keyword_item.get('title', ''),
                        'domain': keyword_item.get('domain', ''),
                        'final_keyword': keyword_item.get('final_keyword', ''),
                        'previous_uv': keyword_item.get('previous_uv', 0),
                        'current_uv': keyword_item.get('current_uv', 0),
                        'decline_amount': keyword_item.get('decline_amount', 0),
                        'decline_rate': keyword_item.get('decline_rate', 0),
                        'rank': '查询失败',
                        'rank_num': 0,
                        'rank_title': '',
                        'rank_url': '',
                        'site_count': 0,
                        'query_time': datetime.now().isoformat(),
                        'success': False,
                        'error': str(e)
                    }
                    
                    results.append(result_item)
                    
                    # 更新任务进度
                    task_manager.update_task_progress(
                        task_info.task_id,
                        progress=i + 1,
                        current_item=f"已完成 {i+1}/{total_queries} 个查询 (失败: {failed_queries})",
                        results=results
                    )
            
            # 任务完成
            completion_summary = f"排名查询完成！总数: {total_queries}, 成功: {successful_queries}, 失败: {failed_queries}"
            task_manager.update_task_progress(
                task_info.task_id,
                progress=total_queries,
                current_item=completion_summary,
                results=results
            )
            
            # 同时保存到历史记录系统
            try:
                query_record = {
                    'session_id': task_info.task_id,
                    'total_queries': total_queries,
                    'successful_queries': successful_queries,
                    'query_method': 'background_task',
                    'task_name': task_info.metadata.get('task_name', '后台排名查询'),
                    'results': results,
                    'timestamp': datetime.now().isoformat()
                }
                session_manager.save_rank_query_record(task_info.task_id, query_record)
                self.logger.info(f"后台任务历史记录已保存: {task_info.task_id}")
            except Exception as e:
                self.logger.error(f"保存后台任务历史记录失败: {str(e)}")
            
            self.logger.info(f"任务 {task_info.task_id} 完成: {completion_summary}")
            
            return results
            
        except Exception as e:
            self.logger.error(f"执行排名查询任务失败: {str(e)}")
            raise
    
    def create_rank_query_task(self, keywords_data: List[Dict[str, Any]], 
                              api_key: str, task_name: str = None) -> str:
        """
        创建排名查询任务
        """
        if not keywords_data:
            raise ValueError("关键词数据不能为空")
        
        if not api_key:
            raise ValueError("API密钥不能为空")
        
        # 创建任务
        task_name = task_name or f"排名查询_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        metadata = {
            'keywords_data': keywords_data,
            'api_key': api_key,
            'task_name': task_name,
            'total_keywords': len(keywords_data),
            'created_by': 'rank_query_system'
        }
        
        task_id = task_manager.create_task(
            task_type='rank_query',
            metadata=metadata,
            max_retries=3,
            retry_delay=75  # 重试间隔75秒
        )
        
        # 创建初始的历史记录
        try:
            initial_record = {
                'session_id': task_id,
                'total_queries': len(keywords_data),
                'successful_queries': 0,
                'query_method': 'background_task',
                'task_name': task_name,
                'status': 'created',
                'results': [],
                'timestamp': datetime.now().isoformat()
            }
            session_manager.save_rank_query_record(task_id, initial_record)
            self.logger.info(f"后台任务初始历史记录已创建: {task_id}")
        except Exception as e:
            self.logger.error(f"创建后台任务初始历史记录失败: {str(e)}")
        
        self.logger.info(f"创建排名查询任务: {task_id}, 关键词数量: {len(keywords_data)}")
        
        return task_id
    
    def start_rank_query_task(self, task_id: str) -> bool:
        """
        启动排名查询任务
        """
        success = task_manager.start_task(task_id, self.execute_rank_query_task)
        
        if success:
            # 更新历史记录状态为已启动
            try:
                task_info = task_manager.get_task(task_id)
                if task_info:
                    update_record = {
                        'session_id': task_id,
                        'total_queries': task_info.metadata.get('total_keywords', 0),
                        'successful_queries': 0,
                        'query_method': 'background_task',
                        'task_name': task_info.metadata.get('task_name', '后台排名查询'),
                        'status': 'started',
                        'results': [],
                        'timestamp': datetime.now().isoformat()
                    }
                    session_manager.save_rank_query_record(task_id, update_record)
                    self.logger.info(f"后台任务历史记录已更新为启动状态: {task_id}")
            except Exception as e:
                self.logger.error(f"更新后台任务历史记录失败: {str(e)}")
        
        return success
    
    def get_task_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务进度
        """
        task_info = task_manager.get_task(task_id)
        if not task_info:
            return None
        
        return {
            'task_id': task_info.task_id,
            'status': task_info.status.value,
            'progress': task_info.progress,
            'total': task_info.total,
            'current_item': task_info.current_item,
            'created_at': task_info.created_at,
            'started_at': task_info.started_at,
            'finished_at': task_info.finished_at,
            'retry_count': task_info.retry_count,
            'max_retries': task_info.max_retries,
            'error_message': task_info.error_message,
            'results_count': len(task_info.results) if task_info.results else 0,
            'task_name': task_info.metadata.get('task_name', ''),
            'percentage': round((task_info.progress / task_info.total * 100) if task_info.total > 0 else 0, 2)
        }
    
    def get_task_results(self, task_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取任务结果
        """
        task_info = task_manager.get_task(task_id)
        if not task_info:
            return None
        
        return task_info.results
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        """
        return task_manager.cancel_task(task_id)
    
    def pause_task(self, task_id: str) -> bool:
        """
        暂停任务
        """
        return task_manager.pause_task(task_id)
    
    def resume_task(self, task_id: str) -> bool:
        """
        恢复任务
        """
        return task_manager.resume_task(task_id)
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """
        获取所有排名查询任务
        """
        tasks = task_manager.get_tasks_by_type('rank_query')
        result = []
        
        for task in tasks:
            result.append({
                'task_id': task.task_id,
                'status': task.status.value,
                'progress': task.progress,
                'total': task.total,
                'current_item': task.current_item,
                'created_at': task.created_at,
                'started_at': task.started_at,
                'finished_at': task.finished_at,
                'retry_count': task.retry_count,
                'max_retries': task.max_retries,
                'error_message': task.error_message,
                'results_count': len(task.results) if task.results else 0,
                'task_name': task.metadata.get('task_name', ''),
                'total_keywords': task.metadata.get('total_keywords', 0),
                'percentage': round((task.progress / task.total * 100) if task.total > 0 else 0, 2)
            })
        
        return result

# 全局排名查询执行器实例
rank_query_executor = RankQueryExecutor() 