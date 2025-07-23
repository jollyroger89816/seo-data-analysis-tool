#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
用于保存和管理API Key等配置信息
"""

import os
import json
import logging
from datetime import datetime

class ConfigManager:
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # 返回默认配置
                return {
                    'chinaz_api_key': '',
                    'last_updated': '',
                    'api_usage_info': {
                        'total_calls': 0,
                        'last_check': '',
                        'remaining_calls': 'unknown'
                    }
                }
        except Exception as e:
            logging.error(f"加载配置文件失败: {str(e)}")
            return {
                'chinaz_api_key': '',
                'last_updated': '',
                'api_usage_info': {
                    'total_calls': 0,
                    'last_check': '',
                    'remaining_calls': 'unknown'
                }
            }
    
    def save_config(self):
        """保存配置文件"""
        try:
            self.config['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logging.error(f"保存配置文件失败: {str(e)}")
            return False
    
    def get_api_key(self):
        """获取API Key"""
        return self.config.get('chinaz_api_key', '')
    
    def set_api_key(self, api_key):
        """设置API Key"""
        self.config['chinaz_api_key'] = api_key
        return self.save_config()
    
    def get_api_usage_info(self):
        """获取API使用信息"""
        return self.config.get('api_usage_info', {
            'total_calls': 0,
            'last_check': '',
            'remaining_calls': 'unknown'
        })
    
    def update_api_usage(self, total_calls=None, remaining_calls=None):
        """更新API使用信息"""
        api_info = self.config.get('api_usage_info', {})
        
        if total_calls is not None:
            api_info['total_calls'] = total_calls
        
        if remaining_calls is not None:
            api_info['remaining_calls'] = remaining_calls
        
        api_info['last_check'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.config['api_usage_info'] = api_info
        return self.save_config()
    
    def increment_api_calls(self, count=1):
        """增加API调用次数"""
        api_info = self.config.get('api_usage_info', {})
        current_calls = api_info.get('total_calls', 0)
        api_info['total_calls'] = current_calls + count
        api_info['last_check'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.config['api_usage_info'] = api_info
        return self.save_config()

# 全局配置管理器实例
config_manager = ConfigManager() 