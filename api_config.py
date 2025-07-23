#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API配置管理
用于安全存储和管理API密钥
"""

import os
import json
import logging
from pathlib import Path

class APIConfig:
    def __init__(self):
        self.config_file = os.path.join(os.path.dirname(__file__), 'api_keys.json')
        self.config_data = self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # 创建默认配置
                default_config = {
                    "chinaz_api_key": "",
                    "other_api_keys": {},
                    "settings": {
                        "auto_retry": True,
                        "cache_enabled": True,
                        "default_concurrent": 2
                    }
                }
                self._save_config(default_config)
                return default_config
        except Exception as e:
            logging.error(f"加载API配置失败: {str(e)}")
            return {
                "chinaz_api_key": "",
                "other_api_keys": {},
                "settings": {
                    "auto_retry": True,
                    "cache_enabled": True,
                    "default_concurrent": 2
                }
            }
    
    def _save_config(self, config_data):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            logging.info("API配置已保存")
        except Exception as e:
            logging.error(f"保存API配置失败: {str(e)}")
    
    def get_chinaz_api_key(self):
        """获取站长之家API Key"""
        return self.config_data.get("chinaz_api_key", "")
    
    def set_chinaz_api_key(self, api_key):
        """设置站长之家API Key"""
        self.config_data["chinaz_api_key"] = api_key.strip()
        self._save_config(self.config_data)
        logging.info("站长之家API Key已更新")
    
    def get_setting(self, key, default=None):
        """获取设置项"""
        return self.config_data.get("settings", {}).get(key, default)
    
    def set_setting(self, key, value):
        """设置配置项"""
        if "settings" not in self.config_data:
            self.config_data["settings"] = {}
        self.config_data["settings"][key] = value
        self._save_config(self.config_data)
    
    def has_valid_api_key(self):
        """检查是否有有效的API Key"""
        api_key = self.get_chinaz_api_key()
        return bool(api_key and len(api_key.strip()) > 10)
    
    def get_config_file_path(self):
        """获取配置文件路径"""
        return self.config_file

# 全局实例
api_config = APIConfig() 