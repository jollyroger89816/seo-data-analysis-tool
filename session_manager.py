#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session管理器 - 持久化存储分析结果和关键词查询记录
让动态结果页面可以长期重复查看，并保存关键词提取和排名查询的历史记录
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Any, List

class SessionManager:
    def __init__(self, session_dir='sessions'):
        # 如果是相对路径，则相对于当前脚本文件的目录
        if not os.path.isabs(session_dir):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            session_dir = os.path.join(script_dir, session_dir)
        
        self.session_dir = session_dir
        self.keyword_history_dir = os.path.join(session_dir, 'keyword_history')
        self.rank_history_dir = os.path.join(session_dir, 'rank_history')
        self.ensure_session_dir()
        
    def ensure_session_dir(self):
        """确保session目录存在"""
        for dir_path in [self.session_dir, self.keyword_history_dir, self.rank_history_dir]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
    
    def save_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """保存session数据到磁盘"""
        try:
            session_file = os.path.join(self.session_dir, f"{session_id}.json")
            
            # 添加时间戳
            data['saved_at'] = datetime.now().isoformat()
            data['session_id'] = session_id
            
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            
            logging.info(f"Session保存成功: {session_id}")
            return True
        except Exception as e:
            logging.error(f"保存session失败 {session_id}: {str(e)}")
            return False
    
    def save_keyword_extraction_record(self, session_id: str, extraction_data: Dict[str, Any]) -> bool:
        """保存关键词提取记录"""
        try:
            record_file = os.path.join(self.keyword_history_dir, f"extract_{session_id}.json")
            
            # 添加记录元数据
            record = {
                'session_id': session_id,
                'type': 'keyword_extraction',
                'timestamp': datetime.now().isoformat(),
                'extraction_data': extraction_data
            }
            
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2, default=str)
            
            logging.info(f"关键词提取记录保存成功: {session_id}")
            return True
        except Exception as e:
            logging.error(f"保存关键词提取记录失败 {session_id}: {str(e)}")
            return False
    
    def save_rank_query_record(self, session_id: str, query_data: Dict[str, Any]) -> bool:
        """保存排名查询记录"""
        try:
            record_file = os.path.join(self.rank_history_dir, f"rank_{session_id}.json")
            
            # 添加记录元数据
            record = {
                'session_id': session_id,
                'type': 'rank_query',
                'timestamp': datetime.now().isoformat(),
                'query_data': query_data
            }
            
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2, default=str)
            
            logging.info(f"排名查询记录保存成功: {session_id}")
            return True
        except Exception as e:
            logging.error(f"保存排名查询记录失败 {session_id}: {str(e)}")
            return False
    
    def get_keyword_extraction_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取关键词提取历史记录"""
        try:
            history = []
            
            # 获取所有关键词提取记录文件
            for filename in os.listdir(self.keyword_history_dir):
                if filename.startswith('extract_') and filename.endswith('.json'):
                    file_path = os.path.join(self.keyword_history_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            record = json.load(f)
                            
                        # 获取文件统计信息
                        stat = os.stat(file_path)
                        record['file_size'] = stat.st_size
                        record['file_path'] = file_path
                        
                        history.append(record)
                    except Exception as e:
                        logging.warning(f"读取关键词提取记录失败 {filename}: {str(e)}")
            
            # 按时间戳排序（最新的在前）
            history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return history[:limit]
        except Exception as e:
            logging.error(f"获取关键词提取历史失败: {str(e)}")
            return []
    
    def get_rank_query_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取排名查询历史记录"""
        try:
            history = []
            
            # 获取所有排名查询记录文件
            for filename in os.listdir(self.rank_history_dir):
                if filename.startswith('rank_') and filename.endswith('.json'):
                    file_path = os.path.join(self.rank_history_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            record = json.load(f)
                            
                        # 获取文件统计信息
                        stat = os.stat(file_path)
                        record['file_size'] = stat.st_size
                        record['file_path'] = file_path
                        
                        history.append(record)
                    except Exception as e:
                        logging.warning(f"读取排名查询记录失败 {filename}: {str(e)}")
            
            # 按时间戳排序（最新的在前）
            history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return history[:limit]
        except Exception as e:
            logging.error(f"获取排名查询历史失败: {str(e)}")
            return []
    
    def get_keyword_extraction_record(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取特定的关键词提取记录"""
        try:
            record_file = os.path.join(self.keyword_history_dir, f"extract_{session_id}.json")
            
            if not os.path.exists(record_file):
                return None
                
            with open(record_file, 'r', encoding='utf-8') as f:
                record = json.load(f)
            
            return record
        except Exception as e:
            logging.error(f"获取关键词提取记录失败 {session_id}: {str(e)}")
            return None
    
    def get_rank_query_record(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取特定的排名查询记录"""
        try:
            record_file = os.path.join(self.rank_history_dir, f"rank_{session_id}.json")
            
            if not os.path.exists(record_file):
                return None
                
            with open(record_file, 'r', encoding='utf-8') as f:
                record = json.load(f)
            
            return record
        except Exception as e:
            logging.error(f"获取排名查询记录失败 {session_id}: {str(e)}")
            return None
    
    def get_history_statistics(self) -> Dict[str, Any]:
        """获取历史记录统计信息"""
        try:
            keyword_count = len([f for f in os.listdir(self.keyword_history_dir) 
                               if f.startswith('extract_') and f.endswith('.json')])
            
            rank_count = len([f for f in os.listdir(self.rank_history_dir) 
                            if f.startswith('rank_') and f.endswith('.json')])
            
            return {
                'keyword_extraction_count': keyword_count,
                'rank_query_count': rank_count,
                'total_records': keyword_count + rank_count
            }
        except Exception as e:
            logging.error(f"获取历史记录统计失败: {str(e)}")
            return {
                'keyword_extraction_count': 0,
                'rank_query_count': 0,
                'total_records': 0
            }
    
    def cleanup_old_keyword_records(self, max_age_days: int = 30) -> int:
        """清理过期的关键词提取记录"""
        try:
            from datetime import timedelta
            
            cutoff_time = datetime.now() - timedelta(days=max_age_days)
            deleted_count = 0
            
            for filename in os.listdir(self.keyword_history_dir):
                if filename.startswith('extract_') and filename.endswith('.json'):
                    file_path = os.path.join(self.keyword_history_dir, filename)
                    mtime = os.path.getmtime(file_path)
                    modified_time = datetime.fromtimestamp(mtime)
                    
                    if modified_time < cutoff_time:
                        os.remove(file_path)
                        deleted_count += 1
            
            logging.info(f"清理过期关键词记录完成，删除了{deleted_count}个文件")
            return deleted_count
        except Exception as e:
            logging.error(f"清理过期关键词记录失败: {str(e)}")
            return 0
    
    def cleanup_old_rank_records(self, max_age_days: int = 30) -> int:
        """清理过期的排名查询记录"""
        try:
            from datetime import timedelta
            
            cutoff_time = datetime.now() - timedelta(days=max_age_days)
            deleted_count = 0
            
            for filename in os.listdir(self.rank_history_dir):
                if filename.startswith('rank_') and filename.endswith('.json'):
                    file_path = os.path.join(self.rank_history_dir, filename)
                    mtime = os.path.getmtime(file_path)
                    modified_time = datetime.fromtimestamp(mtime)
                    
                    if modified_time < cutoff_time:
                        os.remove(file_path)
                        deleted_count += 1
            
            logging.info(f"清理过期排名查询记录完成，删除了{deleted_count}个文件")
            return deleted_count
        except Exception as e:
            logging.error(f"清理过期排名查询记录失败: {str(e)}")
            return 0
    
    def delete_keyword_extraction_record(self, session_id: str) -> bool:
        """删除关键词提取记录"""
        try:
            record_file = os.path.join(self.keyword_history_dir, f"extract_{session_id}.json")
            if os.path.exists(record_file):
                os.remove(record_file)
                logging.info(f"关键词提取记录删除成功: {session_id}")
                return True
            return False
        except Exception as e:
            logging.error(f"删除关键词提取记录失败 {session_id}: {str(e)}")
            return False
    
    def delete_rank_query_record(self, session_id: str) -> bool:
        """删除排名查询记录"""
        try:
            record_file = os.path.join(self.rank_history_dir, f"rank_{session_id}.json")
            if os.path.exists(record_file):
                os.remove(record_file)
                logging.info(f"排名查询记录删除成功: {session_id}")
                return True
            return False
        except Exception as e:
            logging.error(f"删除排名查询记录失败 {session_id}: {str(e)}")
            return False

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """从磁盘加载session数据"""
        try:
            session_file = os.path.join(self.session_dir, f"{session_id}.json")
            
            if not os.path.exists(session_file):
                return None
                
            with open(session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logging.info(f"Session加载成功: {session_id}")
            return data
        except Exception as e:
            logging.error(f"加载session失败 {session_id}: {str(e)}")
            return None
    
    def session_exists(self, session_id: str) -> bool:
        """检查session是否存在"""
        session_file = os.path.join(self.session_dir, f"{session_id}.json")
        return os.path.exists(session_file)
    
    def list_sessions(self) -> list:
        """列出所有session"""
        try:
            sessions = []
            for filename in os.listdir(self.session_dir):
                if filename.endswith('.json'):
                    session_id = filename[:-5]  # 移除.json后缀
                    session_file = os.path.join(self.session_dir, filename)
                    
                    # 获取文件修改时间
                    mtime = os.path.getmtime(session_file)
                    modified_time = datetime.fromtimestamp(mtime)
                    
                    # 获取文件大小
                    file_size = os.path.getsize(session_file)
                    
                    sessions.append({
                        'session_id': session_id,
                        'modified_time': modified_time,
                        'formatted_time': modified_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'file_path': session_file,
                        'file_size': f"{file_size / 1024:.1f} KB"
                    })
            
            # 按修改时间排序
            sessions.sort(key=lambda x: x['modified_time'], reverse=True)
            return sessions
        except Exception as e:
            logging.error(f"列出sessions失败: {str(e)}")
            return []
    
    def delete_session(self, session_id: str) -> bool:
        """删除session"""
        try:
            session_file = os.path.join(self.session_dir, f"{session_id}.json")
            if os.path.exists(session_file):
                os.remove(session_file)
                logging.info(f"Session删除成功: {session_id}")
                return True
            return False
        except Exception as e:
            logging.error(f"删除session失败 {session_id}: {str(e)}")
            return False
    
    def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """清理超过指定天数的旧session"""
        try:
            from datetime import timedelta
            
            cutoff_time = datetime.now() - timedelta(days=max_age_days)
            deleted_count = 0
            
            for filename in os.listdir(self.session_dir):
                if filename.endswith('.json'):
                    session_file = os.path.join(self.session_dir, filename)
                    mtime = os.path.getmtime(session_file)
                    modified_time = datetime.fromtimestamp(mtime)
                    
                    if modified_time < cutoff_time:
                        os.remove(session_file)
                        deleted_count += 1
            
            logging.info(f"清理旧session完成，删除了{deleted_count}个文件")
            return deleted_count
        except Exception as e:
            logging.error(f"清理旧session失败: {str(e)}")
            return 0
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取session基本信息（不加载完整数据）"""
        try:
            session_file = os.path.join(self.session_dir, f"{session_id}.json")
            
            if not os.path.exists(session_file):
                return None
            
            # 获取文件统计信息
            stat = os.stat(session_file)
            modified_time = datetime.fromtimestamp(stat.st_mtime)
            file_size = stat.st_size
            
            # 尝试读取基本信息
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                return {
                    'session_id': session_id,
                    'modified_time': modified_time,
                    'file_size': file_size,
                    'current_filename': data.get('current_filename', '未知'),
                    'previous_filename': data.get('previous_filename'),
                    'has_error': bool(data.get('error')),
                    'has_result': bool(data.get('result')),
                    'saved_at': data.get('saved_at')
                }
            except json.JSONDecodeError:
                return {
                    'session_id': session_id,
                    'modified_time': modified_time,
                    'file_size': file_size,
                    'current_filename': '未知',
                    'previous_filename': None,
                    'has_error': True,
                    'saved_at': None
                }
                
        except Exception as e:
            logging.error(f"获取session信息失败 {session_id}: {str(e)}")
            return None

# 创建全局session管理器实例
session_manager = SessionManager() 