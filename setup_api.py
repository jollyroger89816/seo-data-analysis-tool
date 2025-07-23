#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Key 快速设置脚本
"""

import os
import json
import sys

def setup_api_key():
    """设置API Key"""
    print("=== SEO排名查询系统 - API Key配置 ===")
    print()
    
    config_file = "api_keys.json"
    
    # 检查配置文件是否存在
    if not os.path.exists(config_file):
        if os.path.exists("api_keys.json.example"):
            # 复制示例文件
            import shutil
            shutil.copy2("api_keys.json.example", config_file)
            print(f"✅ 已创建配置文件: {config_file}")
        else:
            print(f"❌ 找不到示例配置文件: api_keys.json.example")
            return False
    
    # 读取当前配置
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return False
    
    # 显示当前状态
    current_key = config.get("chinaz_api_key", "")
    if current_key and current_key != "请在这里填入你的站长之家API Key":
        print(f"📝 当前API Key: {current_key[:10]}...")
        if input("是否要更新API Key? (y/N): ").lower() != 'y':
            return True
    else:
        print("🔑 当前未配置API Key")
    
    print()
    print("📌 获取站长之家API Key:")
    print("   1. 访问: https://data.chinaz.com/api")
    print("   2. 注册/登录账号")
    print("   3. 申请API接口权限")
    print("   4. 获取API Key")
    print()
    
    # 输入新的API Key
    while True:
        api_key = input("请输入站长之家API Key (回车取消): ").strip()
        
        if not api_key:
            print("❌ 已取消设置")
            return False
        
        if len(api_key) < 10:
            print("❌ API Key长度太短，请检查")
            continue
        
        # 确认
        print(f"🔍 API Key: {api_key[:10]}...{api_key[-4:]}")
        if input("确认设置此API Key? (y/N): ").lower() == 'y':
            break
    
    # 保存配置
    try:
        config["chinaz_api_key"] = api_key
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        print(f"✅ API Key已保存到: {config_file}")
        print()
        print("🎉 配置完成！可以重启服务了:")
        print("   python start_services.py")
        
        return True
        
    except Exception as e:
        print(f"❌ 保存配置失败: {e}")
        return False

def main():
    try:
        if setup_api_key():
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ 已取消设置")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 设置失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 