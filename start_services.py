#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务启动脚本
同时启动数据分析服务和排名查询服务
"""

import os
import sys
import time
import signal
import subprocess
import threading
import requests
from datetime import datetime

class ServiceManager:
    def __init__(self):
        self.services = {
            'data_analysis': {
                'name': '数据分析服务',
                'script': 'keyword_rank_analyzer.py',
                'port': 5001,
                'url': 'http://127.0.0.1:5001',
                'process': None
            },
            'rank_query': {
                'name': '排名查询服务',
                'script': 'rank_query_app.py',
                'port': 5000,  # 修改为5000
                'url': 'http://127.0.0.1:5000',  # 修改为5000
                'process': None
            }
        }
        self.running = True
        
    def log(self, message, service_name=None):
        """输出日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if service_name:
            print(f"[{timestamp}] [{service_name}] {message}")
        else:
            print(f"[{timestamp}] [系统] {message}")
    
    def check_port_available(self, port):
        """检查端口是否可用"""
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', port))
                return result != 0
        except Exception:
            return True
    
    def find_process_by_port(self, port):
        """根据端口找到占用的进程"""
        try:
            if os.name == 'nt':  # Windows
                cmd = f'netstat -ano | findstr :{port}'
            else:  # Unix/Linux/macOS
                cmd = f'lsof -ti:{port}'
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                if os.name == 'nt':
                    # Windows: 解析netstat输出
                    lines = result.stdout.strip().split('\n')
                    pids = []
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 5:
                            pids.append(parts[-1])
                    return pids
                else:
                    # Unix: lsof直接返回PID
                    pids = result.stdout.strip().split('\n')
                    return [pid for pid in pids if pid.isdigit()]
            return []
        except Exception as e:
            self.log(f"查找端口 {port} 占用进程时出错: {str(e)}")
            return []
    
    def kill_process_by_pid(self, pid):
        """根据PID终止进程"""
        try:
            if os.name == 'nt':  # Windows
                subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
            else:  # Unix/Linux/macOS
                subprocess.run(f'kill -9 {pid}', shell=True, capture_output=True)
            return True
        except Exception as e:
            self.log(f"终止进程 {pid} 时出错: {str(e)}")
            return False
    
    def free_port(self, port, service_name):
        """释放被占用的端口"""
        self.log(f"端口 {port} 被占用，正在查找占用进程...", service_name)
        
        pids = self.find_process_by_port(port)
        if not pids:
            self.log(f"未找到占用端口 {port} 的进程", service_name)
            return False
        
        self.log(f"找到占用端口 {port} 的进程: {', '.join(pids)}", service_name)
        
        success_count = 0
        for pid in pids:
            self.log(f"正在终止进程 {pid}...", service_name)
            if self.kill_process_by_pid(pid):
                success_count += 1
                self.log(f"进程 {pid} 已终止", service_name)
            else:
                self.log(f"终止进程 {pid} 失败", service_name)
        
        if success_count > 0:
            # 等待端口释放
            self.log(f"等待端口 {port} 释放...", service_name)
            time.sleep(2)
            
            # 再次检查端口
            if self.check_port_available(port):
                self.log(f"端口 {port} 已释放", service_name)
                return True
            else:
                self.log(f"端口 {port} 仍被占用", service_name)
                return False
        
        return False
    
    def wait_for_service(self, service_key, timeout=60):
        """等待服务启动"""
        service = self.services[service_key]
        url = service['url']
        
        self.log(f"等待 {service['name']} 启动...", service['name'])
        
        for i in range(timeout):
            # 检查进程是否还活着
            if service['process'] and service['process'].poll() is not None:
                # 进程已退出，获取错误信息
                stdout, stderr = service['process'].communicate()
                self.log(f"{service['name']} 进程异常退出", service['name'])
                if stdout:
                    self.log(f"标准输出: {stdout}", service['name'])
                if stderr:
                    self.log(f"错误输出: {stderr}", service['name'])
                return False
            
            try:
                response = requests.get(url, timeout=3)
                if response.status_code == 200:
                    self.log(f"{service['name']} 启动成功！", service['name'])
                    return True
            except requests.exceptions.RequestException as e:
                if i % 10 == 0:  # 每10秒输出一次进度
                    self.log(f"等待 {service['name']} 响应... ({i}/{timeout}秒)", service['name'])
            
            time.sleep(1)
        
        self.log(f"{service['name']} 启动超时", service['name'])
        
        # 检查进程状态
        if service['process']:
            if service['process'].poll() is None:
                self.log(f"{service['name']} 进程仍在运行，但无法访问服务", service['name'])
            else:
                self.log(f"{service['name']} 进程已退出", service['name'])
        
        return False
    
    def start_service(self, service_key):
        """启动单个服务"""
        service = self.services[service_key]
        
        # 检查端口是否可用
        if not self.check_port_available(service['port']):
            self.log(f"端口 {service['port']} 已被占用，尝试自动释放...", service['name'])
            
            # 尝试释放端口
            if not self.free_port(service['port'], service['name']):
                self.log(f"无法释放端口 {service['port']}，请手动关闭相关进程", service['name'])
                return False
        
        # 检查脚本文件是否存在
        script_path = os.path.abspath(service['script'])
        if not os.path.exists(script_path):
            self.log(f"服务脚本不存在: {script_path}", service['name'])
            self.log(f"当前工作目录: {os.getcwd()}", service['name'])
            return False
        
        try:
            # 启动服务
            self.log(f"启动 {service['name']}...", service['name'])
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            service['process'] = process
            self.log(f"{service['name']} 进程启动，PID: {process.pid}", service['name'])
            
            # 等待一下，检查进程是否立即退出
            time.sleep(2)
            if process.poll() is not None:
                # 进程已经退出，获取错误信息
                stdout, stderr = process.communicate()
                self.log(f"{service['name']} 进程异常退出", service['name'])
                if stdout:
                    self.log(f"标准输出: {stdout}", service['name'])
                if stderr:
                    self.log(f"错误输出: {stderr}", service['name'])
                return False
            
            return True
            
        except Exception as e:
            self.log(f"启动 {service['name']} 失败: {str(e)}", service['name'])
            return False
    
    def stop_service(self, service_key):
        """停止单个服务"""
        service = self.services[service_key]
        
        if service['process'] and service['process'].poll() is None:
            self.log(f"停止 {service['name']}...", service['name'])
            service['process'].terminate()
            
            # 等待进程结束
            try:
                service['process'].wait(timeout=5)
                self.log(f"{service['name']} 已停止", service['name'])
            except subprocess.TimeoutExpired:
                self.log(f"强制停止 {service['name']}", service['name'])
                service['process'].kill()
                service['process'].wait()
            
            service['process'] = None
    
    def monitor_services(self):
        """监控服务状态"""
        while self.running:
            for service_key, service in self.services.items():
                if service['process'] and service['process'].poll() is not None:
                    self.log(f"{service['name']} 进程异常退出", service['name'])
                    
                    # 尝试重启
                    self.log(f"尝试重启 {service['name']}", service['name'])
                    self.start_service(service_key)
                    
                    # 等待服务启动
                    time.sleep(2)
                    if not self.wait_for_service(service_key, timeout=10):
                        self.log(f"{service['name']} 重启失败", service['name'])
            
            time.sleep(5)  # 每5秒检查一次
    
    def signal_handler(self, signum, frame):
        """信号处理器"""
        self.log("接收到停止信号，正在关闭所有服务...")
        self.stop_all_services()
        sys.exit(0)
    
    def start_all_services(self):
        """启动所有服务"""
        self.log("=== 启动所有服务 ===")
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # 预先清理可能占用的端口
        self.log("检查并清理端口...")
        for service_key, service in self.services.items():
            if not self.check_port_available(service['port']):
                self.log(f"端口 {service['port']} 被占用，尝试清理...", service['name'])
                self.free_port(service['port'], service['name'])
        
        success_count = 0
        
        # 启动所有服务
        for service_key in self.services:
            if self.start_service(service_key):
                success_count += 1
        
        if success_count == 0:
            self.log("没有服务启动成功")
            return False
        
        # 等待服务完全启动
        self.log("等待所有服务完全启动...")
        time.sleep(3)
        
        # 检查服务状态
        healthy_services = 0
        for service_key in self.services:
            if self.services[service_key]['process']:
                if self.wait_for_service(service_key, timeout=45):
                    healthy_services += 1
        
        if healthy_services > 0:
            self.log(f"成功启动 {healthy_services}/{len(self.services)} 个服务")
            self.show_service_info()
            
            # 启动监控线程
            monitor_thread = threading.Thread(target=self.monitor_services, daemon=True)
            monitor_thread.start()
            
            return True
        else:
            self.log("所有服务启动失败")
            self.stop_all_services()
            return False
    
    def stop_all_services(self):
        """停止所有服务"""
        self.log("=== 停止所有服务 ===")
        self.running = False
        
        for service_key in self.services:
            self.stop_service(service_key)
        
        self.log("所有服务已停止")
    
    def show_service_info(self):
        """显示服务信息"""
        self.log("=== 服务信息 ===")
        for service_key, service in self.services.items():
            status = "运行中" if service['process'] and service['process'].poll() is None else "已停止"
            self.log(f"{service['name']}: {service['url']} - {status}")
        
        self.log("\n可用的服务:")
        self.log("- 数据分析工具: http://127.0.0.1:5001")
        self.log("- 排名查询工具: http://127.0.0.1:5000")
        self.log("\n按 Ctrl+C 停止所有服务")
    
    def check_services_status(self):
        """检查服务状态"""
        self.log("=== 检查服务状态 ===")
        
        for service_key, service in self.services.items():
            try:
                response = requests.get(service['url'], timeout=5)
                if response.status_code == 200:
                    self.log(f"{service['name']}: ✓ 正常运行", service['name'])
                else:
                    self.log(f"{service['name']}: ✗ 响应异常 (状态码: {response.status_code})", service['name'])
            except requests.exceptions.RequestException as e:
                self.log(f"{service['name']}: ✗ 无法连接 ({str(e)})", service['name'])

def main():
    """主函数"""
    print("=== SEO数据分析与排名查询服务管理器 ===\n")
    
    # 确保在正确的目录中运行
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"工作目录: {script_dir}")
    print("注意：如发现端口被占用，将自动终止占用进程并重新启动服务\n")
    
    # 检查是否有命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        manager = ServiceManager()
        
        if command == 'stop':
            # 这里可以添加停止现有服务的逻辑
            print("停止服务功能待实现...")
            
        elif command == 'status':
            manager.check_services_status()
            
        elif command == 'help':
            print("使用方法:")
            print("  python start_services.py         - 直接启动所有服务（默认）")
            print("  python start_services.py stop    - 停止所有服务")
            print("  python start_services.py status  - 检查服务状态")
            print("  python start_services.py help    - 显示帮助信息")
            
        else:
            print(f"未知命令: {command}")
            print("使用 'python start_services.py help' 查看帮助")
            return
    
    # 默认启动所有服务（无论有无参数，除非是特定命令）
    if len(sys.argv) == 1 or (len(sys.argv) > 1 and sys.argv[1].lower() not in ['stop', 'status', 'help']):
        manager = ServiceManager()
        print("正在启动所有服务...")
        
        if manager.start_all_services():
            try:
                # 保持运行状态
                while manager.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                manager.stop_all_services()
        else:
            print("\n服务启动失败！")
            print("可能的解决方案：")
            print("1. 检查 keyword_rank_analyzer.py 和 rank_query_app.py 文件是否存在")
            print("2. 检查Python依赖包是否安装完整")
            print("3. 手动终止占用端口5001和5002的进程")
            print("4. 确保在数据分析目录中运行此脚本")

if __name__ == '__main__':
    main() 