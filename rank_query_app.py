#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立的排名查询工具
支持手动输入URL和一键查询Excel报告中的目标下降词排名
"""

import os
import time
import json
import logging
import requests
import threading
from datetime import datetime
from urllib.parse import urlparse
import re
import pandas as pd
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
import random
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import queue
from config_manager import config_manager
from session_manager import session_manager
from task_manager import task_manager, TaskStatus
from rank_query_executor import rank_query_executor
from api_config import api_config
import socket

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rank_query.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
app.secret_key = "rank_query_app_secret_key"
app.config['UPLOAD_FOLDER'] = os.path.abspath('uploads')
app.config['EXPORT_FOLDER'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'exports'))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# 创建必要的文件夹
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)

def init_dir():
    """初始化必要的目录"""
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)
    os.makedirs('analysis_results', exist_ok=True)
    os.makedirs('sessions', exist_ok=True)
    logging.info("目录初始化完成")

# 全局变量用于跟踪查询进度
query_progress_data = {
    'total': 0,
    'completed': 0,
    'current_url': '',
    'status': 'idle',
    'results': [],
    'session_id': None,
    'should_stop': False
}

# 全局变量用于保存排名查询结果
rank_query_results = {
    'results': [],
    'query_type': '',
    'source_file': '',
    'timestamp': ''
}

# 全局变量用于保存关键词提取结果
keyword_extraction_results = {
    'results': [],
    'session_id': None,
    'total': 0,
    'completed': 0,
    'status': 'idle'
}

# 全局变量用于跟踪查询和提取进度
extract_progress_data = {
    'total': 0,
    'completed': 0,
    'current_url': '',
    'status': 'idle',
    'results': [],
    'session_id': None,
    'should_stop': False
}

# 添加全局锁和队列
extract_lock = Lock()
result_queue = queue.Queue()

# API频率控制
api_call_times = []
api_call_lock = threading.Lock()
last_api_call_time = 0
# 添加缓存
rank_cache = {}
cache_lock = threading.Lock()
# 添加缓存命中计数器
cache_hits = 0
cache_hits_lock = threading.Lock()

def smart_api_delay():
    """智能API调用延时控制"""
    global last_api_call_time, api_call_times
    
    with api_call_lock:
        current_time = time.time()
        
        # 清理1分钟前的记录
        api_call_times = [t for t in api_call_times if current_time - t < 60]
        
        # 如果1分钟内调用次数过多，增加延时
        if len(api_call_times) >= 50:  # 每分钟最多50次调用
            delay = 1.5
        elif len(api_call_times) >= 30:  # 每分钟30次以上时增加延时
            delay = 0.8
        elif len(api_call_times) >= 15:  # 每分钟15次以上时小幅延时
            delay = 0.3
        else:
            delay = 0.1  # 最小延时
        
        # 确保与上次调用间隔至少100ms
        time_since_last = current_time - last_api_call_time
        if time_since_last < delay:
            time.sleep(delay - time_since_last)
        
        api_call_times.append(time.time())
        last_api_call_time = time.time()

def get_cache_key(domain, keyword):
    """生成缓存键"""
    return f"{domain}|{keyword}".lower()

def get_cached_rank(domain, keyword):
    """获取缓存的排名结果"""
    global cache_hits
    cache_key = get_cache_key(domain, keyword)
    with cache_lock:
        cached_result = rank_cache.get(cache_key)
        if cached_result:
            # 检查缓存是否过期（30分钟）
            if time.time() - cached_result['timestamp'] < 1800:
                with cache_hits_lock:
                    cache_hits += 1
                logging.info(f"使用缓存结果: {domain} - {keyword}")
                return cached_result['data']
            else:
                # 删除过期缓存
                del rank_cache[cache_key]
    return None

def set_cached_rank(domain, keyword, result):
    """设置缓存的排名结果"""
    cache_key = get_cache_key(domain, keyword)
    with cache_lock:
        rank_cache[cache_key] = {
            'data': result,
            'timestamp': time.time()
        }
        
        # 限制缓存大小，删除最旧的缓存
        if len(rank_cache) > 1000:
            oldest_key = min(rank_cache.keys(), key=lambda k: rank_cache[k]['timestamp'])
            del rank_cache[oldest_key]

def get_analysis_results_dir():
    """智能获取分析结果目录路径"""
    # 获取当前脚本的绝对路径
    current_script_path = os.path.abspath(__file__)
    
    # 多种环境检测方式
    is_server_env = False
    
    # 方式1: 检查路径是否包含服务器特征
    if '/opt/seo_analysis' in current_script_path:
        is_server_env = True
    
    # 方式2: 检查环境变量
    if os.environ.get('SEO_ENV') == 'production':
        is_server_env = True
    
    # 方式3: 检查是否存在服务器特有的目录
    if os.path.exists('/opt/seo_analysis') and os.path.isdir('/opt/seo_analysis'):
        is_server_env = True
    
    if is_server_env:
        # 线上环境，使用线上路径
        analysis_dir = '/opt/seo_analysis/analysis_results'
        logging.info(f"检测到线上环境，使用路径: {analysis_dir}")
    else:
        # 本地环境，使用脚本相对路径
        analysis_dir = os.path.join(os.path.dirname(__file__), 'analysis_results')
        logging.info(f"检测到本地环境，使用路径: {analysis_dir}")
    
    return analysis_dir

def get_latest_analysis_result():
    """获取最新的分析结果"""
    try:
        analysis_dir = get_analysis_results_dir()
        
        if not os.path.exists(analysis_dir):
            logging.warning(f"分析结果目录不存在: {analysis_dir}")
            return None
        
        # 获取所有JSON文件
        json_files = glob.glob(os.path.join(analysis_dir, '*.json'))
        if not json_files:
            return None
        
        # 按修改时间排序，获取最新的文件
        latest_file = max(json_files, key=os.path.getmtime)
        
        # 读取JSON文件
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logging.info(f"成功加载最新分析结果: {latest_file}")
        return data
        
    except Exception as e:
        logging.error(f"获取最新分析结果失败: {str(e)}")
        return None

def get_all_analysis_reports():
    """获取所有可用的分析报告列表"""
    try:
        reports = []
        analysis_dir = get_analysis_results_dir()
        
        if not os.path.exists(analysis_dir):
            logging.warning(f"分析结果目录不存在: {analysis_dir}")
            return []
        
        # 获取所有JSON文件
        json_files = glob.glob(os.path.join(analysis_dir, '*.json'))
        
        for json_file in json_files:
            # 从文件名提取时间戳
            filename = os.path.basename(json_file)
            if not filename.startswith('analysis_'):
                continue
                
            timestamp_str = filename.replace('analysis_', '').replace('.json', '')
            
            try:
                # 尝试两种时间戳格式
                try:
                    # 先尝试带下划线的格式 (20250716_175957)
                    timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                except ValueError:
                    # 如果失败，尝试不带下划线的格式 (20250707183702)
                    timestamp = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
                    # 转换为带下划线的格式
                    timestamp_str = timestamp.strftime('%Y%m%d_%H%M%S')
                    
                
                # 获取文件大小
                file_size = os.path.getsize(json_file)
                file_size_mb = round(file_size / (1024 * 1024), 1)
                
                # 读取JSON文件获取基本信息
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    basic_analysis = data.get('basic_analysis', {})
                    comparative_analysis = data.get('comparative_analysis', {})
                    
                reports.append({
                    'filename': filename,
                    'timestamp': timestamp_str,
                    'display_time': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'file_size': file_size_mb,
                    'json_path': json_file,
                    'total_uv': basic_analysis.get('total_uv', 0),
                    'total_urls': basic_analysis.get('total_urls', 0),
                    'unique_ids': basic_analysis.get('unique_ids', 0),
                    'target_decline_count': len(comparative_analysis.get('target_decline_details', [])),
                    'category': basic_analysis.get('category', '全部'),
                    'date_range': basic_analysis.get('date_range', '')
                })
            except Exception as e:
                logging.warning(f"处理报告文件失败 {filename}: {str(e)}")
        
        # 按时间戳倒序排序（最新的在前面）
        reports.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return reports
        
    except Exception as e:
        logging.error(f"获取分析报告列表失败: {str(e)}")
        return []

def get_analysis_result_by_timestamp(timestamp):
    """根据时间戳获取指定的分析结果"""
    try:
        analysis_dir = get_analysis_results_dir()
        
        if not os.path.exists(analysis_dir):
            logging.warning(f"分析结果目录不存在: {analysis_dir}")
            return None
        
        logging.info(f"正在查找时间戳 {timestamp} 对应的分析文件，目录: {analysis_dir}")
        
        # 列出目录中的所有JSON文件
        all_json_files = glob.glob(os.path.join(analysis_dir, '*.json'))
        logging.info(f"目录中的所有JSON文件: {[os.path.basename(f) for f in all_json_files]}")
        
        # 尝试多种可能的文件名格式
        possible_filenames = [
            f'analysis_{timestamp}.json',  # 完整时间戳：analysis_20250718_134011.json
            f'analysis_{timestamp.replace("_", "")}.json',  # 去掉下划线：analysis_20250718134011.json
        ]
        
        # 如果timestamp中包含下划线，也尝试去掉下划线的版本
        if '_' in timestamp:
            timestamp_no_underscore = timestamp.replace('_', '')
            possible_filenames.extend([
                f'analysis_{timestamp_no_underscore}.json',
                f'analysis_{timestamp_no_underscore[:8]}_{timestamp_no_underscore[8:]}.json'
            ])
        else:
            # 如果没有下划线，尝试添加下划线的版本
            if len(timestamp) >= 8:
                timestamp_with_underscore = f"{timestamp[:8]}_{timestamp[8:]}"
                possible_filenames.append(f'analysis_{timestamp_with_underscore}.json')
        
        logging.info(f"尝试查找的文件名: {possible_filenames}")
        
        json_file = None
        for filename in possible_filenames:
            temp_path = os.path.join(analysis_dir, filename)
            if os.path.exists(temp_path):
                json_file = temp_path
                logging.info(f"找到匹配文件: {filename}")
                break
        
        if not json_file:
            logging.warning(f"指定的分析结果文件不存在，尝试过以下文件名: {possible_filenames}")
            # 尝试模糊匹配，查找包含时间戳的文件
            for json_file_path in all_json_files:
                filename = os.path.basename(json_file_path)
                if timestamp.replace('_', '') in filename or timestamp in filename:
                    json_file = json_file_path
                    logging.info(f"通过模糊匹配找到文件: {filename}")
                    break
            
            if not json_file:
                return None
        
        # 读取JSON文件
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logging.info(f"成功加载指定分析结果: {json_file}")
        return data
        
    except Exception as e:
        logging.error(f"获取指定分析结果失败: {str(e)}")
        return None

def extract_target_decline_urls_from_analysis(min_decline_uv=None, min_decline_rate=None, max_decline_uv=None, max_decline_rate=None, timestamp=None):
    try:
        # 根据timestamp参数决定使用哪个分析结果
        if timestamp:
            analysis_data = get_analysis_result_by_timestamp(timestamp)
        else:
            analysis_data = get_latest_analysis_result()
        
        if not analysis_data:
            return []
        
        # 获取目标下降词详情
        comparative_analysis = analysis_data.get('comparative_analysis', {})
        target_decline_details = comparative_analysis.get('target_decline_details_full', [])
        
        if not target_decline_details:
            # 如果没有完整数据，尝试使用显示数据
            target_decline_details = comparative_analysis.get('target_decline_details', [])
        
        if not target_decline_details:
            logging.warning("分析结果中没有找到目标下降词数据")
            return []
        
        # 应用过滤条件
        filtered_urls = []
        for item in target_decline_details:
            decline_amount = item.get('decline_amount', 0)
            decline_rate = item.get('decline_rate', 0)
            
            # 检查过滤条件
            if min_decline_uv is not None and decline_amount < min_decline_uv:
                continue
            if max_decline_uv is not None and decline_amount > max_decline_uv:
                continue
            if min_decline_rate is not None and decline_rate < min_decline_rate:
                continue
            if max_decline_rate is not None and decline_rate > max_decline_rate:
                continue
            
            url_info = {
                'url': item.get('url', ''),
                'id': item.get('id', ''),
                'title': item.get('title', ''),
                'previous_uv': item.get('previous_uv', 0),
                'current_uv': item.get('current_uv', 0),
                'decline_amount': decline_amount,
                'decline_rate': decline_rate
            }
            filtered_urls.append(url_info)
        
        report_info = f"指定报告 ({timestamp})" if timestamp else "最新报告"
        logging.info(f"从{report_info}中提取到 {len(target_decline_details)} 个目标下降词URL，过滤后剩余 {len(filtered_urls)} 个")
        return filtered_urls
        
    except Exception as e:
        logging.error(f"提取目标下降词URL失败: {str(e)}")
        return []

def extract_title_from_url(url):
    """从URL提取页面标题"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=5)  # 从15秒减少到5秒
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('title')
        
        if title_tag:
            title = title_tag.get_text().strip()
            # 清理标题，移除常见的网站后缀
            title = title.replace(' - 东奥会计在线', '').replace(' | 东奥会计在线', '')
            title = title.replace('_东奥会计在线', '').replace('-东奥会计在线', '')
            return title
        
        return None
        
    except requests.exceptions.Timeout:
        logging.warning(f"提取标题超时: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logging.warning(f"提取标题网络错误 {url}: {str(e)}")
        return None
    except Exception as e:
        logging.warning(f"提取标题失败 {url}: {str(e)}")
        return None

def extract_keywords_from_url(url, timeout=5):  # 从10秒减少到5秒
    """从URL的meta keywords标签中提取关键词，如果有多个关键词则只返回第一个"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout)
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 查找keywords meta标签
        keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        if keywords_tag and keywords_tag.get('content'):
            keywords = keywords_tag['content'].strip()
            # 清理关键词，去除多余的逗号和空格
            keywords = re.sub(r'[,，]\s*', ',', keywords)
            keywords = re.sub(r'^[,，]+|[,，]+$', '', keywords)  # 去除开头和结尾的逗号
            
            # 如果有多个关键词，只取第一个
            return extract_first_keyword(keywords)
        else:
            # 如果没有keywords标签，尝试从title中提取
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()
                # 清理标题，移除常见的网站后缀
                title = title.replace(' - 东奥会计在线', '').replace(' | 东奥会计在线', '')
                title = title.replace('_东奥会计在线', '').replace('-东奥会计在线', '')
                return title
            return None
        
    except requests.exceptions.Timeout:
        logging.warning(f"提取关键词超时: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logging.warning(f"提取关键词网络错误 {url}: {str(e)}")
        return None
    except Exception as e:
        logging.warning(f"提取关键词失败 {url}: {str(e)}")
        return None

def extract_first_keyword(text):
    """从文本中提取第一个关键词，用于排名查询"""
    if not text:
        return text
    
    # 处理多个关键词的情况（用逗号分隔）
    if ',' in text or '，' in text:
        first_keyword = re.split(r'[,，]', text)[0].strip()
        logging.info(f"从多个关键词中选择第一个: '{first_keyword}' (原始: '{text}')")
        return first_keyword
    else:
        return text.strip()

def extract_domain_from_url(url):
    """从URL中提取域名"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        # 移除www前缀
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return 'dongao.com'  # 默认域名

def auto_save_ranking_results(results, query_type='manual'):
    """自动保存排名查询结果到Excel文件"""
    try:
        if not results:
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"排名查询结果_{timestamp}.xlsx"
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)
        
        # 创建DataFrame
        df_data = []
        for result in results:
            row = {
                '序号': result.get('index', ''),
                'ID': result.get('id', ''),
                'URL': result.get('url', ''),
                '关键词': result.get('keywords', ''),
                '页面标题': result.get('title', ''),
                '域名': result.get('domain', ''),
                '最终关键词': result.get('final_keyword', ''),
                '百度排名': result.get('rank', ''),
                '排名标题': result.get('rank_title', ''),
                '排名URL': result.get('rank_url', ''),
                '收录量': result.get('site_count', 0),
                '状态': '失败' if result.get('error') else '正常'
            }
            
            # 如果有流量信息，添加流量数据
            if 'previous_uv' in result:
                row.update({
                    '去年UV': result.get('previous_uv', 0),
                    '今年UV': result.get('current_uv', 0),
                    '下降流量': result.get('decline_amount', 0),
                    '下降幅度(%)': result.get('decline_rate', 0)
                })
            
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        
        # 创建Excel文件
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='排名查询结果', index=False)
            
            # 添加汇总信息
            summary_data = {
                '项目': [
                    '查询时间',
                    '查询类型',
                    '总查询数量',
                    '成功查询数量',
                    '失败查询数量',
                    '有排名数量',
                    '无排名数量'
                ],
                '值': [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    query_type,
                    len(results),
                    len([r for r in results if not r.get('error')]),
                    len([r for r in results if r.get('error')]),
                    len([r for r in results if r.get('rank') and r.get('rank') != '未找到']),
                    len([r for r in results if not r.get('rank') or r.get('rank') == '未找到'])
                ]
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='查询汇总', index=False)
        
        logging.info(f"排名查询结果已自动保存到: {filename}")
        return filename
        
    except Exception as e:
        logging.error(f"自动保存排名结果失败: {str(e)}")
        return None

def query_chinaz_rank(domain, keyword, api_key, max_retries=2):
    """使用站长之家API查询关键词排名（优化版）"""
    # 先检查缓存
    cached_result = get_cached_rank(domain, keyword)
    if cached_result:
        return cached_result
    
    # 智能延时控制
    smart_api_delay()
    
    for attempt in range(max_retries + 1):
        try:
            # 站长之家API接口
            api_url = "https://openapi.chinaz.net/v1/1001/baidupc_keywordranking"
            
            params = {
                'domain': domain,
                'keyword': keyword,
                'APIKey': api_key,
                'ChinazVer': '1.0'
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
            }
            
            response = requests.get(api_url, params=params, headers=headers, timeout=10, verify=False)
            response.encoding = 'utf-8'
            
            # 记录API调用次数
            config_manager.increment_api_calls(1)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('StateCode') == 1:  # 成功
                    ranks = result.get('Result', {}).get('Ranks', [])
                    final_result = None
                    
                    if ranks:
                        # 返回第一个排名结果
                        first_rank = ranks[0]
                        final_result = {
                            'rank': first_rank.get('RankStr', '未找到'),
                            'title': first_rank.get('Title', ''),
                            'url': first_rank.get('Url', ''),
                            'site_count': result.get('Result', {}).get('SiteCount', 0),
                            'total_ranks': len(ranks)
                        }
                    else:
                        final_result = {'rank': '未找到', 'title': '', 'url': '', 'site_count': 0, 'total_ranks': 0}
                    
                    # 缓存成功结果
                    set_cached_rank(domain, keyword, final_result)
                    return final_result
                    
                elif result.get('StateCode') == -1:  # API错误，不需要重试
                    error_msg = result.get('Reason', '未知错误')
                    logging.error(f"API返回错误: {error_msg}")
                    error_result = {'error': error_msg}
                    # 缓存错误结果（短时间）
                    set_cached_rank(domain, keyword, error_result)
                    return error_result
                else:
                    # 其他状态码，可能需要重试
                    if attempt < max_retries:
                        logging.warning(f"API状态码 {result.get('StateCode')}, 重试 {attempt + 1}/{max_retries}")
                        time.sleep(0.5 * (attempt + 1))  # 递增延时
                        continue
                    else:
                        error_msg = f"API状态码: {result.get('StateCode')}"
                        return {'error': error_msg}
                        
            elif response.status_code in [429, 503, 502]:  # 服务器限制，需要重试
                if attempt < max_retries:
                    delay = 2 ** attempt  # 指数退避
                    logging.warning(f"服务器响应 {response.status_code}, 等待 {delay}s 后重试 {attempt + 1}/{max_retries}")
                    time.sleep(delay)
                    continue
                else:
                    return {'error': f'服务器响应错误，状态码: {response.status_code}'}
            else:
                return {'error': f'API请求失败，状态码: {response.status_code}'}
            
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                logging.warning(f"请求超时，重试 {attempt + 1}/{max_retries} - 域名: {domain}, 关键词: {keyword}")
                time.sleep(1)
                continue
            else:
                logging.error(f"API请求超时 - 域名: {domain}, 关键词: {keyword}")
                return {'error': '请求超时'}
                
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                logging.warning(f"网络错误，重试 {attempt + 1}/{max_retries} - {str(e)}")
                time.sleep(1)
                continue
            else:
                logging.error(f"API请求网络错误 - 域名: {domain}, 关键词: {keyword}: {str(e)}")
                return {'error': f'网络错误: {str(e)}'}
                
        except Exception as e:
            logging.error(f"API请求失败 - 域名: {domain}, 关键词: {keyword}: {str(e)}")
            return {'error': f'请求失败: {str(e)}'}
    
    return {'error': '所有重试均失败'}

def batch_query_ranks(query_items, api_key, max_workers=3):
    """批量并发查询排名"""
    results = []
    completed_count = 0
    total_count = len(query_items)
    
    # 限制并发数，避免API限制
    max_workers = min(max_workers, 3)  # 最多3个并发
    
    logging.info(f"开始批量查询，共 {total_count} 个关键词，使用 {max_workers} 个线程")
    
    def query_single_rank(item, index):
        """查询单个关键词的排名"""
        try:
            domain = item['domain']
            keyword = item['final_keyword']
            
            # 查询排名
            rank_result = query_chinaz_rank(domain, keyword, api_key)
            
            # 构建结果
            result_item = {
                'index': index + 1,
                'id': item['id'],
                'url': item['url'],
                'keywords': item['keywords'],
                'title': item['title'],
                'domain': domain,
                'final_keyword': keyword,
                'previous_uv': item.get('previous_uv', 0),
                'current_uv': item.get('current_uv', 0),
                'decline_amount': item.get('decline_amount', 0),
                'decline_rate': item.get('decline_rate', 0),
                'rank': rank_result.get('rank', '未找到'),
                'rank_title': rank_result.get('title', ''),
                'rank_url': rank_result.get('url', ''),
                'site_count': rank_result.get('site_count', 0),
                'error': rank_result.get('error', None)
            }
            
            return result_item
            
        except Exception as e:
            logging.error(f"查询排名失败 {item.get('id', 'unknown')}: {str(e)}")
            return {
                'index': index + 1,
                'id': item.get('id', 'unknown'),
                'url': item.get('url', ''),
                'keywords': item.get('keywords', ''),
                'title': item.get('title', ''),
                'domain': item.get('domain', ''),
                'final_keyword': item.get('final_keyword', ''),
                'previous_uv': item.get('previous_uv', 0),
                'current_uv': item.get('current_uv', 0),
                'decline_amount': item.get('decline_amount', 0),
                'decline_rate': item.get('decline_rate', 0),
                'rank': '查询失败',
                'rank_title': '',
                'rank_url': '',
                'site_count': 0,
                'error': str(e)
            }
    
    # 使用线程池并发查询
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_index = {
            executor.submit(query_single_rank, item, i): i 
            for i, item in enumerate(query_items)
        }
        
        # 处理完成的任务
        for future in as_completed(future_to_index):
            try:
                index = future_to_index[future]
                result_item = future.result()
                results.append(result_item)
                completed_count += 1
                
                # 更新全局进度（如果需要）
                if hasattr(query_progress_data, 'update'):
                    query_progress_data.update({
                        'completed': completed_count,
                        'results': sorted(results, key=lambda x: x['index'])
                    })
                
                logging.info(f"批量查询进度: {completed_count}/{total_count}")
                
            except Exception as e:
                logging.error(f"处理查询结果失败: {str(e)}")
    
    # 按索引排序返回结果
    results.sort(key=lambda x: x['index'])
    logging.info(f"批量查询完成，共处理 {len(results)}/{total_count} 个关键词")
    
    return results

def update_query_progress(session_id, total, completed, current_url, status):
    """更新查询进度"""
    global query_progress_data
    query_progress_data.update({
        'total': total,
        'completed': completed,
        'current_url': current_url,
        'status': status,
        'session_id': session_id
    })
    logging.info(f"查询进度: {completed}/{total} - {current_url} - {status}")

def generate_rank_results_excel(rank_data, filepath):
    """生成排名查询结果Excel文件"""
    try:
        results = rank_data['results']
        query_type = rank_data['query_type']
        source_file = rank_data.get('source_file', '')
        
        # 创建DataFrame
        df_data = []
        for result in results:
            row = {
                '序号': result.get('index', ''),
                'URL': result.get('url', ''),
                '关键词': result.get('keywords', result.get('title', '')),
                '域名': result.get('domain', ''),
                '百度排名': result.get('rank', ''),
                '排名标题': result.get('rank_title', ''),
                '排名URL': result.get('rank_url', ''),
                '收录量': result.get('site_count', 0),
                '状态': result.get('error', '正常') if result.get('error') else '正常'
            }
            
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        
        # 创建Excel文件
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # 写入主要结果
            df.to_excel(writer, sheet_name='排名查询结果', index=False)
            
            # 添加汇总信息工作表
            summary_data = {
                '项目': [
                    '查询类型',
                    '数据源文件',
                    '查询时间',
                    '总查询数量',
                    '成功查询数量',
                    '失败查询数量',
                    '有排名数量',
                    '无排名数量'
                ],
                '值': [
                    {'manual': '手动输入', 'excel': 'Excel报告'}.get(query_type, query_type),
                    source_file or '手动输入',
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    len(results),
                    len([r for r in results if not r.get('error')]),
                    len([r for r in results if r.get('error')]),
                    len([r for r in results if r.get('rank') and r.get('rank') != '未找到']),
                    len([r for r in results if not r.get('rank') or r.get('rank') == '未找到'])
                ]
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='查询汇总', index=False)
        
        logging.info(f"排名查询结果Excel文件已生成: {filepath}")
        return True
        
    except Exception as e:
        logging.error(f"生成排名结果Excel文件失败: {str(e)}")
        return False

def extract_single_url_info(item, index):
    """提取单个URL的关键词信息"""
    try:
        current_url = item['url']
        
        # 提取关键词
        keywords = extract_keywords_from_url(current_url, timeout=4)  # 从8秒减少到4秒
        
        # 提取标题作为备选
        title = extract_title_from_url(current_url)
        
        # 提取域名
        domain = extract_domain_from_url(current_url)
        
        # 确定最终使用的关键词
        if keywords:
            final_keyword = keywords
            status = '成功'
        elif title:
            final_keyword = extract_first_keyword(title)
            status = '使用标题'
        else:
            final_keyword = f"ID_{item['id']}"
            status = '无关键词'
        
        result_item = {
            'index': index + 1,
            'id': item['id'],
            'url': current_url,
            'keywords': keywords or '',
            'title': title or '',
            'domain': domain,
            'final_keyword': final_keyword,
            'status': status,
            'previous_uv': item.get('previous_uv', 0),
            'current_uv': item.get('current_uv', 0),
            'decline_amount': item.get('decline_amount', 0),
            'decline_rate': item.get('decline_rate', 0)
        }
        
        return result_item
        
    except Exception as e:
        logging.error(f"处理URL失败 {item.get('id', 'unknown')}: {str(e)}")
        return {
            'index': index + 1,
            'id': item.get('id', 'unknown'),
            'url': item.get('url', ''),
            'keywords': '',
            'title': '',
            'domain': '',
            'final_keyword': f"ID_{item.get('id', 'unknown')}",
            'status': '失败',
            'error': str(e),
            'previous_uv': item.get('previous_uv', 0),
            'current_uv': item.get('current_uv', 0),
            'decline_amount': item.get('decline_amount', 0),
            'decline_rate': item.get('decline_rate', 0)
        }

@app.route('/')
def index():
    """主页面，包含简化的分析信息"""
    try:
        # 在服务器端直接获取分析信息
        analysis_data = get_latest_analysis_result()
        
        analysis_info = None
        if analysis_data:
            basic_analysis = analysis_data.get('basic_analysis', {})
            
            analysis_info = {
                'has_analysis': True,
                'total_uv': basic_analysis.get('total_uv', 0),
                'total_urls': basic_analysis.get('total_urls', 0),
                'category': basic_analysis.get('category', '全部'),
                'date_range': basic_analysis.get('date_range', '未知')
            }
        else:
            analysis_info = {
                'has_analysis': False,
                'message': '没有找到分析结果文件'
            }
        
        return render_template('rank_query_integrated.html', analysis_info=analysis_info)
        
    except Exception as e:
        logging.error(f"主页面加载失败: {str(e)}")
        analysis_info = {
            'has_analysis': False,
            'message': f'加载失败: {str(e)}'
        }
        return render_template('rank_query_integrated.html', analysis_info=analysis_info)

@app.route('/old')
def old_interface():
    """旧版界面（重定向到主页）"""
    return render_template('rank_query_integrated.html')

@app.route('/integrated')
def integrated_interface():
    """整合版界面"""
    return render_template('rank_query_integrated.html')

@app.route('/test_console')
def test_console():
    """JavaScript Console测试页面"""
    return render_template('test_console.html')

@app.route('/api/get_analysis_info')
def get_analysis_info():
    """获取分析结果信息"""
    try:
        # 获取最新的分析结果
        analysis_data = get_latest_analysis_result()
        
        if not analysis_data:
            return jsonify({
                'has_analysis': False,
                'message': '没有找到分析结果'
            })
        
        # 提取基本信息
        basic_analysis = analysis_data.get('basic_analysis', {})
        comparative_analysis = analysis_data.get('comparative_analysis', {})
        
        # 构建返回数据
        return jsonify({
            'has_analysis': True,
            'total_uv': basic_analysis.get('total_uv', 0),
            'total_urls': basic_analysis.get('total_urls', 0),
            'unique_ids': basic_analysis.get('unique_ids', 0),
            'target_decline_count': len(comparative_analysis.get('target_decline_details', [])),
            'category': basic_analysis.get('category', '全部'),
            'date_range': basic_analysis.get('date_range', ''),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logging.error(f"获取分析信息失败: {str(e)}")
        return jsonify({
            'has_analysis': False,
            'message': f'获取分析信息失败: {str(e)}'
        })

@app.route('/api/get_all_reports')
def get_all_reports():
    """获取所有可用的分析报告列表"""
    try:
        reports = get_all_analysis_reports()
        return jsonify({
            'success': True,
            'reports': reports,
            'count': len(reports)
        })
    except Exception as e:
        logging.error(f"获取报告列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'获取报告列表失败: {str(e)}',
            'reports': [],
            'count': 0
        })

@app.route('/api/get_report_info/<timestamp>')
def get_report_info(timestamp):
    """获取指定报告的数据"""
    try:
        # 直接调用本地函数获取报告数据
        report_data = get_analysis_result_by_timestamp(timestamp)
        
        if not report_data:
            return jsonify({
                'success': False,
                'error': '指定的报告不存在'
            })
        
        # 获取过滤统计信息
        filter_stats = get_filter_statistics_for_report(timestamp)
        if filter_stats:
            report_data['filter_stats'] = filter_stats
        
        return jsonify({
            'success': True,
            'report': report_data
        })
        
    except Exception as e:
        logging.error(f"获取报告数据失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'获取报告数据失败: {str(e)}'
        })

def get_filter_statistics_for_report(timestamp):
    """获取指定报告的过滤统计信息"""
    try:
        # 获取报告数据
        data = get_analysis_result_by_timestamp(timestamp)
        if not data:
            return None
            
        # 获取目标下降词详情
        comparative_analysis = data.get('comparative_analysis', {})
        target_decline_details = comparative_analysis.get('target_decline_details_full', [])
        
        if not target_decline_details:
            target_decline_details = comparative_analysis.get('target_decline_details', [])
        
        if not target_decline_details:
            return None
            
        # 统计下降量和下降率
        decline_amounts = [item.get('decline_amount', 0) for item in target_decline_details]
        decline_rates = [item.get('decline_rate', 0) for item in target_decline_details]
        
        # 计算统计信息
        return {
            'total_count': len(target_decline_details),
            'decline_amount': {
                'min': min(decline_amounts),
                'max': max(decline_amounts),
                'avg': sum(decline_amounts) / len(decline_amounts),
                'median': sorted(decline_amounts)[len(decline_amounts) // 2]
            },
            'decline_rate': {
                'min': min(decline_rates),
                'max': max(decline_rates),
                'avg': sum(decline_rates) / len(decline_rates),
                'median': sorted(decline_rates)[len(decline_rates) // 2]
            }
        }
        
    except Exception as e:
        logging.error(f"获取过滤统计信息失败: {str(e)}")
        return None

@app.route('/api/extract_from_analysis', methods=['POST'])
def extract_from_analysis():
    """从分析结果中提取目标下降词的关键词（多线程版本）"""
    try:
        data = request.get_json() or {}
        
        # 获取线程数配置，默认8个线程（从5个增加到8个）
        max_workers = data.get('max_workers', 8)
        
        # 获取timestamp参数，用于选择特定的分析报告
        timestamp = data.get('timestamp')
        
        # 获取目标下降词URL列表
        urls_data = extract_target_decline_urls_from_analysis(timestamp=timestamp)
        
        if not urls_data:
            return jsonify({'error': '没有找到目标下降词数据'})
        
        # 生成会话ID
        session_id = f"extract_{int(time.time())}"
        
        # 启动后台多线程提取任务
        def background_extract_all_threaded():
            try:
                global extract_progress_data
                results = []
                total_extracts = len(urls_data)
                completed_count = 0
                
                # 初始化进度
                extract_progress_data.update({
                    'total': total_extracts,
                    'completed': 0,
                    'current_url': '',
                    'status': 'starting',
                    'results': [],
                    'session_id': session_id,
                    'should_stop': False,
                    'max_workers': max_workers
                })
                
                # 使用线程池执行器
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # 提交所有任务
                    future_to_index = {
                        executor.submit(extract_single_url_info, item, i): i 
                        for i, item in enumerate(urls_data)
                    }
                    
                    # 处理完成的任务
                    for future in as_completed(future_to_index):
                        try:
                            # 检查是否需要停止
                            if extract_progress_data.get('should_stop', False):
                                logging.info(f"关键词提取被用户取消，已处理 {completed_count} 个URL")
                                # 取消未完成的任务
                                for f in future_to_index:
                                    if not f.done():
                                        f.cancel()
                                break
                            
                            index = future_to_index[future]
                            result_item = future.result()
                            
                            # 线程安全地更新结果
                            with extract_lock:
                                results.append(result_item)
                                completed_count += 1
                                
                                # 更新当前处理的URL
                                current_url = result_item['url']
                                
                                # 更新进度
                                extract_progress_data.update({
                                    'completed': completed_count,
                                    'current_url': current_url,
                                    'status': 'extracting',
                                    'results': sorted(results, key=lambda x: x['index'])
                                })
                                
                                # 每50个任务记录一次进度
                                if completed_count % 50 == 0:
                                    logging.info(f"已完成 {completed_count}/{total_extracts} 个URL的关键词提取")
                        
                        except Exception as e:
                            logging.error(f"处理任务结果失败: {str(e)}")
                            with extract_lock:
                                completed_count += 1
                                extract_progress_data.update({
                                    'completed': completed_count,
                                    'status': 'extracting'
                                })
                
                # 提取完成，按index排序
                results.sort(key=lambda x: x['index'])
                
                # 更新最终状态
                extract_progress_data.update({
                    'status': 'finished',
                    'results': results,
                    'completed': len(results)
                })
                
                logging.info(f"多线程关键词提取完成，共处理 {len(results)} 个URL，使用 {max_workers} 个线程")
                
                # 保存关键词提取记录到Session管理器
                try:
                    extraction_record = {
                        'session_id': session_id,
                        'total_urls': len(urls_data),
                        'successful_extractions': len(results),
                        'extraction_method': 'from_analysis',
                        'max_workers': max_workers,
                        'results': results,
                        'timestamp': datetime.now().isoformat()
                    }
                    session_manager.save_keyword_extraction_record(session_id, extraction_record)
                    logging.info(f"关键词提取记录已保存: {session_id}")
                except Exception as e:
                    logging.error(f"保存关键词提取记录失败: {str(e)}")
                
            except Exception as e:
                logging.error(f"多线程后台提取任务失败: {str(e)}")
                extract_progress_data.update({
                    'status': 'error',
                    'error': str(e)
                })
        
        # 启动后台线程
        thread = threading.Thread(target=background_extract_all_threaded)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'session_id': session_id,
            'status': 'started',
            'message': f'已启动多线程提取（{max_workers}线程），共 {len(urls_data)} 个URL',
            'total_urls': len(urls_data),
            'max_workers': max_workers
        })
        
    except Exception as e:
        logging.error(f"多线程提取关键词失败: {str(e)}")
        return jsonify({'error': f'多线程提取失败: {str(e)}'})

@app.route('/api/cancel_extract', methods=['POST'])
def cancel_extract():
    """取消当前的关键词提取任务"""
    try:
        global extract_progress_data
        
        if extract_progress_data.get('session_id'):
            extract_progress_data['should_stop'] = True
            logging.info(f"用户请求取消提取任务: {extract_progress_data.get('session_id')}")
            
            return jsonify({
                'status': 'success',
                'message': '已发送取消请求',
                'session_id': extract_progress_data.get('session_id')
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '没有正在运行的提取任务'
            })
    except Exception as e:
        logging.error(f"取消提取任务失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'取消失败: {str(e)}'
        })

@app.route('/api/extract_progress/<session_id>')
def get_extract_progress(session_id):
    """获取关键词提取进度"""
    try:
        global extract_progress_data
        
        if extract_progress_data.get('session_id') != session_id:
            return jsonify({
                'error': '会话ID不匹配或已过期',
                'session_id': session_id,
                'total': 0,
                'completed': 0,
                'progress_percent': 0,
                'status': 'not_found'
            })
        
        # 计算进度百分比
        total = extract_progress_data.get('total', 0)
        completed = extract_progress_data.get('completed', 0)
        
        if total > 0:
            progress_percent = int((completed / total) * 100)
        else:
            progress_percent = 0
        
        return jsonify({
            'total': total,
            'completed': completed,
            'progress_percent': progress_percent,
            'status': extract_progress_data.get('status', 'unknown'),
            'current_url': extract_progress_data.get('current_url', ''),
            'error': extract_progress_data.get('error', ''),
            'session_id': session_id
        })
        
    except Exception as e:
        logging.error(f"获取提取进度失败: {str(e)}")
        return jsonify({
            'error': f'获取进度失败: {str(e)}',
            'session_id': session_id,
            'total': 0,
            'completed': 0,
            'progress_percent': 0,
            'status': 'error'
        })

@app.route('/get_extract_results/<session_id>')
def get_extract_results(session_id):
    """获取关键词提取结果"""
    global extract_progress_data
    if extract_progress_data['session_id'] == session_id:
        if extract_progress_data['status'] == 'finished':
            return jsonify({
                'results': extract_progress_data['results'],
                'total_count': len(extract_progress_data['results']),
                'status': 'finished'
            })
        elif extract_progress_data['status'] == 'error':
            return jsonify({
                'error': extract_progress_data.get('error', '提取过程中发生错误'),
                'status': 'error'
            })
        else:
            return jsonify({
                'status': extract_progress_data['status'],
                'message': '提取进行中'
            })
    else:
        return jsonify({'error': '无效的会话ID'})

@app.route('/query_by_keywords', methods=['POST'])
def query_by_keywords():
    """关键词排名查询（整合版）"""
    try:
        data = request.get_json() or {}
        extract_results = data.get('extract_results', [])
        
        # 检查是否有API Key配置
        if not api_config.has_valid_api_key():
            return jsonify({'error': '请先在api_keys.json文件中配置站长之家API Key'})
        
        api_key = api_config.get_chinaz_api_key()
        
        if not extract_results:
            return jsonify({'error': '没有关键词数据需要查询'})
        
        # 生成查询会话ID
        query_session_id = f"query_{int(time.time())}"
        
        # 启动后台排名查询任务
        def background_query():
            try:
                global query_progress_data
                results = []
                total_queries = len(extract_results)
                
                # 初始化查询进度
                query_progress_data.update({
                    'total': total_queries,
                    'completed': 0,
                    'current_url': '',
                    'status': 'starting',
                    'results': [],
                    'session_id': query_session_id,
                    'should_stop': False
                })
                
                for i, item in enumerate(extract_results):
                    try:
                        # 检查是否需要停止
                        if query_progress_data.get('should_stop', False):
                            logging.info(f"排名查询被用户取消，已处理 {i} 个关键词")
                            break
                        
                        current_url = item['url']
                        query_progress_data.update({
                            'completed': i,
                            'current_url': current_url,
                            'status': 'querying'
                        })
                        
                        # 获取查询参数
                        domain = item['domain']
                        keyword = item['final_keyword']
                        
                        # 查询排名
                        rank_result = query_chinaz_rank(domain, keyword, api_key)
                        
                        # 构建结果
                        result_item = {
                            'index': i + 1,
                            'id': item['id'],
                            'url': current_url,
                            'keywords': item['keywords'],
                            'title': item['title'],
                            'domain': domain,
                            'final_keyword': keyword,
                            'previous_uv': item['previous_uv'],
                            'current_uv': item['current_uv'],
                            'decline_amount': item['decline_amount'],
                            'decline_rate': item['decline_rate'],
                            'rank': rank_result.get('rank', '未找到'),
                            'rank_title': rank_result.get('title', ''),
                            'rank_url': rank_result.get('url', ''),
                            'site_count': rank_result.get('site_count', 0),
                            'error': rank_result.get('error', None)
                        }
                        
                        results.append(result_item)
                        
                        # 更新进度
                        query_progress_data.update({
                            'completed': i + 1,
                            'results': results
                        })
                        
                        # 智能延时已在API函数中处理，无需额外延时
                        # time.sleep(1)  # 移除固定延时
                        
                    except Exception as e:
                        logging.error(f"查询排名失败 {item.get('id', 'unknown')}: {str(e)}")
                        results.append({
                            'index': i + 1,
                            'id': item.get('id', 'unknown'),
                            'url': item.get('url', ''),
                            'keywords': item.get('keywords', ''),
                            'title': item.get('title', ''),
                            'domain': item.get('domain', ''),
                            'final_keyword': item.get('final_keyword', ''),
                            'rank': '查询失败',
                            'error': str(e)
                        })
                        
                        query_progress_data.update({
                            'completed': i + 1,
                            'results': results
                        })
                
                # 查询完成
                query_progress_data.update({
                    'status': 'finished'
                })
                
                # 保存排名查询记录到Session管理器
                try:
                    query_record = {
                        'session_id': query_session_id,
                        'total_queries': len(extract_results),
                        'successful_queries': len([r for r in results if not r.get('error')]),
                        'query_method': 'from_keywords',
                        'results': results,
                        'timestamp': datetime.now().isoformat()
                    }
                    session_manager.save_rank_query_record(query_session_id, query_record)
                    logging.info(f"排名查询记录已保存: {query_session_id}")
                except Exception as e:
                    logging.error(f"保存排名查询记录失败: {str(e)}")
                
            except Exception as e:
                logging.error(f"后台排名查询任务失败: {str(e)}")
                query_progress_data.update({
                    'status': 'error',
                    'error': str(e)
                })
        
        # 启动后台线程
        thread = threading.Thread(target=background_query)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'session_id': query_session_id,
            'status': 'started',
            'message': '排名查询已启动，请等待完成',
            'total_keywords': len(extract_results)
        })
        
    except Exception as e:
        logging.error(f"根据关键词查询排名失败: {str(e)}")
        return jsonify({'error': f'查询失败: {str(e)}'})

@app.route('/export_keywords', methods=['POST'])
def export_keywords():
    """导出关键词提取结果"""
    try:
        data = request.get_json()
        session_id = data.get('session_id', '')
        
        # 获取提取结果
        global extract_progress_data
        if extract_progress_data['session_id'] != session_id:
            return jsonify({'error': '无效的会话ID'})
        
        if extract_progress_data['status'] != 'finished':
            return jsonify({'error': '关键词提取未完成'})
        
        extract_results = extract_progress_data['results']
        
        if not extract_results:
            return jsonify({'error': '没有可导出的关键词数据'})
        
        # 生成导出文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"关键词提取结果_{timestamp}.xlsx"
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)
        
        # 创建DataFrame
        df_data = []
        for result in extract_results:
            row = {
                '序号': result.get('index', ''),
                'ID': result.get('id', ''),
                'URL': result.get('url', ''),
                '提取的关键词': result.get('keywords', ''),
                '页面标题': result.get('title', ''),
                '域名': result.get('domain', ''),
                '最终关键词': result.get('final_keyword', ''),
                '状态': result.get('status', ''),
                '去年UV': result.get('previous_uv', 0),
                '今年UV': result.get('current_uv', 0),
                '下降流量': result.get('decline_amount', 0),
                '下降幅度(%)': result.get('decline_rate', 0)
            }
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        
        # 创建Excel文件
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='关键词提取结果', index=False)
            
            # 添加汇总信息
            summary_data = {
                '项目': [
                    '提取时间',
                    '总URL数量',
                    '成功提取数量',
                    '使用标题数量',
                    '无关键词数量',
                    '失败数量'
                ],
                '值': [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    len(extract_results),
                    len([r for r in extract_results if r.get('status') == '成功']),
                    len([r for r in extract_results if r.get('status') == '使用标题']),
                    len([r for r in extract_results if r.get('status') == '无关键词']),
                    len([r for r in extract_results if r.get('status') == '失败'])
                ]
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='提取汇总', index=False)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'download_url': f'/download/{filename}',
            'message': f'关键词提取结果已导出为 {filename}'
        })
        
    except Exception as e:
        logging.error(f"导出关键词提取结果失败: {str(e)}")
        return jsonify({'error': f'导出失败: {str(e)}'})

@app.route('/export_results', methods=['POST'])
def export_results():
    """导出排名查询结果"""
    try:
        # 获取查询结果
        global rank_query_results
        query_results = rank_query_results.get('results', [])
        
        if not query_results:
            return jsonify({'error': '没有可导出的查询结果'})
        
        # 生成导出文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"排名查询结果_{timestamp}.xlsx"
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)
        
        # 创建DataFrame
        df_data = []
        for result in query_results:
            row = {
                '序号': result.get('index', ''),
                'ID': result.get('id', ''),
                'URL': result.get('url', ''),
                '关键词': result.get('keywords', ''),
                '页面标题': result.get('title', ''),
                '域名': result.get('domain', ''),
                '最终关键词': result.get('final_keyword', ''),
                '百度排名': result.get('rank', ''),
                '排名标题': result.get('rank_title', ''),
                '排名URL': result.get('rank_url', ''),
                '收录量': result.get('site_count', 0),
                '状态': result.get('error', '正常') if result.get('error') else '正常'
            }
            
            # 如果有流量信息，添加流量数据
            if 'previous_uv' in result:
                row.update({
                    '去年UV': result.get('previous_uv', 0),
                    '今年UV': result.get('current_uv', 0),
                    '下降流量': result.get('decline_amount', 0),
                    '下降幅度(%)': result.get('decline_rate', 0)
                })
            
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        
        # 创建Excel文件
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='排名查询结果', index=False)
            
            # 添加汇总信息
            summary_data = {
                '项目': [
                    '查询时间',
                    '总查询数量',
                    '成功查询数量',
                    '失败查询数量',
                    '有排名数量',
                    '无排名数量'
                ],
                '值': [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    len(query_results),
                    len([r for r in query_results if not r.get('error')]),
                    len([r for r in query_results if r.get('error')]),
                    len([r for r in query_results if r.get('rank') and r.get('rank') != '未找到']),
                    len([r for r in query_results if not r.get('rank') or r.get('rank') == '未找到'])
                ]
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='查询汇总', index=False)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'download_url': f'/download/{filename}',
            'message': f'排名查询结果已导出为 {filename}'
        })
        
    except Exception as e:
        logging.error(f"导出排名查询结果失败: {str(e)}")
        return jsonify({'error': f'导出失败: {str(e)}'})

@app.route('/api/get_filter_statistics')
def get_filter_statistics():
    """获取过滤统计信息，用于设置过滤条件"""
    try:
        # 获取时间戳参数
        timestamp = request.args.get('timestamp')
        
        # 根据时间戳获取分析结果
        if timestamp:
            analysis_data = get_analysis_result_by_timestamp(timestamp)
        else:
            analysis_data = get_latest_analysis_result()
        
        if not analysis_data:
            return jsonify({'error': '没有找到分析结果'})
        
        # 获取目标下降词详情
        comparative_analysis = analysis_data.get('comparative_analysis', {})
        target_decline_details = comparative_analysis.get('target_decline_details_full', [])
        
        if not target_decline_details:
            target_decline_details = comparative_analysis.get('target_decline_details', [])
        
        if not target_decline_details:
            return jsonify({'error': '没有找到目标下降词数据'})
        
        # 统计下降量和下降率
        decline_amounts = [item.get('decline_amount', 0) for item in target_decline_details]
        decline_rates = [item.get('decline_rate', 0) for item in target_decline_details]
        
        # 计算统计信息
        stats = {
            'total_count': len(target_decline_details),
            'decline_amount': {
                'min': min(decline_amounts),
                'max': max(decline_amounts),
                'avg': sum(decline_amounts) / len(decline_amounts),
                'median': sorted(decline_amounts)[len(decline_amounts) // 2]
            },
            'decline_rate': {
                'min': min(decline_rates),
                'max': max(decline_rates),
                'avg': sum(decline_rates) / len(decline_rates),
                'median': sorted(decline_rates)[len(decline_rates) // 2]
            }
        }
        
        return jsonify({
            'success': True,
            'stats': stats,
            'timestamp': timestamp or 'latest'
        })
        
    except Exception as e:
        logging.error(f"获取过滤统计信息失败: {str(e)}")
        return jsonify({'error': f'获取统计信息失败: {str(e)}'})

@app.route('/api/extract_with_filter', methods=['POST'])
def extract_with_filter():
    """根据过滤条件从分析结果中提取目标下降词的关键词（多线程版本）"""
    try:
        data = request.get_json()
        
        # 获取过滤条件
        min_decline_uv = data.get('min_decline_uv')
        max_decline_uv = data.get('max_decline_uv')
        min_decline_rate = data.get('min_decline_rate')
        max_decline_rate = data.get('max_decline_rate')
        timestamp = data.get('timestamp')  # 获取时间戳参数
        
        # 获取线程数配置，默认8个线程（从5个增加到8个）
        max_workers = data.get('max_workers', 8)
        
        # 转换为数字类型
        if min_decline_uv is not None:
            min_decline_uv = int(min_decline_uv) if min_decline_uv != '' else None
        if max_decline_uv is not None:
            max_decline_uv = int(max_decline_uv) if max_decline_uv != '' else None
        if min_decline_rate is not None:
            min_decline_rate = float(min_decline_rate) if min_decline_rate != '' else None
        if max_decline_rate is not None:
            max_decline_rate = float(max_decline_rate) if max_decline_rate != '' else None
        
        # 获取过滤后的目标下降词URL列表
        urls_data = extract_target_decline_urls_from_analysis(
            min_decline_uv=min_decline_uv,
            max_decline_uv=max_decline_uv,
            min_decline_rate=min_decline_rate,
            max_decline_rate=max_decline_rate,
            timestamp=timestamp  # 添加timestamp参数
        )
        
        if not urls_data:
            return jsonify({'error': '根据过滤条件没有找到符合条件的目标下降词数据'})
        
        # 生成会话ID
        session_id = f"extract_{int(time.time())}"
        
        # 启动后台多线程提取任务
        def background_extract_threaded():
            try:
                global extract_progress_data
                results = []
                total_extracts = len(urls_data)
                completed_count = 0  # 确保变量初始化
                
                # 初始化进度
                extract_progress_data.update({
                    'total': total_extracts,
                    'completed': 0,
                    'current_url': '',
                    'status': 'starting',
                    'results': [],
                    'session_id': session_id,
                    'should_stop': False,
                    'max_workers': max_workers,
                    'filter_conditions': {
                        'min_decline_uv': min_decline_uv,
                        'max_decline_uv': max_decline_uv,
                        'min_decline_rate': min_decline_rate,
                        'max_decline_rate': max_decline_rate,
                        'timestamp': timestamp  # 添加timestamp到过滤条件中
                    }
                })
                
                logging.info(f"开始多线程提取，共 {total_extracts} 个URL，使用 {max_workers} 个线程")
                
                # 使用线程池执行器
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # 提交所有任务
                    future_to_index = {
                        executor.submit(extract_single_url_info, item, i): i 
                        for i, item in enumerate(urls_data)
                    }
                    
                    # 更新状态为正在提取
                    extract_progress_data['status'] = 'extracting'
                    
                    # 处理完成的任务
                    for future in as_completed(future_to_index):
                        try:
                            # 检查是否需要停止
                            if extract_progress_data.get('should_stop', False):
                                logging.info(f"关键词提取被用户取消，已处理 {completed_count} 个URL")
                                # 取消未完成的任务
                                for f in future_to_index:
                                    if not f.done():
                                        f.cancel()
                                # 更新状态为已取消
                                extract_progress_data.update({
                                    'status': 'cancelled',
                                    'completed': completed_count
                                })
                                return
                            
                            index = future_to_index[future]
                            result_item = future.result()
                            
                            # 线程安全地更新结果
                            with extract_lock:
                                results.append(result_item)
                                completed_count += 1
                                
                                # 更新当前处理的URL
                                current_url = result_item['url']
                                
                                # 计算进度百分比
                                progress_percent = int((completed_count / total_extracts) * 100)
                                
                                # 更新进度
                                extract_progress_data.update({
                                    'completed': completed_count,
                                    'current_url': current_url,
                                    'status': 'extracting',
                                    'progress_percent': progress_percent,
                                    'results': sorted(results, key=lambda x: x['index'])
                                })
                                
                                # 每10个任务记录一次进度
                                if completed_count % 10 == 0:
                                    logging.info(f"已完成 {completed_count}/{total_extracts} 个URL的关键词提取 ({progress_percent}%)")
                        
                        except Exception as e:
                            logging.error(f"处理任务结果失败: {str(e)}")
                            with extract_lock:
                                completed_count += 1
                                progress_percent = int((completed_count / total_extracts) * 100)
                                extract_progress_data.update({
                                    'completed': completed_count,
                                    'progress_percent': progress_percent,
                                    'status': 'extracting'
                                })
                
                # 检查是否被取消
                if extract_progress_data.get('should_stop', False):
                    return
                
                # 提取完成，按index排序
                results.sort(key=lambda x: x['index'])
                
                # 更新最终状态
                extract_progress_data.update({
                    'status': 'finished',
                    'results': results,
                    'completed': len(results),
                    'progress_percent': 100
                })
                
                logging.info(f"多线程关键词提取完成，共处理 {len(results)} 个URL，使用 {max_workers} 个线程")
                
                # 保存关键词提取记录到Session管理器
                try:
                    extraction_record = {
                        'session_id': session_id,
                        'total_urls': len(urls_data),
                        'successful_extractions': len(results),
                        'extraction_method': 'with_filter',
                        'filter_conditions': {
                            'min_decline_uv': min_decline_uv,
                            'max_decline_uv': max_decline_uv,
                            'min_decline_rate': min_decline_rate,
                            'max_decline_rate': max_decline_rate,
                            'timestamp': timestamp  # 添加timestamp到记录中
                        },
                        'max_workers': max_workers,
                        'results': results,
                        'timestamp': datetime.now().isoformat()
                    }
                    session_manager.save_keyword_extraction_record(session_id, extraction_record)
                    logging.info(f"过滤关键词提取记录已保存: {session_id}")
                except Exception as e:
                    logging.error(f"保存过滤关键词提取记录失败: {str(e)}")
                
            except Exception as e:
                logging.error(f"多线程后台提取任务失败: {str(e)}")
                extract_progress_data.update({
                    'status': 'error',
                    'error': str(e),
                    'progress_percent': 0
                })
        
        # 启动后台线程
        thread = threading.Thread(target=background_extract_threaded)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'session_id': session_id,
            'status': 'started',
            'message': f'已启动多线程过滤提取（{max_workers}线程），共 {len(urls_data)} 个URL符合条件',
            'total_urls': len(urls_data),
            'filter_conditions': {
                'min_decline_uv': min_decline_uv,
                'max_decline_uv': max_decline_uv,
                'min_decline_rate': min_decline_rate,
                'max_decline_rate': max_decline_rate,
                'timestamp': timestamp  # 添加timestamp到返回数据中
            }
        })
        
    except Exception as e:
        logging.error(f"多线程过滤提取关键词失败: {str(e)}")
        return jsonify({'error': f'多线程过滤提取失败: {str(e)}'})

@app.route('/api/preview_filter', methods=['POST'])
def preview_filter():
    """预览过滤条件的结果数量"""
    try:
        data = request.get_json()
        
        # 获取过滤条件
        min_decline_uv = data.get('min_decline_uv')
        max_decline_uv = data.get('max_decline_uv')
        min_decline_rate = data.get('min_decline_rate')
        max_decline_rate = data.get('max_decline_rate')
        timestamp = data.get('timestamp')  # 获取时间戳参数
        
        # 转换为数字类型
        if min_decline_uv is not None:
            min_decline_uv = int(min_decline_uv) if min_decline_uv != '' else None
        if max_decline_uv is not None:
            max_decline_uv = int(max_decline_uv) if max_decline_uv != '' else None
        if min_decline_rate is not None:
            min_decline_rate = float(min_decline_rate) if min_decline_rate != '' else None
        if max_decline_rate is not None:
            max_decline_rate = float(max_decline_rate) if max_decline_rate != '' else None
        
        # 根据时间戳获取分析结果
        if timestamp:
            analysis_data = get_analysis_result_by_timestamp(timestamp)
        else:
            analysis_data = get_latest_analysis_result()
            
        if not analysis_data:
            return jsonify({'error': '没有找到分析结果'})
            
        # 获取目标下降词详情
        comparative_analysis = analysis_data.get('comparative_analysis', {})
        target_decline_details = comparative_analysis.get('target_decline_details_full', [])
        
        if not target_decline_details:
            target_decline_details = comparative_analysis.get('target_decline_details', [])
            
        if not target_decline_details:
            return jsonify({'error': '没有找到目标下降词数据'})
            
        # 应用过滤条件
        filtered_data = []
        for item in target_decline_details:
            decline_amount = item.get('decline_amount', 0)
            decline_rate = item.get('decline_rate', 0)
            
            # 检查是否满足所有过滤条件
            if min_decline_uv is not None and decline_amount < min_decline_uv:
                continue
            if max_decline_uv is not None and decline_amount > max_decline_uv:
                continue
            if min_decline_rate is not None and decline_rate < min_decline_rate:
                continue
            if max_decline_rate is not None and decline_rate > max_decline_rate:
                continue
                
            filtered_data.append(item)
        
        # 计算过滤后的数据范围
        if filtered_data:
            decline_amounts = [item.get('decline_amount', 0) for item in filtered_data]
            decline_rates = [item.get('decline_rate', 0) for item in filtered_data]
            
            result = {
                'filtered_count': len(filtered_data),
                'decline_amount_range': {
                    'min': min(decline_amounts),
                    'max': max(decline_amounts)
                },
                'decline_rate_range': {
                    'min': min(decline_rates),
                    'max': max(decline_rates)
                }
            }
        else:
            result = {
                'filtered_count': 0,
                'decline_amount_range': {'min': 0, 'max': 0},
                'decline_rate_range': {'min': 0, 'max': 0}
            }
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"预览过滤结果失败: {str(e)}")
        return jsonify({'error': f'预览失败: {str(e)}'})

@app.route('/download/<filename>')
def download_file(filename):
    """下载导出的文件"""
    try:
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename)
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        logging.error(f"下载文件失败: {str(e)}")
        return jsonify({'error': f'下载失败: {str(e)}'}), 500

@app.route('/api/query_progress/<session_id>')
def get_query_progress(session_id):
    """获取查询进度"""
    try:
        global query_progress_data
        
        if query_progress_data.get('session_id') != session_id:
            return jsonify({
                'error': '会话ID不匹配或已过期',
                'session_id': session_id,
                'total': 0,
                'completed': 0,
                'progress_percent': 0,
                'status': 'not_found'
            })
        
        # 计算进度百分比
        total = query_progress_data.get('total', 0)
        completed = query_progress_data.get('completed', 0)
        
        if total > 0:
            progress_percent = int((completed / total) * 100)
        else:
            progress_percent = 0
        
        return jsonify({
            'total': total,
            'completed': completed,
            'progress_percent': progress_percent,
            'status': query_progress_data.get('status', 'unknown'),
            'current_url': query_progress_data.get('current_url', ''),
            'error': query_progress_data.get('error', ''),
            'session_id': session_id
        })
        
    except Exception as e:
        logging.error(f"获取查询进度失败: {str(e)}")
        return jsonify({
            'error': f'获取进度失败: {str(e)}',
            'session_id': session_id,
            'total': 0,
            'completed': 0,
            'progress_percent': 0,
            'status': 'error'
        })

@app.route('/get_query_results/<session_id>')
def get_query_results(session_id):
    """获取查询结果"""
    try:
        global query_progress_data
        
        if query_progress_data.get('session_id') != session_id:
            return jsonify({'error': '无效的会话ID'})
        
        if query_progress_data.get('status') == 'finished':
            results = query_progress_data.get('results', [])
            
            # 更新rank_query_results全局变量，以便导出功能使用
            global rank_query_results
            rank_query_results = {
                'results': results,
                'query_type': 'analysis',
                'source_file': '',
                'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S")
            }
            
            # 检查是否已经自动保存过（避免重复保存）
            if not query_progress_data.get('auto_saved', False):
                saved_filename = auto_save_ranking_results(results, 'analysis')
                query_progress_data['auto_saved'] = True
                query_progress_data['saved_filename'] = saved_filename
                if saved_filename:
                    logging.info(f"分析查询结果已自动保存: {saved_filename}")
            
            return jsonify({
                'results': results,
                'total_count': len(results),
                'query_type': 'analysis',
                'status': 'finished',
                'saved_file': query_progress_data.get('saved_filename'),
                'message': f'查询完成，结果已自动保存到 {query_progress_data.get("saved_filename")}' if query_progress_data.get('saved_filename') else '查询完成'
            })
        elif query_progress_data.get('status') == 'error':
            return jsonify({
                'error': query_progress_data.get('error', '查询过程中发生错误'),
                'status': 'error'
            })
        else:
            return jsonify({
                'status': query_progress_data.get('status', 'unknown'),
                'message': '查询进行中'
            })
            
    except Exception as e:
        logging.error(f"获取查询结果失败: {str(e)}")
        return jsonify({'error': f'获取结果失败: {str(e)}'})

@app.route('/api/cancel_query/<session_id>', methods=['POST'])
def cancel_query(session_id):
    """取消查询"""
    try:
        global query_progress_data
        
        if query_progress_data.get('session_id') != session_id:
            return jsonify({'error': '无效的会话ID'})
        
        query_progress_data['should_stop'] = True
        query_progress_data['status'] = 'cancelled'
        
        logging.info(f"用户请求取消查询任务: {session_id}")
        
        return jsonify({
            'success': True,
            'message': '查询已取消',
            'session_id': session_id
        })
        
    except Exception as e:
        logging.error(f"取消查询失败: {str(e)}")
        return jsonify({
            'error': f'取消失败: {str(e)}',
            'session_id': session_id
        })

@app.route('/api/manual_query', methods=['POST'])
def manual_query():
    """手动输入URL查询排名"""
    try:
        data = request.get_json() or {}
        urls = data.get('urls', [])
        
        # 检查是否有API Key配置
        if not api_config.has_valid_api_key():
            return jsonify({'error': '请先在api_keys.json文件中配置站长之家API Key'})
        
        api_key = api_config.get_chinaz_api_key()
        
        if not urls:
            return jsonify({'error': '请提供要查询的URL列表'})
        
        results = []
        
        for i, url in enumerate(urls):
            try:
                # 提取关键词和标题
                keywords = extract_keywords_from_url(url)
                title = extract_title_from_url(url)
                domain = extract_domain_from_url(url)
                
                # 确定最终使用的关键词
                if keywords:
                    final_keyword = keywords
                    status = '成功'
                elif title:
                    final_keyword = extract_first_keyword(title)
                    status = '使用标题'
                else:
                    final_keyword = f"URL_{i+1}"
                    status = '无关键词'
                
                # 查询排名
                rank_result = query_chinaz_rank(domain, final_keyword, api_key)
                
                result_item = {
                    'index': i + 1,
                    'url': url,
                    'keywords': keywords or '',
                    'title': title or '',
                    'domain': domain,
                    'final_keyword': final_keyword,
                    'rank': rank_result.get('rank', '未找到'),
                    'rank_title': rank_result.get('title', ''),
                    'rank_url': rank_result.get('url', ''),
                    'site_count': rank_result.get('site_count', 0),
                    'error': rank_result.get('error', None)
                }
                
                results.append(result_item)
                
                # 智能延时已在API函数中处理，无需额外延时
                # time.sleep(1)  # 移除固定延时
                
            except Exception as e:
                logging.error(f"处理URL失败 {url}: {str(e)}")
                results.append({
                    'index': i + 1,
                    'url': url,
                    'keywords': '',
                    'title': '',
                    'domain': '',
                    'final_keyword': f"URL_{i+1}",
                    'rank': '查询失败',
                    'error': str(e)
                })
        
        # 更新全局变量
        global rank_query_results
        rank_query_results = {
            'results': results,
            'query_type': 'manual',
            'source_file': '',
            'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S")
        }
        
        # 自动保存到Excel文件
        saved_filename = auto_save_ranking_results(results, 'manual')
        
        return jsonify({
            'results': results,
            'total_count': len(results),
            'query_type': 'manual',
            'saved_file': saved_filename,
            'message': f'查询完成，结果已自动保存到 {saved_filename}' if saved_filename else '查询完成'
        })
        
    except Exception as e:
        logging.error(f"手动查询失败: {str(e)}")
        return jsonify({'error': f'手动查询失败: {str(e)}'})

@app.route('/api/get_config', methods=['GET'])
def get_config():
    """获取配置信息"""
    try:
        usage_info = config_manager.get_api_usage_info()
        
        return jsonify({
            'success': True,
            'has_api_key': api_config.has_valid_api_key(),
            'config_file': api_config.get_config_file_path(),
            'usage_info': usage_info,
            'settings': {
                'auto_retry': api_config.get_setting('auto_retry', True),
                'cache_enabled': api_config.get_setting('cache_enabled', True),
                'default_concurrent': api_config.get_setting('default_concurrent', 2)
            }
        })
        
    except Exception as e:
        logging.error(f"获取配置信息失败: {str(e)}")
        return jsonify({'error': f'获取配置失败: {str(e)}'})

@app.route('/api/save_config', methods=['POST'])
def save_config():
    """保存配置信息（已移除API Key配置，请直接编辑api_keys.json文件）"""
    try:
        data = request.get_json() or {}
        
        # 保存其他设置
        if 'auto_retry' in data:
            api_config.set_setting('auto_retry', data['auto_retry'])
        
        if 'cache_enabled' in data:
            api_config.set_setting('cache_enabled', data['cache_enabled'])
        
        if 'default_concurrent' in data:
            api_config.set_setting('default_concurrent', data['default_concurrent'])
        
            return jsonify({
                'success': True,
            'message': '配置已保存。如需修改API Key，请直接编辑api_keys.json文件'
            })
            
    except Exception as e:
        logging.error(f"保存配置失败: {str(e)}")
        return jsonify({'error': f'保存配置失败: {str(e)}'})

@app.route('/api/check_api_quota', methods=['POST'])
def check_api_quota():
    """检查API余量"""
    try:
        api_key = request.json.get('api_key')
        if not api_key:
            return jsonify({'error': '请提供API密钥'})
        
        # 站长之家API接口
        quota_url = "https://openapi.chinaz.net/v1/1001/user_info"
        
        params = {
            'APIKey': api_key,
            'ChinazVer': '1.0'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json'
        }
        
        response = requests.get(quota_url, params=params, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('StateCode') == 1:
                user_info = result.get('Result', {})
                return jsonify({
                    'success': True,
                    'remaining_quota': user_info.get('Surplus', 0),
                    'total_quota': user_info.get('MaxNum', 0),
                    'used_quota': user_info.get('MaxNum', 0) - user_info.get('Surplus', 0)
                })
            else:
                return jsonify({'error': result.get('Reason', '查询失败')})
        else:
            return jsonify({'error': f'请求失败，状态码: {response.status_code}'})
            
    except Exception as e:
        logging.error(f"查询API余量失败: {str(e)}")
        return jsonify({'error': f'查询失败: {str(e)}'})

@app.route('/api/get_cache_stats', methods=['GET'])
def get_cache_stats():
    """获取缓存统计信息"""
    try:
        with cache_lock:
            total_cache_items = len(rank_cache)
            
            # 计算缓存命中率（基于API调用统计）
            usage_info = config_manager.get_api_usage_info()
            total_api_calls = usage_info.get('total_calls', 0)
            
            # 计算当前API调用频率
            current_time = time.time()
            recent_calls = [t for t in api_call_times if current_time - t < 60]
            current_qps = len(recent_calls)
            
            # 计算平均响应时间（毫秒）
            if recent_calls:
                avg_response_time = int((current_time - recent_calls[0]) / len(recent_calls) * 1000)
            else:
                avg_response_time = 0
            
            # 使用全局缓存命中计数
            with cache_hits_lock:
                current_cache_hits = cache_hits
            
            return jsonify({
                'success': True,
                'cache_items': total_cache_items,
                'cache_hit_rate': round((current_cache_hits / max(total_api_calls, 1)) * 100, 1),
                'api_calls_saved': current_cache_hits,
                'avg_response_time': avg_response_time,
                'current_qps': current_qps,
                'total_api_calls': total_api_calls
            })
            
    except Exception as e:
        logging.error(f"获取缓存统计失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/reset_usage_stats', methods=['POST'])
def reset_usage_stats():
    """重置使用统计"""
    try:
        # 重置配置管理器中的使用统计
        config_manager.reset_usage_stats()
        
        return jsonify({
            'success': True,
            'message': '使用统计已重置'
        })
        
    except Exception as e:
        logging.error(f"重置使用统计失败: {str(e)}")
        return jsonify({'error': f'重置失败: {str(e)}'})

@app.route('/api/keyword_history')
def get_keyword_history():
    """获取关键词提取历史记录"""
    try:
        limit = request.args.get('limit', 20, type=int)
        history = session_manager.get_keyword_extraction_history(limit)
        
        # 格式化历史记录
        formatted_history = []
        for record in history:
            extraction_data = record.get('extraction_data', {})
            formatted_record = {
                'session_id': record.get('session_id'),
                'timestamp': record.get('timestamp'),
                'total_urls': extraction_data.get('total_urls', 0),
                'successful_extractions': extraction_data.get('successful_extractions', 0),
                'extraction_method': extraction_data.get('extraction_method', 'unknown'),
                'filter_conditions': extraction_data.get('filter_conditions'),
                'file_size': record.get('file_size', 0),
                'formatted_time': datetime.fromisoformat(record.get('timestamp', '')).strftime('%Y-%m-%d %H:%M:%S') if record.get('timestamp') else '未知',
                'success_rate': round((extraction_data.get('successful_extractions', 0) / extraction_data.get('total_urls', 1)) * 100, 1) if extraction_data.get('total_urls', 0) > 0 else 0
            }
            formatted_history.append(formatted_record)
        
        return jsonify({
            'success': True,
            'history': formatted_history,
            'total_count': len(formatted_history)
        })
        
    except Exception as e:
        logging.error(f"获取关键词提取历史失败: {str(e)}")
        return jsonify({'error': f'获取历史失败: {str(e)}'})

@app.route('/api/rank_history')
def get_rank_history():
    """获取排名查询历史记录"""
    try:
        limit = request.args.get('limit', 20, type=int)
        history = session_manager.get_rank_query_history(limit)
        
        # 格式化历史记录
        formatted_history = []
        for record in history:
            query_data = record.get('query_data', {})
            # 判断是否为后台任务
            is_background_task = query_data.get('query_method') == 'background_task'
            task_name = query_data.get('task_name', '未知任务')
            task_status = query_data.get('status', 'unknown')
            
            formatted_record = {
                'session_id': record.get('session_id'),
                'timestamp': record.get('timestamp'),
                'total_queries': query_data.get('total_queries', 0),
                'successful_queries': query_data.get('successful_queries', 0),
                'query_method': query_data.get('query_method', 'unknown'),
                'is_background_task': is_background_task,
                'task_name': task_name,
                'task_status': task_status,
                'file_size': record.get('file_size', 0),
                'formatted_time': datetime.fromisoformat(record.get('timestamp', '')).strftime('%Y-%m-%d %H:%M:%S') if record.get('timestamp') else '未知',
                'success_rate': round((query_data.get('successful_queries', 0) / query_data.get('total_queries', 1)) * 100, 1) if query_data.get('total_queries', 0) > 0 else 0
            }
            formatted_history.append(formatted_record)
        
        return jsonify({
            'success': True,
            'history': formatted_history,
            'total_count': len(formatted_history)
        })
        
    except Exception as e:
        logging.error(f"获取排名查询历史失败: {str(e)}")
        return jsonify({'error': f'获取历史失败: {str(e)}'})

@app.route('/api/history_statistics')
def get_history_statistics():
    """获取历史记录统计信息"""
    try:
        stats = session_manager.get_history_statistics()
        return jsonify({
            'success': True,
            'statistics': stats
        })
        
    except Exception as e:
        logging.error(f"获取历史记录统计失败: {str(e)}")
        return jsonify({'error': f'获取统计失败: {str(e)}'})

@app.route('/api/keyword_history/<session_id>')
def get_keyword_history_detail(session_id):
    """获取特定关键词提取记录的详细信息"""
    try:
        record = session_manager.get_keyword_extraction_record(session_id)
        
        if not record:
            return jsonify({'error': '记录不存在'}), 404
        
        return jsonify({
            'success': True,
            'record': record
        })
        
    except Exception as e:
        logging.error(f"获取关键词提取记录详情失败: {str(e)}")
        return jsonify({'error': f'获取记录详情失败: {str(e)}'})

@app.route('/api/rank_history/<session_id>')
def get_rank_history_detail(session_id):
    """获取特定排名查询记录的详细信息"""
    try:
        record = session_manager.get_rank_query_record(session_id)
        
        if not record:
            return jsonify({'error': '记录不存在'}), 404
        
        return jsonify({
            'success': True,
            'record': record
        })
        
    except Exception as e:
        logging.error(f"获取排名查询记录详情失败: {str(e)}")
        return jsonify({'error': f'获取记录详情失败: {str(e)}'})

@app.route('/api/delete_keyword_history/<session_id>', methods=['DELETE'])
def delete_keyword_history(session_id):
    """删除特定的关键词提取记录"""
    try:
        success = session_manager.delete_keyword_extraction_record(session_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '记录删除成功'
            })
        else:
            return jsonify({'error': '记录不存在或删除失败'}), 404
        
    except Exception as e:
        logging.error(f"删除关键词提取记录失败: {str(e)}")
        return jsonify({'error': f'删除记录失败: {str(e)}'})

@app.route('/api/delete_rank_history/<session_id>', methods=['DELETE'])
def delete_rank_history(session_id):
    """删除特定的排名查询记录"""
    try:
        success = session_manager.delete_rank_query_record(session_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '记录删除成功'
            })
        else:
            return jsonify({'error': '记录不存在或删除失败'}), 404
        
    except Exception as e:
        logging.error(f"删除排名查询记录失败: {str(e)}")
        return jsonify({'error': f'删除记录失败: {str(e)}'})

@app.route('/api/cleanup_old_records', methods=['POST'])
def cleanup_old_records():
    """清理过期的历史记录"""
    try:
        data = request.get_json() or {}
        max_age_days = data.get('max_age_days', 30)
        
        # 清理关键词提取记录
        keyword_deleted = session_manager.cleanup_old_keyword_records(max_age_days)
        
        # 清理排名查询记录
        rank_deleted = session_manager.cleanup_old_rank_records(max_age_days)
        
        return jsonify({
            'success': True,
            'message': f'清理完成：删除了 {keyword_deleted} 个关键词记录和 {rank_deleted} 个排名记录',
            'keyword_deleted': keyword_deleted,
            'rank_deleted': rank_deleted
        })
        
    except Exception as e:
        logging.error(f"清理过期记录失败: {str(e)}")
        return jsonify({'error': f'清理失败: {str(e)}'})

@app.route('/history')
def history_page():
    """历史记录页面"""
    return render_template('history.html')

# ================================
# 后台任务管理 API
# ================================

@app.route('/api/tasks/create_rank_query', methods=['POST'])
def create_rank_query_task():
    """创建排名查询任务"""
    try:
        data = request.get_json() or {}
        urls = data.get('urls', [])
        
        # 检查是否有API Key配置
        if not api_config.has_valid_api_key():
            return jsonify({'error': '请先在api_keys.json文件中配置站长之家API Key'})
        
        api_key = api_config.get_chinaz_api_key()
        
        if not urls:
            return jsonify({'error': '请提供要查询的URL列表'})
        
        # 创建任务
        task_id = task_manager.create_task(
            task_type='rank_query',
            data={
                'urls': urls,
                'total_count': len(urls)
            },
            api_key=api_key,
            status=TaskStatus.PENDING
        )
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'排名查询任务已创建: {task_id}',
            'total_keywords': len(urls)
        })
        
    except Exception as e:
        logging.error(f"创建排名查询任务失败: {str(e)}")
        return jsonify({'error': f'创建任务失败: {str(e)}'})

@app.route('/api/tasks/start/<task_id>', methods=['POST'])
def start_task(task_id):
    """启动任务"""
    try:
        success = rank_query_executor.start_rank_query_task(task_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'任务 {task_id} 已启动'
            })
        else:
            return jsonify({'error': '启动任务失败'})
        
    except Exception as e:
        logging.error(f"启动任务失败: {str(e)}")
        return jsonify({'error': f'启动任务失败: {str(e)}'})

@app.route('/api/tasks/progress/<task_id>')
def get_task_progress(task_id):
    """获取任务进度"""
    try:
        progress = rank_query_executor.get_task_progress(task_id)
        
        if progress:
            return jsonify({
                'success': True,
                'progress': progress
            })
        else:
            return jsonify({'error': '任务不存在'})
        
    except Exception as e:
        logging.error(f"获取任务进度失败: {str(e)}")
        return jsonify({'error': f'获取进度失败: {str(e)}'})

@app.route('/api/tasks/results/<task_id>')
def get_task_results(task_id):
    """获取任务结果"""
    try:
        results = rank_query_executor.get_task_results(task_id)
        
        if results is not None:
            # 更新rank_query_results全局变量，以便导出功能使用
            global rank_query_results
            rank_query_results = {
                'results': results,
                'query_type': 'task',
                'source_file': '',
                'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S")
            }
            
            # 自动保存到Excel文件
            saved_filename = auto_save_ranking_results(results, 'task')
            
            return jsonify({
                'success': True,
                'results': results,
                'total_results': len(results),
                'saved_file': saved_filename,
                'message': f'任务完成，结果已自动保存到 {saved_filename}' if saved_filename else '任务完成'
            })
        else:
            return jsonify({'error': '任务不存在'})
        
    except Exception as e:
        logging.error(f"获取任务结果失败: {str(e)}")
        return jsonify({'error': f'获取结果失败: {str(e)}'})

@app.route('/api/tasks/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id):
    """取消任务"""
    try:
        success = rank_query_executor.cancel_task(task_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'任务 {task_id} 已取消'
            })
        else:
            return jsonify({'error': '取消任务失败'})
        
    except Exception as e:
        logging.error(f"取消任务失败: {str(e)}")
        return jsonify({'error': f'取消任务失败: {str(e)}'})

@app.route('/api/tasks/pause/<task_id>', methods=['POST'])
def pause_task(task_id):
    """暂停任务"""
    try:
        success = rank_query_executor.pause_task(task_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'任务 {task_id} 已暂停'
            })
        else:
            return jsonify({'error': '暂停任务失败'})
        
    except Exception as e:
        logging.error(f"暂停任务失败: {str(e)}")
        return jsonify({'error': f'暂停任务失败: {str(e)}'})

@app.route('/api/tasks/resume/<task_id>', methods=['POST'])
def resume_task(task_id):
    """恢复任务"""
    try:
        success = rank_query_executor.resume_task(task_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'任务 {task_id} 已恢复'
            })
        else:
            return jsonify({'error': '恢复任务失败'})
        
    except Exception as e:
        logging.error(f"恢复任务失败: {str(e)}")
        return jsonify({'error': f'恢复任务失败: {str(e)}'})

@app.route('/api/tasks/list')
def list_tasks():
    """获取所有任务列表"""
    try:
        tasks = rank_query_executor.get_all_tasks()
        
        return jsonify({
            'success': True,
            'tasks': tasks,
            'total_tasks': len(tasks)
        })
        
    except Exception as e:
        logging.error(f"获取任务列表失败: {str(e)}")
        return jsonify({'error': f'获取任务列表失败: {str(e)}'})

@app.route('/api/tasks/delete/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """删除任务"""
    try:
        success = task_manager.delete_task(task_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'任务 {task_id} 已删除'
            })
        else:
            return jsonify({'error': '删除任务失败'})
        
    except Exception as e:
        logging.error(f"删除任务失败: {str(e)}")
        return jsonify({'error': f'删除任务失败: {str(e)}'})

@app.route('/api/tasks/cleanup', methods=['POST'])
def cleanup_old_tasks():
    """清理旧任务"""
    try:
        data = request.get_json() or {}
        days = data.get('days', 7)
        
        deleted_count = task_manager.cleanup_old_tasks(days)
        
        return jsonify({
            'success': True,
            'message': f'已清理 {deleted_count} 个旧任务',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        logging.error(f"清理旧任务失败: {str(e)}")
        return jsonify({'error': f'清理任务失败: {str(e)}'})

@app.route('/api/tasks/statistics')
def get_task_statistics():
    """获取任务统计信息"""
    try:
        stats = task_manager.get_task_statistics()
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
        
    except Exception as e:
        logging.error(f"获取任务统计失败: {str(e)}")
        return jsonify({'error': f'获取统计失败: {str(e)}'})

@app.route('/api/tasks/export_results/<task_id>')
def export_task_results(task_id):
    """导出任务结果"""
    try:
        # 获取任务结果
        results = rank_query_executor.get_task_results(task_id)
        task_progress = rank_query_executor.get_task_progress(task_id)
        
        if not results:
            return jsonify({'error': '任务不存在或无结果'})
        
        # 生成导出文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_name = task_progress.get('task_name', 'unknown') if task_progress else 'unknown'
        filename = f"排名查询结果_{task_name}_{timestamp}.xlsx"
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)
        
        # 创建DataFrame
        df_data = []
        for result in results:
            row = {
                '序号': result.get('index', ''),
                'ID': result.get('id', ''),
                'URL': result.get('url', ''),
                '提取的关键词': result.get('keywords', ''),
                '页面标题': result.get('title', ''),
                '域名': result.get('domain', ''),
                '查询关键词': result.get('final_keyword', ''),
                '去年UV': result.get('previous_uv', 0),
                '今年UV': result.get('current_uv', 0),
                '下降流量': result.get('decline_amount', 0),
                '下降幅度(%)': result.get('decline_rate', 0),
                '百度排名': result.get('rank', ''),
                '排名标题': result.get('rank_title', ''),
                '排名URL': result.get('rank_url', ''),
                '收录量': result.get('site_count', 0),
                '查询时间': result.get('query_time', ''),
                '查询状态': '成功' if result.get('success', False) else '失败',
                '错误信息': result.get('error', '')
            }
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        
        # 创建Excel文件
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='排名查询结果', index=False)
            
            # 添加汇总信息
            summary_data = {
                '项目': [
                    '任务ID',
                    '任务名称',
                    '查询时间',
                    '总查询数量',
                    '成功查询数量',
                    '失败查询数量',
                    '成功率'
                ],
                '值': [
                    task_id,
                    task_name,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    len(results),
                    len([r for r in results if r.get('success', False)]),
                    len([r for r in results if not r.get('success', False)]),
                    f"{round(len([r for r in results if r.get('success', False)]) / len(results) * 100, 1)}%" if results else "0%"
                ]
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='查询汇总', index=False)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'download_url': f'/download/{filename}',
            'message': f'排名查询结果已导出为 {filename}'
        })
        
    except Exception as e:
        logging.error(f"导出任务结果失败: {str(e)}")
        return jsonify({'error': f'导出失败: {str(e)}'})

@app.route('/tasks')
def tasks_page():
    """任务管理页面"""
    return render_template('tasks.html')

@app.route('/view_excel_report/<filename>')
def view_excel_report(filename):
    """查看Excel报告"""
    try:
        file_path = os.path.join(app.config['EXPORT_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'message': '报告文件不存在'
            })
            
        # 读取Excel文件
        df = pd.read_excel(file_path)
        
        # 转换为HTML表格
        html_table = df.to_html(classes='table table-striped', index=False)
        
        return render_template('view_excel.html',
                             filename=filename,
                             table_html=html_table)
    
    except Exception as e:
        logging.error(f"查看Excel报告失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'查看报告失败: {str(e)}'
        })

@app.route('/download_excel_report/<filename>')
def download_excel_report(filename):
    """下载Excel报告"""
    try:
        file_path = os.path.join(app.config['EXPORT_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'message': '报告文件不存在'
            })
        
        return send_file(file_path,
                        as_attachment=True,
                        download_name=filename)
    
    except Exception as e:
        logging.error(f"下载Excel报告失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'下载报告失败: {str(e)}'
        })

@app.route('/download_json_report/<timestamp>')
def download_json_report(timestamp):
    """下载JSON报告"""
    try:
        json_file = os.path.join(os.path.dirname(__file__), 
                                'analysis_results', 
                                f'analysis_{timestamp}.json')
        
        if not os.path.exists(json_file):
            return jsonify({
                'success': False,
                'message': 'JSON报告文件不存在'
            })
        
        return send_file(json_file,
                        as_attachment=True,
                        download_name=f'analysis_{timestamp}.json')
    
    except Exception as e:
        logging.error(f"下载JSON报告失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'下载报告失败: {str(e)}'
        })

@app.route('/api/health_check')
def health_check():
    """健康检查接口"""
    try:
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'service': 'rank_query',
            'version': '1.0'
        })
    except Exception as e:
        logging.error(f"健康检查失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# 允许跨域访问
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# 根据环境获取分析服务的URL
def get_analysis_service_url():
    """获取分析服务的URL"""
    hostname = socket.gethostname()
    if hostname == 'localhost' or '127.0.0.1' in hostname or hostname.startswith('bogon'):
        # 本地开发环境
        return 'http://localhost:5001'
    else:
        # 线上环境
        return 'http://127.0.0.1:5001'  # 在服务器上使用本地地址

@app.route('/api/get_analysis_reports')
def get_analysis_reports():
    """获取可用的分析报告列表"""
    try:
        # 直接调用本地函数获取报告列表
        reports = get_all_analysis_reports()
        
        return jsonify({
            'success': True,
            'reports': reports,
            'count': len(reports)
        })
        
    except Exception as e:
        logging.error(f"获取分析报告列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'获取报告列表失败: {str(e)}',
            'reports': [],
            'count': 0
        })

@app.route('/api/get_report_data/<timestamp>')
def get_report_data(timestamp):
    """获取指定报告的数据"""
    try:
        # 直接调用本地函数获取报告数据
        report_data = get_analysis_result_by_timestamp(timestamp)
        
        if not report_data:
            return jsonify({
                'success': False,
                'error': '指定的报告不存在'
            })
        
        return jsonify({
            'success': True,
            'report': report_data
        })
        
    except Exception as e:
        logging.error(f"获取报告数据失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'获取报告数据失败: {str(e)}'
        })

# 添加前端需要的 /rank/api/ 路由
@app.route('/rank/api/get_all_reports')
def rank_get_all_reports():
    """获取所有报告列表 - 前端兼容路由"""
    return get_analysis_reports()

@app.route('/rank/api/get_report_info/<timestamp>')
def rank_get_report_info(timestamp):
    """获取指定报告信息 - 前端兼容路由"""
    return get_report_data(timestamp)

@app.route('/rank/api/get_analysis_info')
def rank_get_analysis_info():
    """获取分析信息 - 前端兼容路由（简化版）"""
    try:
        # 检查是否提供了timestamp参数
        timestamp = request.args.get('timestamp')
        
        if timestamp:
            # 获取指定时间戳的分析结果
            analysis_data = get_analysis_result_by_timestamp(timestamp)
        else:
            # 获取最新的分析结果
            analysis_data = get_latest_analysis_result()
        
        if not analysis_data:
            return jsonify({
                'has_analysis': False,
                'message': '没有找到分析结果文件'
            })
        
        # 简化获取数据结构 - 只获取基本信息
        basic_analysis = analysis_data.get('basic_analysis', {})
        
        return jsonify({
            'has_analysis': True,
            'total_uv': basic_analysis.get('total_uv', 0),
            'total_urls': basic_analysis.get('total_urls', 0),
            'category': basic_analysis.get('category', '全部'),
            'date_range': basic_analysis.get('date_range', '未知'),
            'timestamp': timestamp if timestamp else 'latest'
        })
        
    except Exception as e:
        logging.error(f"获取分析信息失败: {str(e)}")
        return jsonify({
            'has_analysis': False,
            'message': f'获取分析信息失败: {str(e)}'
        })

@app.route('/rank/api/get_filter_statistics')
def rank_get_filter_statistics():
    """获取过滤统计信息 - 前端兼容路由"""
    try:
        timestamp = request.args.get('timestamp')
        
        # 获取分析数据
        if timestamp:
            analysis_data = get_analysis_result_by_timestamp(timestamp)
        else:
            analysis_data = get_latest_analysis_result()
            
        if not analysis_data:
            return jsonify({
                'error': '没有找到分析数据'
            })
        
        # 获取目标下降词详情来计算统计信息
        comparative_analysis = analysis_data.get('comparative_analysis', {})
        target_decline_details = comparative_analysis.get('target_decline_details_full', [])
        
        if not target_decline_details:
            target_decline_details = comparative_analysis.get('target_decline_details', [])
        
        if not target_decline_details:
            return jsonify({
                'error': '没有找到目标下降词数据'
            })
        
        # 计算统计信息
        decline_amounts = [item.get('decline_amount', 0) for item in target_decline_details]
        decline_rates = [item.get('decline_rate', 0) for item in target_decline_details]
        
        stats = {
            'total_count': len(target_decline_details),
            'decline_amount': {
                'min': min(decline_amounts) if decline_amounts else 0,
                'max': max(decline_amounts) if decline_amounts else 0,
                'avg': sum(decline_amounts) / len(decline_amounts) if decline_amounts else 0,
                'median': sorted(decline_amounts)[len(decline_amounts) // 2] if decline_amounts else 0
            },
            'decline_rate': {
                'min': min(decline_rates) if decline_rates else 0,
                'max': max(decline_rates) if decline_rates else 0,
                'avg': sum(decline_rates) / len(decline_rates) if decline_rates else 0,
                'median': sorted(decline_rates)[len(decline_rates) // 2] if decline_rates else 0
            }
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logging.error(f"获取过滤统计失败: {str(e)}")
        return jsonify({
            'error': f'获取统计信息失败: {str(e)}'
        })

@app.route('/rank/api/get_config')
def rank_get_config():
    """获取配置信息 - 前端兼容路由"""
    try:
        usage_info = config_manager.get_api_usage_info()
        
        # 获取缓存统计用于查询统计显示
        cache_stats = {
            'cache_hit_rate': 0.0,
            'api_calls_saved': 0,
            'avg_response_time': 0,
            'current_qps': 0
        }
        
        try:
            # 直接调用get_cache_stats函数
            cache_response = get_cache_stats()
            if hasattr(cache_response, 'get_json'):
                cache_data = cache_response.get_json()
                if cache_data and cache_data.get('success'):
                    cache_stats.update({
                        'cache_hit_rate': cache_data.get('cache_hit_rate', 0.0),
                        'api_calls_saved': cache_data.get('api_calls_saved', 0),
                        'avg_response_time': cache_data.get('avg_response_time', 0),
                        'current_qps': cache_data.get('current_qps', 0)
                    })
        except Exception as e:
            logging.warning(f"获取缓存统计失败: {str(e)}")
        
        # 合并usage_info和cache_stats
        combined_usage_info = {}
        if usage_info:
            combined_usage_info.update(usage_info)
        combined_usage_info.update(cache_stats)
        
        return jsonify({
            'success': True,
            'has_api_key': api_config.has_valid_api_key(),  # 修复字段名
            'api_configured': api_config.has_valid_api_key(),
            'api_key_preview': api_config.get_chinaz_api_key()[:10] + '...' if api_config.has_valid_api_key() else None,
            'usage_info': combined_usage_info,
            'settings': {
                'auto_retry': api_config.get_setting('auto_retry', True),
                'cache_enabled': api_config.get_setting('cache_enabled', True),
                'default_concurrent': api_config.get_setting('default_concurrent', 2)
            }
        })
    except Exception as e:
        logging.error(f"获取配置信息失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'获取配置失败: {str(e)}'
        })

# 添加缺失的前端兼容路由
@app.route('/rank/api/extract_from_analysis', methods=['POST'])
def rank_extract_from_analysis():
    """从分析结果中提取关键词 - 前端兼容路由"""
    return extract_from_analysis()

@app.route('/rank/api/extract_with_filter', methods=['POST'])
def rank_extract_with_filter():
    """根据过滤条件提取关键词 - 前端兼容路由"""
    return extract_with_filter()

@app.route('/rank/api/preview_filter', methods=['POST'])
def rank_preview_filter():
    """预览过滤条件结果 - 前端兼容路由"""
    return preview_filter()

@app.route('/rank/api/cancel_extract', methods=['POST'])
def rank_cancel_extract():
    """取消提取任务 - 前端兼容路由"""
    return cancel_extract()

@app.route('/rank/api/manual_query', methods=['POST'])
def rank_manual_query():
    """手动查询 - 前端兼容路由"""
    return manual_query()

@app.route('/rank/api/get_cache_stats', methods=['GET'])
def rank_get_cache_stats():
    """获取缓存统计 - 前端兼容路由"""
    return get_cache_stats()

@app.route('/rank/api/get_historical_results')
def get_historical_results():
    """获取历史排名查询结果列表"""
    try:
        import os
        import glob
        from datetime import datetime
        
        exports_dir = os.path.join(os.path.dirname(__file__), 'exports')
        if not os.path.exists(exports_dir):
            return jsonify({'success': False, 'message': '导出目录不存在'})
        
        # 查找排名查询结果文件
        pattern = os.path.join(exports_dir, '排名查询结果_*.xlsx')
        files = glob.glob(pattern)
        
        results = []
        for file_path in files:
            try:
                filename = os.path.basename(file_path)
                # 提取时间戳
                timestamp_str = filename.replace('排名查询结果_', '').replace('.xlsx', '')
                timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                
                results.append({
                    'filename': filename,
                    'filepath': file_path,
                    'timestamp': timestamp_str,
                    'display_time': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'file_size': round(file_size, 2),
                    'date': timestamp.strftime('%Y-%m-%d')
                })
            except Exception as e:
                logging.warning(f"解析文件失败 {file_path}: {str(e)}")
                continue
        
        # 按时间倒序排列
        results.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'results': results,
            'total': len(results)
        })
        
    except Exception as e:
        logging.error(f"获取历史结果失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/rank/api/load_historical_result/<timestamp>')
def load_historical_result(timestamp):
    """加载指定的历史排名查询结果"""
    try:
        import pandas as pd
        import numpy as np
        import os
        
        exports_dir = os.path.join(os.path.dirname(__file__), 'exports')
        filename = f'排名查询结果_{timestamp}.xlsx'
        filepath = os.path.join(exports_dir, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': '文件不存在'})
        
        # 读取Excel文件
        df = pd.read_excel(filepath)
        
        # 安全获取值的函数，处理NaN和None
        def safe_get(value, default=''):
            if pd.isna(value) or value is None:
                return default
            if isinstance(value, (int, float)):
                return int(value) if default == 0 else value
            return str(value)
        
        # 转换为前端需要的格式
        results = []
        for index, row in df.iterrows():
            result = {
                'index': safe_get(row.get('序号'), index + 1),
                'id': safe_get(row.get('ID'), ''),
                'url': safe_get(row.get('URL'), ''),
                'keywords': safe_get(row.get('关键词'), ''),
                'final_keyword': safe_get(row.get('最终关键词'), ''),
                'domain': safe_get(row.get('域名'), ''),
                'rank': safe_get(row.get('百度排名'), ''),
                'site_count': safe_get(row.get('收录量'), 0),
                'previous_uv': safe_get(row.get('去年UV'), 0),
                'current_uv': safe_get(row.get('今年UV'), 0),
                'decline_amount': safe_get(row.get('下降流量'), 0),
                'decline_rate': safe_get(row.get('下降幅度(%)'), 0),
                'status': safe_get(row.get('状态'), ''),
                'page_title': safe_get(row.get('页面标题'), ''),
                'rank_title': safe_get(row.get('排名标题'), ''),
                'rank_url': safe_get(row.get('排名URL'), ''),
                'error': safe_get(row.get('状态'), '') != '正常'
            }
            results.append(result)
        
        # 更新全局变量
        global rank_query_results
        rank_query_results = {
            'results': results,
            'query_type': 'historical',
            'source_file': filename,
            'timestamp': timestamp
        }
        
        return jsonify({
            'success': True,
            'results': results,
            'total': len(results),
            'source_file': filename,
            'timestamp': timestamp
        })
        
    except Exception as e:
        logging.error(f"加载历史结果失败: {str(e)}")
        return jsonify({'success': False, 'error': f'加载失败: {str(e)}'})

@app.route('/historical_results')
def historical_results_page():
    """历史查询结果管理页面"""
    try:
        return send_from_directory('.', 'historical_results.html')
    except Exception as e:
        logging.error(f"发送历史结果页面失败: {str(e)}")
        return f"<h1>页面加载错误</h1><p>{str(e)}</p>"


if __name__ == '__main__':
    init_dir()
    logging.info("正在启动排名查询应用...")
    # api_config已经是APIConfig的实例，不需要再次初始化
    
    # 检查API key是否配置
    if api_config.has_valid_api_key():
        logging.info(f"API Key已配置: {api_config.get_chinaz_api_key()[:10]}...")
    else:
        logging.warning("API Key未配置或无效，请在api_keys.json中配置")
        
    app.run(host='0.0.0.0', port=5051, debug=True)