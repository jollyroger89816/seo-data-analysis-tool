import os
import pandas as pd
import requests
import json
import re
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from werkzeug.utils import secure_filename
import time
# import matplotlib.pyplot as plt
# import numpy as np
import logging
from bs4 import BeautifulSoup
import random
from urllib.parse import urlparse
import threading
import numpy as np
from session_manager import session_manager
import glob

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def convert_to_json_serializable(obj):
    """转换对象为JSON可序列化格式"""
    if isinstance(obj, (pd.DataFrame, pd.Series)):
        return obj.to_dict()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_json_serializable(i) for i in obj]
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj

app = Flask(__name__)
app.secret_key = "keyword_rank_analyzer_secret_key"
app.config['UPLOAD_FOLDER'] = os.path.abspath('uploads')
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls'}
app.config['EXPORT_FOLDER'] = os.path.abspath('exports')

# 添加abs函数到Jinja2环境
app.jinja_env.globals.update(abs=abs)

# 创建上传和导出文件夹
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)

# 全局进度跟踪
progress_data = {
    'current_step': '',
    'progress': 0,
    'total_steps': 0,
    'details': '',
    'session_id': None
}

# 全局变量用于存储分析结果（避免Flask session上下文问题）
analysis_results = {}
analysis_status = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def update_progress(step, progress, total_steps, details='', session_id=None):
    """更新分析进度"""
    global progress_data
    progress_data.update({
        'current_step': step,
        'progress': progress,
        'total_steps': total_steps,
        'details': details,
        'session_id': session_id
    })
    
    logging.info(f"进度更新: {step} ({progress}/{total_steps}) - {details}")

def extract_id_from_url(url):
    """从URL中提取ID，包含前两级目录作为前缀，避免ID重复"""
    if not isinstance(url, str):
        logging.warning(f"非字符串URL: {url}, 类型: {type(url)}")
        return None
    
    # 处理空URL
    if not url or pd.isna(url):
        return None
    
    # 提取域名后的路径部分
    path_match = re.search(r'https?://[^/]+(/.*)', url)
    if not path_match:
        logging.warning(f"无法从URL中提取路径: {url}")
        return None
    
    path = path_match.group(1)
    path_parts = path.strip('/').split('/')
    
    # 确保路径至少有2部分
    if len(path_parts) < 2:
        logging.warning(f"URL路径部分不足2级: {url}")
        return None
    
    # 1. 匹配形如 /xxx/yyy/123.html 或 /xxx/yyy/123.shtml 的模式
    match = re.search(r'/([^/]+)/([^/]+)/(\d+)\.(s?html)', url)
    if match:
        dir1, dir2, num_id = match.group(1), match.group(2), match.group(3)
        return f"{dir1}_{dir2}_{num_id}"
    
    # 2. 匹配形如 /xxx/yyy/20210413123456.shtml 的模式 (日期+序列号格式)
    match = re.search(r'/([^/]+)/([^/]+)/(\d{14,})\.(s?html)', url)
    if match:
        dir1, dir2, num_id = match.group(1), match.group(2), match.group(3)
        return f"{dir1}_{dir2}_{num_id}"
    
    # 3. 匹配形如 /xxx/yyy/id=123 的模式
    match = re.search(r'/([^/]+)/([^/]+)/[^?]*[?&]id=(\d+)', url)
    if match:
        dir1, dir2, num_id = match.group(1), match.group(2), match.group(3)
        return f"{dir1}_{dir2}_{num_id}"
    
    # 4. 尝试从URL末尾提取数字作为ID
    file_name = path_parts[-1]
    match = re.search(r'(\d+)\.(s?html)', file_name)
    if match:
        num_id = match.group(1)
        if len(path_parts) >= 3:
            dir1, dir2 = path_parts[-3], path_parts[-2]
            return f"{dir1}_{dir2}_{num_id}"
    
    # 5. 处理目录型URL，如 /cjks/cjkjsw/zy
    if len(path_parts) >= 3:
        dir1, dir2, dir3 = path_parts[0], path_parts[1], path_parts[2]
        # 如果最后一级是字母或短字符串，将其作为ID的一部分
        if len(dir3) < 10 and not re.match(r'^\d+$', dir3):
            return f"{dir1}_{dir2}_dir_{dir3}"
    
    logging.warning(f"无法从URL中提取ID: {url}")
    return None

def extract_file_info(file_path):
    """从文件名中提取日期和考种信息"""
    try:
        filename = os.path.basename(file_path)
        
        # 尝试提取日期信息
        date_match = re.search(r'(\d{1,4}[.-]\d{1,2}[.-]\d{1,2})', filename)
        if date_match:
            date_str = date_match.group(1)
            # 格式化日期为简短形式
            parts = re.split(r'[.-]', date_str)
            if len(parts) == 3:
                if len(parts[0]) == 4:  # 年份是4位数
                    date_formatted = f"{parts[0][-2:]}.{parts[1]}.{parts[2]}"
                else:  # 年份可能是2位数
                    date_formatted = f"{parts[0]}.{parts[1]}.{parts[2]}"
            else:
                date_formatted = date_str
        else:
            # 如果没有找到日期，使用当前日期
            date_formatted = datetime.now().strftime("%y.%m.%d")
        
        # 尝试提取考种信息
        exam_types = {
            'chuji': '初级',
            'cj': '初级',
            'zhongji': '中级',
            'zj': '中级',
            'gaoji': '高级',
            'gj': '高级',
            'acca': 'ACCA',
            'cpa': 'CPA',
            'cma': 'CMA',
            'cia': 'CIA'
        }
        
        category = '全部'  # 默认值
        for key, value in exam_types.items():
            if key in filename.lower():
                category = value
                break
        
        return {
            'date': date_formatted,
            'category': category
        }
    except Exception as e:
        logging.warning(f"提取文件信息时出错: {str(e)}")
        return {
            'date': datetime.now().strftime("%y.%m.%d"),
            'category': '全部'
        }

def analyze_id_differences(df_current, df_previous, common_ids):
    """分析ID差异情况"""
    try:
        # 计算各类ID集合
        current_ids = set(df_current['ID'])
        previous_ids = set(df_previous['ID'])
        only_current_ids = current_ids - previous_ids
        only_previous_ids = previous_ids - current_ids
        
        # 创建数据映射以提高查找效率
        current_data = df_current.set_index('ID').to_dict('index')
        previous_data = df_previous.set_index('ID').to_dict('index')
        
        # 一次性处理所有共同ID的变化
        common_id_changes = []
        total_current_uv = 0
        total_previous_uv = 0
        
        for id_val in common_ids:
            current_info = current_data.get(id_val, {})
            previous_info = previous_data.get(id_val, {})
            
            current_uv = current_info.get('UV', 0)
            previous_uv = previous_info.get('UV', 0)
            current_url = current_info.get('URL', '')
            
            total_current_uv += current_uv
            total_previous_uv += previous_uv
            
            uv_change = current_uv - previous_uv
            uv_change_percent = (uv_change / previous_uv * 100) if previous_uv > 0 else 0
            
            common_id_changes.append({
                'id': id_val,
                'url': current_url,
                'current_uv': int(current_uv),
                'previous_uv': int(previous_uv),
                'uv_change': int(uv_change),
                'uv_change_percent': round(uv_change_percent, 2)
            })
        
        # 使用sorted函数一次性排序
        common_id_changes = sorted(common_id_changes, key=lambda x: x['uv_change'])
        
        # 直接切片获取top declining和growing
        top_declining_common_ids = [item for item in common_id_changes if item['uv_change'] < 0][:10]
        top_growing_common_ids = sorted([item for item in common_id_changes if item['uv_change'] > 0],
                                      key=lambda x: x['uv_change'],
                                      reverse=True)[:10]
        
        # 处理仅当前年度存在的ID
        only_current_data = []
        only_current_total_uv = 0
        total_current_all_uv = df_current['UV'].sum()
        
        # 批量处理仅当前年度ID
        only_current_df = df_current[df_current['ID'].isin(only_current_ids)]
        only_current_total_uv = only_current_df['UV'].sum()
        
        # 只获取前10个用于展示
        for _, row in only_current_df.nlargest(10, 'UV').iterrows():
            contribution_percent = (row['UV'] / total_current_all_uv * 100) if total_current_all_uv > 0 else 0
            only_current_data.append({
                'id': row['ID'],
                'url': row['URL'],
                'current_uv': int(row['UV']),
                'contribution_percent': round(contribution_percent, 2)
            })
        
        # 处理仅上一年度存在的ID
        only_previous_data = []
        only_previous_total_uv = 0
        total_previous_all_uv = df_previous['UV'].sum()
        
        # 批量处理仅上一年度ID
        only_previous_df = df_previous[df_previous['ID'].isin(only_previous_ids)]
        only_previous_total_uv = only_previous_df['UV'].sum()
        
        # 只获取前10个用于展示
        for _, row in only_previous_df.nlargest(10, 'UV').iterrows():
            loss_percent = (row['UV'] / total_previous_all_uv * 100) if total_previous_all_uv > 0 else 0
            only_previous_data.append({
                'id': row['ID'],
                'url': row['URL'],
                'previous_uv': int(row['UV']),
                'loss_percent': round(loss_percent, 2)
            })
        
        # 计算总UV变化
        total_uv_change = (total_current_uv - total_previous_uv) + only_current_total_uv - only_previous_total_uv
        
        # 计算各部分占总变化的比例
        if total_uv_change != 0:
            common_uv_change = total_current_uv - total_previous_uv
            common_uv_change_percent_of_total = (common_uv_change / abs(total_uv_change) * 100)
            lost_uv_percent = (-only_previous_total_uv / abs(total_uv_change) * 100)
            new_uv_percent = (only_current_total_uv / abs(total_uv_change) * 100)
        else:
            common_uv_change_percent_of_total = 0
            lost_uv_percent = 0
            new_uv_percent = 0
        
        # 计算平均UV统计（用于内容质量评估）
        avg_current_only_uv = (only_current_total_uv / len(only_current_ids)) if only_current_ids else 0
        avg_previous_only_uv = (only_previous_total_uv / len(only_previous_ids)) if only_previous_ids else 0
        avg_common_current_uv = (total_current_uv / len(common_ids)) if common_ids else 0
        avg_common_previous_uv = (total_previous_uv / len(common_ids)) if common_ids else 0
        
        # 计算内容质量稳定性指标
        quality_stability_diff = abs(avg_current_only_uv - avg_previous_only_uv)
        quality_stability_percent = (quality_stability_diff / avg_previous_only_uv * 100) if avg_previous_only_uv > 0 else 0
        
        return {
            'top_declining_common_ids': top_declining_common_ids,
            'top_growing_common_ids': top_growing_common_ids,
            'only_current_ids': only_current_data,
            'only_previous_ids': only_previous_data,
            'only_current_uv': int(only_current_total_uv),
            'only_previous_uv': int(only_previous_total_uv),
            'common_current_uv': int(total_current_uv),
            'common_previous_uv': int(total_previous_uv),
            'common_uv_change': int(total_current_uv - total_previous_uv),
            'common_uv_change_percent': round(common_uv_change_percent_of_total, 2),
            'lost_uv_percent': round(lost_uv_percent, 2),
            'new_uv_percent': round(new_uv_percent, 2),
            # 新增的平均UV统计
            'avg_current_only_uv': round(avg_current_only_uv, 2),
            'avg_previous_only_uv': round(avg_previous_only_uv, 2),
            'avg_common_current_uv': round(avg_common_current_uv, 2),
            'avg_common_previous_uv': round(avg_common_previous_uv, 2),
            'quality_stability_diff': round(quality_stability_diff, 2),
            'quality_stability_percent': round(quality_stability_percent, 2),
            'summary': {
                'total_common_ids': len(common_ids),
                'total_only_current': len(only_current_ids),
                'total_only_previous': len(only_previous_ids),
                'declining_common_ids': len([x for x in common_id_changes if x['uv_change'] < 0]),
                'growing_common_ids': len([x for x in common_id_changes if x['uv_change'] > 0])
            }
        }
        
    except Exception as e:
        logging.error(f"ID差异分析失败: {str(e)}")
        return None

def generate_excel_report(result, filepath):
    """生成详细的Excel分析报告"""
    try:
        export_data = {}
        
        # 1. 基本信息汇总
        basic_info = []
        basic_info.append(['指标', '当前年度', '上一年度', '变化', '变化率'])
        basic_info.append(['总URL数', result['basic_analysis']['total_urls'], 
                          result['comparative_analysis']['previous_total_urls'] if result.get('comparative_analysis') else '-',
                          result['basic_analysis']['total_urls'] - (result['comparative_analysis']['previous_total_urls'] if result.get('comparative_analysis') else 0),
                          '-'])
        basic_info.append(['唯一ID数', result['basic_analysis']['unique_ids'],
                          result['comparative_analysis']['previous_unique_ids'] if result.get('comparative_analysis') else '-',
                          result['basic_analysis']['unique_ids'] - (result['comparative_analysis']['previous_unique_ids'] if result.get('comparative_analysis') else 0),
                          '-'])
        basic_info.append(['总UV', result['basic_analysis']['total_uv'],
                          result['comparative_analysis']['previous_total_uv'] if result.get('comparative_analysis') else '-',
                          result['comparative_analysis']['total_uv_change'] if result.get('comparative_analysis') else '-',
                          f"{result['comparative_analysis']['total_uv_change_percent']:.2f}%" if result.get('comparative_analysis') else '-'])
        basic_info.append(['总PV', result['basic_analysis']['total_pv'],
                          result['comparative_analysis']['previous_total_pv'] if result.get('comparative_analysis') else '-',
                          result['basic_analysis']['total_pv'] - (result['comparative_analysis']['previous_total_pv'] if result.get('comparative_analysis') else 0),
                          '-'])
        
        export_data['基本信息汇总'] = pd.DataFrame(basic_info[1:], columns=basic_info[0])
        
        # 2. 下降词分析 - 使用完整数据
        if result.get('comparative_analysis'):
            # 获取完整的目标下降词数据（不限制条数）
            target_decline_data = []
            for item in result['comparative_analysis'].get('target_decline_details', []):
                target_decline_data.append({
                    'ID': item['id'],
                    'URL': item['url'],
                    '标题': item['title'],
                    '上年UV': item['previous_uv'],
                    '今年UV': item['current_uv'],
                    '下降量': item['decline_amount'],
                    '下降率': f"{item['decline_rate']:.2f}%"
                })
            
            if target_decline_data:
                export_data['目标下降词详情'] = pd.DataFrame(target_decline_data)
        
            # 导出完整的总下降词详情
            if result['comparative_analysis'].get('all_decline_details'):
                all_decline_data = []
                for item in result['comparative_analysis']['all_decline_details']:
                    all_decline_data.append({
                        'ID': item['id'],
                        'URL': item['url'],
                        '标题': item['title'],
                        '上年UV': item['previous_uv'],
                        '今年UV': item['current_uv'],
                        '下降量': item['decline_amount'],
                        '下降率': f"{item['decline_rate']:.2f}%",
                        '类型': '共同ID' if item['current_uv'] > 0 else '去年独立ID'
                    })
                
                if all_decline_data:
                    export_data['总下降词详情'] = pd.DataFrame(all_decline_data)
        
        # 3. ID差异分析
        if result.get('id_diff_analysis'):
            # 流量下降最严重的ID - 使用完整数据
            if result['id_diff_analysis'].get('top_declining_common_ids'):
                declining_ids = pd.DataFrame(result['id_diff_analysis']['top_declining_common_ids'])
                if not declining_ids.empty:
                    export_data['流量下降最严重的ID'] = declining_ids
            
            # 流量增长最多的ID - 使用完整数据
            if result['id_diff_analysis'].get('top_growing_common_ids'):
                growing_ids = pd.DataFrame(result['id_diff_analysis']['top_growing_common_ids'])
                if not growing_ids.empty:
                    export_data['流量增长最多的ID'] = growing_ids
            
            # 仅当前年度存在的ID - 使用完整数据
            if result['id_diff_analysis'].get('only_current_ids'):
                only_current_ids = pd.DataFrame(result['id_diff_analysis']['only_current_ids'])
                if not only_current_ids.empty:
                    export_data['仅当前年度存在的ID'] = only_current_ids
            
            # 仅上一年度存在的ID - 使用完整数据
            if result['id_diff_analysis'].get('only_previous_ids'):
                only_previous_ids = pd.DataFrame(result['id_diff_analysis']['only_previous_ids'])
                if not only_previous_ids.empty:
                    export_data['仅上一年度存在的ID'] = only_previous_ids
        
        # 创建Excel文件
        with pd.ExcelWriter(filepath) as writer:
            for sheet_name, df in export_data.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        return True
    except Exception as e:
        logging.error(f"生成Excel报告失败: {str(e)}")
        return False

def process_data(current_file, previous_file=None, session_id=None):
    """处理Excel数据并返回分析结果"""
    try:
        update_progress("开始分析", 0, 10, "正在初始化数据分析...", session_id)
        
        logging.info(f"开始处理数据文件: {current_file}")
        
        # 提取文件信息
        file_info = extract_file_info(current_file)
        
        update_progress("读取当前年度数据", 1, 10, f"正在读取文件: {os.path.basename(current_file)}", session_id)
        
        # 读取当前年度数据
        try:
            df_current = pd.read_excel(current_file)
            logging.info(f"成功读取当前年度数据，列名: {list(df_current.columns)}")
        except Exception as e:
            logging.error(f"读取当前年度Excel文件失败: {str(e)}")
            raise ValueError(f"无法读取当前年度Excel文件: {str(e)}")
        
        update_progress("处理列名映射", 2, 10, "正在检查和映射数据列名...", session_id)
        
        # 检查列名并进行映射
        column_mapping = {
            'URL': ['URL', 'Url', 'url', '网址', '链接', 'url地址', 'URL地址'],
            'UV': ['UV', 'Uv', 'uv', '访客数', '独立访客', '访问次数', '用户数'],
            'PV': ['PV', 'Pv', 'pv', '浏览量', '页面浏览', '访问量', '点击量']
        }
        
        # 检查并映射列名
        current_columns = {}
        for target_col, possible_names in column_mapping.items():
            found = False
            for name in possible_names:
                if name in df_current.columns:
                    current_columns[target_col] = name
                    found = True
                    logging.info(f"当前年度数据中找到列 '{name}' 映射到 '{target_col}'")
                    break
            if not found:
                error_msg = f"在当前年度数据中找不到{target_col}列。请确保Excel文件包含以下列名之一: {', '.join(possible_names)}"
                logging.error(error_msg)
                raise ValueError(error_msg)
        
        # 重命名列以便后续处理
        df_current = df_current.rename(columns={current_columns[col]: col for col in current_columns})
        logging.info(f"重命名当前年度数据列完成，现在的列名: {list(df_current.columns)}")
        
        update_progress("提取ID", 3, 10, f"正在从{len(df_current)}个URL中提取ID...", session_id)
        
        # 添加ID列
        df_current['ID'] = df_current['URL'].apply(extract_id_from_url)
        # 检查ID提取情况
        null_ids = df_current['ID'].isnull().sum()
        if null_ids > 0:
            logging.warning(f"当前年度数据中有 {null_ids} 个URL无法提取ID")
        
        update_progress("合并数据", 4, 10, "正在按ID合并相同内容...", session_id)
        
        # 按ID合并数据（合并www和m的相同内容）
        df_current_grouped = df_current.groupby('ID').agg({
            'UV': 'sum',
            'PV': 'sum',
            'URL': 'first'  # 保留一个URL用于展示
        }).reset_index()
        
        # 基本分析
        total_uv = df_current_grouped['UV'].sum()
        total_pv = df_current_grouped['PV'].sum()
        total_urls = len(df_current)
        unique_ids = len(df_current_grouped)
        
        # 统计域名分布
        www_count = len(df_current[df_current['URL'].str.contains('www\.', regex=True)])
        m_count = len(df_current[df_current['URL'].str.contains('//m\.', regex=True)])
        other_count = total_urls - www_count - m_count
        
        basic_analysis = {
            'total_uv': int(total_uv),
            'total_pv': int(total_pv),
            'total_urls': total_urls,
            'unique_ids': unique_ids,
            'avg_uv_per_url': round(total_uv / total_urls, 2),
            'avg_pv_per_url': round(total_pv / total_urls, 2),
            'avg_uv_per_id': round(total_uv / unique_ids, 2),
            'avg_pv_per_id': round(total_pv / unique_ids, 2),
            'www_count': www_count,
            'm_count': m_count,
            'other_count': other_count
        }
        
        logging.info(f"当前年度基本分析完成: 总UV={total_uv}, 总URL数={total_urls}, 唯一ID数={unique_ids}")
        
        # 初始化对比分析变量
        comparative_analysis = None
        
        # 对比分析 - 计算共同ID的流量变化
        if previous_file:
            update_progress("读取上一年度数据", 5, 10, f"正在读取文件: {os.path.basename(previous_file)}", session_id)
            
            logging.info(f"开始处理上一年度数据文件: {previous_file}")
            
            # 读取上一年度数据
            try:
                df_previous = pd.read_excel(previous_file)
                logging.info(f"成功读取上一年度数据，列名: {list(df_previous.columns)}")
            except Exception as e:
                logging.error(f"读取上一年度Excel文件失败: {str(e)}")
                raise ValueError(f"无法读取上一年度Excel文件: {str(e)}")
            
            # 检查并映射上一年度数据列名
            previous_columns = {}
            for target_col, possible_names in column_mapping.items():
                found = False
                for name in possible_names:
                    if name in df_previous.columns:
                        previous_columns[target_col] = name
                        found = True
                        logging.info(f"上一年度数据中找到列 '{name}' 映射到 '{target_col}'")
                        break
                if not found:
                    error_msg = f"在上一年度数据中找不到{target_col}列。请确保Excel文件包含以下列名之一: {', '.join(possible_names)}"
                    logging.error(error_msg)
                    raise ValueError(error_msg)
            
            # 重命名上一年度数据列
            df_previous = df_previous.rename(columns={previous_columns[col]: col for col in previous_columns})
            logging.info(f"重命名上一年度数据列完成，现在的列名: {list(df_previous.columns)}")
            
            update_progress("处理上一年度ID", 6, 10, f"正在从{len(df_previous)}个URL中提取ID...", session_id)
            
            # 添加ID列
            df_previous['ID'] = df_previous['URL'].apply(extract_id_from_url)
            # 检查ID提取情况
            null_ids_previous = df_previous['ID'].isnull().sum()
            if null_ids_previous > 0:
                logging.warning(f"上一年度数据中有 {null_ids_previous} 个URL无法提取ID")
            
            # 按ID合并上一年度数据
            df_previous_grouped = df_previous.groupby('ID').agg({
                'UV': 'sum',
                'PV': 'sum',
                'URL': 'first'
            }).reset_index()
                
            update_progress("分析下降词", 7, 10, "正在分析目标下降词...", session_id)
            
            # 找到共同的ID
            common_ids = set(df_current_grouped['ID']) & set(df_previous_grouped['ID'])
                
            # 优化：创建ID到数据的映射，避免重复查询
            current_id_map = df_current_grouped.set_index('ID').to_dict('index')
            previous_id_map = df_previous_grouped.set_index('ID').to_dict('index')
            
            # 计算共同ID的下降词数据
            common_decline_ids = []
            common_decline_traffic = 0
            common_target_decline_ids = []
            common_target_decline_traffic = 0
            target_decline_details = []  # 保存目标下降词的详细信息
            
            # 用于调试的统计信息
            debug_stats = {
                'total_decline': 0,
                'uv_too_small': 0,  # UV ≤ 10
                'decline_rate_too_small': 0,  # 降幅 ≤ 50%
                'both_conditions_not_met': 0,  # 两个条件都不满足
                'target_decline': 0  # 目标下降词
            }
            
            total_common_ids = len(common_ids)
            processed_ids = 0
            
            # 新增：保存所有共同ID下降词的详细信息
            common_decline_details = []
            
            # 批量处理所有共同ID，避免重复计算
            for id_val in common_ids:
                # 使用映射快速获取数据
                current_data = current_id_map.get(id_val, {})
                previous_data = previous_id_map.get(id_val, {})
                
                current_uv = current_data.get('UV', 0)
                previous_uv = previous_data.get('UV', 0)
                
                if current_uv < previous_uv:
                    decline_amount = previous_uv - current_uv
                    decline_rate = (decline_amount / previous_uv * 100) if previous_uv > 0 else 0
                    common_decline_ids.append(id_val)
                    common_decline_traffic += decline_amount
                    
                    debug_stats['total_decline'] += 1
                    
                    # 获取URL信息
                    url = current_data.get('URL', '')
                    
                    # 保存所有共同ID下降词的详细信息
                    common_decline_details.append({
                        'id': id_val,
                        'url': url,
                        'title': f'ID_{id_val}',
                        'previous_uv': int(previous_uv),
                        'current_uv': int(current_uv),
                        'decline_amount': int(decline_amount),
                        'decline_rate': round(decline_rate, 2)
                    })
                    
                    # 判断是否为目标下降词（UV大于10且降幅大于50%）
                    if previous_uv > 10 and decline_rate > 50:
                        common_target_decline_ids.append(id_val)
                        common_target_decline_traffic += decline_amount
                        debug_stats['target_decline'] += 1
                        
                    target_decline_details.append({
                            'id': id_val,
                            'url': url,
                            'title': f'ID_{id_val}',  # 使用ID作为临时标题，避免网络请求
                            'previous_uv': int(previous_uv),
                            'current_uv': int(current_uv),
                            'decline_amount': int(decline_amount),
                            'decline_rate': round(decline_rate, 2)
                        })
                else:
                    # 统计不符合条件的原因
                    if previous_uv <= 10 and decline_rate <= 50:
                        debug_stats['both_conditions_not_met'] += 1
                    elif previous_uv <= 10:
                        debug_stats['uv_too_small'] += 1
                    elif decline_rate <= 50:
                        debug_stats['decline_rate_too_small'] += 1
                
                processed_ids += 1
                # 每处理100个ID更新一次进度
                if processed_ids % 100 == 0:
                    update_progress("分析下降词", 7, 10, f"已处理 {processed_ids}/{total_common_ids} 个共同ID", session_id)
            
            logging.info(f"目标下降词统计 - 总下降词:{debug_stats['total_decline']}, 目标下降词:{debug_stats['target_decline']}, UV≤10:{debug_stats['uv_too_small']}, 降幅≤50%:{debug_stats['decline_rate_too_small']}, 两个条件都不满足:{debug_stats['both_conditions_not_met']}")
            
            # 按下降流量排序
            common_decline_details.sort(key=lambda x: x['decline_amount'], reverse=True)
            target_decline_details.sort(key=lambda x: x['decline_amount'], reverse=True)
            
            # 保存完整数据用于导出
            target_decline_details_full = target_decline_details.copy()
            # 只保留前20个目标下降词用于页面显示
            target_decline_details = target_decline_details[:20]
            
            # 计算所有ID的下降词数据（包括共同ID下降 + 去年独立ID）
            total_decline_ids = common_decline_ids.copy()  # 复用已计算的数据
            total_decline_traffic = common_decline_traffic
            
            # 按考种分类统计下降词
            decline_by_exam_type = {
                'all': {
                    'common': {
                        'count': 0,  # 共同ID下降词数量
                        'traffic': 0,  # 共同ID下降词流量
                        'target_count': 0,  # 目标下降词数量
                        'target_traffic': 0,  # 目标下降词流量
                    },
                    'total': {
                        'count': 0,  # 总下降词数量
                        'traffic': 0,  # 总下降词流量
                    }
                }
            }
            
            # 初始化各考种的统计数据
            for exam_type in ['cjks', 'zjks', 'zckjs', 'gaoji', 'zjjs', 'shuiwushi', 'scjy', 'acca', 'cma']:
                decline_by_exam_type[exam_type] = {
                    'common': {
                        'count': 0,
                        'traffic': 0,
                        'target_count': 0,
                        'target_traffic': 0,
                    },
                    'total': {
                        'count': 0,
                        'traffic': 0,
                    }
                }
            
            # 分类统计共同ID下降词
            for id_val in common_decline_ids:
                current_data = current_id_map.get(id_val, {})
                previous_data = previous_id_map.get(id_val, {})
                url = current_data.get('URL', '').lower()
                decline_amount = previous_data.get('UV', 0) - current_data.get('UV', 0)
                previous_uv = previous_data.get('UV', 0)
                current_uv = current_data.get('UV', 0)
                decline_rate = ((previous_uv - current_uv) / previous_uv * 100) if previous_uv > 0 else 0
                
                # 更新全部统计
                decline_by_exam_type['all']['common']['count'] += 1
                decline_by_exam_type['all']['common']['traffic'] += decline_amount
                decline_by_exam_type['all']['total']['count'] += 1
                decline_by_exam_type['all']['total']['traffic'] += decline_amount
                
                # 如果是目标下降词(UV>10且降幅>50%)
                if previous_uv > 10 and decline_rate > 50:
                    decline_by_exam_type['all']['common']['target_count'] += 1
                    decline_by_exam_type['all']['common']['target_traffic'] += decline_amount
                
                # 按考种分类
                exam_type_matched = False
                if 'cjks' in url or 'cjkjsw' in url:
                    exam_type = 'cjks'
                    exam_type_matched = True
                elif 'zjks' in url or 'zjkjsw' in url:
                    exam_type = 'zjks'
                    exam_type_matched = True
                elif 'zckjs' in url or 'cpa' in url:
                    exam_type = 'zckjs'
                    exam_type_matched = True
                elif 'gaoji' in url:
                    exam_type = 'gaoji'
                    exam_type_matched = True
                elif 'zjjs' in url:
                    exam_type = 'zjjs'
                    exam_type_matched = True
                elif 'shuiwushi' in url:
                    exam_type = 'shuiwushi'
                    exam_type_matched = True
                elif 'scjy' in url:
                    exam_type = 'scjy'
                    exam_type_matched = True
                elif 'acca' in url:
                    exam_type = 'acca'
                    exam_type_matched = True
                elif 'cma' in url:
                    exam_type = 'cma'
                    exam_type_matched = True
                
                if exam_type_matched:
                    decline_by_exam_type[exam_type]['common']['count'] += 1
                    decline_by_exam_type[exam_type]['common']['traffic'] += decline_amount
                    decline_by_exam_type[exam_type]['total']['count'] += 1
                    decline_by_exam_type[exam_type]['total']['traffic'] += decline_amount
                    
                    if previous_uv > 10 and decline_rate > 50:
                        decline_by_exam_type[exam_type]['common']['target_count'] += 1
                        decline_by_exam_type[exam_type]['common']['target_traffic'] += decline_amount
            
            # 2. 去年独立ID（今年消失的ID，相当于流量下降到0）
            only_previous_ids = set(df_previous_grouped['ID']) - set(df_current_grouped['ID'])
            total_decline_from_previous = []  # 保存去年独立ID的详细数据
            
            for id_val in only_previous_ids:
                previous_data = previous_id_map.get(id_val, {})
                previous_uv = previous_data.get('UV', 0)
                url = previous_data.get('URL', '').lower()
                
                total_decline_ids.append(id_val)
                total_decline_traffic += previous_uv  # 全部流量都算作下降
                
                # 更新考种统计
                decline_by_exam_type['all']['total']['count'] += 1
                decline_by_exam_type['all']['total']['traffic'] += previous_uv
                
                if 'cjks' in url or 'cjkjsw' in url:
                    decline_by_exam_type['cjks']['total']['count'] += 1
                    decline_by_exam_type['cjks']['total']['traffic'] += previous_uv
                elif 'zjks' in url or 'zjkjsw' in url:
                    decline_by_exam_type['zjks']['total']['count'] += 1
                    decline_by_exam_type['zjks']['total']['traffic'] += previous_uv
                elif 'zckjs' in url or 'cpa' in url:
                    decline_by_exam_type['zckjs']['total']['count'] += 1
                    decline_by_exam_type['zckjs']['total']['traffic'] += previous_uv
                elif 'gaoji' in url:
                    decline_by_exam_type['gaoji']['total']['count'] += 1
                    decline_by_exam_type['gaoji']['total']['traffic'] += previous_uv
                elif 'zjjs' in url:
                    decline_by_exam_type['zjjs']['total']['count'] += 1
                    decline_by_exam_type['zjjs']['total']['traffic'] += previous_uv
                elif 'shuiwushi' in url:
                    decline_by_exam_type['shuiwushi']['total']['count'] += 1
                    decline_by_exam_type['shuiwushi']['total']['traffic'] += previous_uv
                elif 'scjy' in url:
                    decline_by_exam_type['scjy']['total']['count'] += 1
                    decline_by_exam_type['scjy']['total']['traffic'] += previous_uv
                elif 'acca' in url:
                    decline_by_exam_type['acca']['total']['count'] += 1
                    decline_by_exam_type['acca']['total']['traffic'] += previous_uv
                elif 'cma' in url:
                    decline_by_exam_type['cma']['total']['count'] += 1
                    decline_by_exam_type['cma']['total']['traffic'] += previous_uv
                
                # 保存去年独立ID的详细信息
                total_decline_from_previous.append({
                    'id': id_val,
                    'url': previous_data.get('URL', ''),
                    'title': f'ID_{id_val}',
                    'previous_uv': int(previous_uv),
                    'current_uv': 0,  # 今年不存在，UV为0
                    'decline_amount': int(previous_uv),
                    'decline_rate': 100.0  # 完全消失，降幅100%
                })
            
            # 按下降流量排序去年独立ID
            total_decline_from_previous.sort(key=lambda x: x['decline_amount'], reverse=True)
            
            # 创建完整的总下降词列表（所有共同ID下降词 + 去年独立ID）
            all_decline_details = common_decline_details.copy()  # 使用所有共同ID下降词数据
            all_decline_details.extend(total_decline_from_previous)  # 添加去年独立ID
            all_decline_details.sort(key=lambda x: x['decline_amount'], reverse=True)
            
            # 按考种分类目标下降词
            exam_type_stats = {
                'all': {'count': len(target_decline_details_full), 'details': target_decline_details[:20]},  # 页面显示仍限制20条
                'cjks': {'count': 0, 'details': []},
                'zjks': {'count': 0, 'details': []},
                'zckjs': {'count': 0, 'details': []},
                'gaoji': {'count': 0, 'details': []},
                'zjjs': {'count': 0, 'details': []},
                'shuiwushi': {'count': 0, 'details': []},
                'scjy': {'count': 0, 'details': []},
                'acca': {'count': 0, 'details': []},
                'cma': {'count': 0, 'details': []}
            }
            
            # 分类统计
            for item in target_decline_details_full:  # 使用完整数据进行分类
                url = item['url'].lower()
                if 'cjks' in url or 'cjkjsw' in url:
                    exam_type_stats['cjks']['details'].append(item)
                elif 'zjks' in url or 'zjkjsw' in url:
                    exam_type_stats['zjks']['details'].append(item)
                elif 'zckjs' in url or 'cpa' in url:
                    exam_type_stats['zckjs']['details'].append(item)
                elif 'gaoji' in url:
                    exam_type_stats['gaoji']['details'].append(item)
                elif 'zjjs' in url:
                    exam_type_stats['zjjs']['details'].append(item)
                elif 'shuiwushi' in url:
                    exam_type_stats['shuiwushi']['details'].append(item)
                elif 'scjy' in url:
                    exam_type_stats['scjy']['details'].append(item)
                elif 'acca' in url:
                    exam_type_stats['acca']['details'].append(item)
                elif 'cma' in url:
                    exam_type_stats['cma']['details'].append(item)
            
            # 更新各考种的统计数据并限制显示前20条
            for exam_type in exam_type_stats:
                if exam_type != 'all':
                    exam_type_stats[exam_type]['count'] = len(exam_type_stats[exam_type]['details'])
                    exam_type_stats[exam_type]['details'] = sorted(
                        exam_type_stats[exam_type]['details'],
                        key=lambda x: x['decline_amount'],
                        reverse=True
                    )[:20]  # 页面显示仍限制20条
            
            comparative_analysis = {
                'common_ids': len(common_ids),
                'previous_total_urls': len(df_previous),
                'previous_unique_ids': len(df_previous_grouped),
                'previous_total_uv': int(df_previous_grouped['UV'].sum()),
                'previous_total_pv': int(df_previous_grouped['PV'].sum()),
                'previous_www_count': len(df_previous[df_previous['URL'].str.contains('www', case=False, na=False)]),
                'previous_m_count': len(df_previous[df_previous['URL'].str.contains('://m\\.', case=False, na=False)]),
                'previous_other_count': len(df_previous[~df_previous['URL'].str.contains('www|://m\\.', case=False, na=False)]),
                'total_uv_change': int(basic_analysis['total_uv'] - df_previous_grouped['UV'].sum()),
                'total_uv_change_percent': float(((basic_analysis['total_uv'] - df_previous_grouped['UV'].sum()) / df_previous_grouped['UV'].sum() * 100)) if df_previous_grouped['UV'].sum() > 0 else 0.0,
                
                # 共同ID的下降词数据
                'common_decline_ids_count': len(common_decline_ids),
                'common_decline_traffic': int(common_decline_traffic),
                'common_target_decline_ids_count': len(common_target_decline_ids),
                'common_target_decline_traffic': int(common_target_decline_traffic),
                'common_target_traffic_ratio': float(common_target_decline_traffic / common_decline_traffic * 100) if common_decline_traffic > 0 else 0.0,
                
                # 总下降词数据
                'total_decline_ids_count': len(total_decline_ids),
                'total_decline_traffic': int(total_decline_traffic),
                
                # 考种分类统计
                'decline_by_exam_type': decline_by_exam_type,
                
                # 文件信息
                'category': file_info['category'],
                'date_range_current': file_info['date'],
                'duplicate_keywords': '',  # 重复优化词暂时为空
                
                # 详细数据 - 分别保存共同ID和总下降词
                'target_decline_details': target_decline_details,  # 页面显示用的前20条
                'target_decline_details_full': target_decline_details_full,  # 完整数据用于导出
                'total_decline_from_previous': total_decline_from_previous,  # 去年独立ID
                'all_decline_details': all_decline_details,  # 完整的总下降词列表
                
                # 提取文件信息
                'exam_type': file_info.get('category', ''),
                'query_time': file_info.get('date', ''),
                'exam_type_stats': exam_type_stats,
            }
            
            update_progress("ID差异分析", 8, 10, "正在进行ID差异分析...", session_id)
            
            # 添加ID差异分析
            id_diff_analysis = analyze_id_differences(df_current_grouped, df_previous_grouped, common_ids)
        
        # 初始化id_diff_analysis变量
        if 'id_diff_analysis' not in locals():
            id_diff_analysis = None
        
        result = {
            'basic_analysis': basic_analysis,
            'top_urls': df_current_grouped.sort_values('UV', ascending=False).head(20).to_dict('records'),
            'comparative_analysis': comparative_analysis,
            'id_diff_analysis': id_diff_analysis
        }
        
        # 自动生成Excel报告
        if previous_file:
            update_progress("生成Excel报告", 9, 10, "正在生成详细的Excel分析报告...", session_id)
            
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_filename = f"分析报告_{timestamp}.xlsx"
                report_path = os.path.join(app.config['EXPORT_FOLDER'], report_filename)
                
                # 确保导出目录存在
                os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)
                
                # 生成Excel报告
                generate_excel_report(result, report_path)
                logging.info(f"Excel报告已生成: {report_path}")
                
                # 将报告文件名添加到结果中
                result['excel_report'] = report_filename
                
            except Exception as e:
                logging.error(f"生成Excel报告失败: {str(e)}")
        update_progress("分析完成", 10, 10, f"数据分析完成！共分析了{unique_ids}个唯一ID", session_id)
        
        return result
    
    except Exception as e:
        logging.error(f"数据处理失败: {str(e)}")
        raise e

def get_progress(session_id):
    """获取分析进度"""
    global progress_data
    
    # 检查分析是否已完成且有结果
    if session_id in analysis_status and analysis_status[session_id]:
        # 检查是否有分析结果
        if session_id in analysis_results and analysis_results[session_id].get('result'):
            # 分析已完成且有结果，返回完成状态
            return jsonify({
                'step': '分析完成',
                'progress': 100,
                'total_steps': 100,
                'percentage': 100,
                'details': '分析已完成，正在跳转到结果页面...'
            })
        elif session_id in analysis_results and analysis_results[session_id].get('error'):
            # 分析完成但有错误
            return jsonify({
                'step': '分析失败',
                'progress': 100,
                'total_steps': 100,
                'percentage': 100,
                'details': analysis_results[session_id]['error']
            })
    
    # 检查当前进度数据
    if progress_data.get('session_id') == session_id:
        return jsonify({
            'step': progress_data['current_step'],
            'progress': progress_data['progress'],
            'total_steps': progress_data['total_steps'],
            'percentage': round((progress_data['progress'] / progress_data['total_steps'] * 100), 1) if progress_data['total_steps'] > 0 else 0,
            'details': progress_data['details']
        })
    else:
        # 如果session存在但没有进度数据，可能是刚开始分析
        if session_id in analysis_results:
            return jsonify({
                'step': '准备分析',
                'progress': 0,
                'total_steps': 100,
                'percentage': 0,
                'details': '正在初始化分析任务...'
            })
        else:
            return jsonify({'error': 'Session not found'}), 404

@app.route('/api/check_analysis/<session_id>')
def check_analysis(session_id):
    """检查分析是否完成的API"""
    try:
        # 检查分析是否完成
        is_complete = is_analysis_complete(session_id)
        return jsonify({'is_complete': is_complete})
    except Exception as e:
        logging.error(f"检查分析状态失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    """首页"""
    # 获取最新的分析报告列表
    reports = []
    try:
        if os.path.exists(app.config['EXPORT_FOLDER']):
            files = os.listdir(app.config['EXPORT_FOLDER'])
            excel_files = [f for f in files if f.endswith('.xlsx') and '分析报告' in f]
            excel_files.sort(key=lambda x: os.path.getmtime(os.path.join(app.config['EXPORT_FOLDER'], x)), reverse=True)
            
            for filename in excel_files[:10]:  # 最多显示10个最新报告
                file_path = os.path.join(app.config['EXPORT_FOLDER'], filename)
                file_size = os.path.getsize(file_path)
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                reports.append({
                    'filename': filename,
                    'file_size': f"{file_size / 1024:.1f} KB",
                    'formatted_time': file_time.strftime('%Y-%m-%d %H:%M:%S')
                })
    except Exception as e:
        logging.error(f"获取报告列表失败: {str(e)}")
    
    # 获取session报告列表
    session_reports = []
    try:
        sessions = session_manager.list_sessions()
        for session in sessions[:10]:  # 最多显示10个最新session报告
            session_info = session_manager.get_session_info(session['session_id'])
            if session_info and session_info.get('has_result'):
                session_reports.append({
                    'session_id': session['session_id'],
                    'current_filename': session_info.get('current_filename', '未知'),
                    'previous_filename': session_info.get('previous_filename'),
                    'formatted_time': session['formatted_time'],
                    'file_size': session.get('file_size', '未知')
                })
    except Exception as e:
        logging.error(f"获取session报告列表失败: {str(e)}")
    
    return render_template('index.html', history_reports=reports, session_reports=session_reports)

@app.route('/analyze', methods=['POST'])
def analyze():
    """处理数据分析请求"""
    try:
        # 检查是否上传了当前年度文件
        if 'current_file' not in request.files:
            flash('请上传当前年度数据文件', 'error')
            return redirect(url_for('index'))
        
        current_file = request.files['current_file']
        if current_file.filename == '':
            flash('请选择当前年度数据文件', 'error')
            return redirect(url_for('index'))
        
        if not allowed_file(current_file.filename):
            flash('不支持的文件格式，请上传Excel文件(.xlsx, .xls)', 'error')
            return redirect(url_for('index'))
        
        # 生成session ID
        session_id = str(int(time.time() * 1000))
        session['current_session_id'] = session_id
        
        # 保存当前年度文件
        current_filename = secure_filename(current_file.filename)
        current_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{session_id}_{current_filename}")
        current_file.save(current_file_path)
        
        # 处理上一年度文件（可选）
        previous_file_path = None
        previous_filename = None
        if 'previous_file' in request.files:
            previous_file = request.files['previous_file']
            if previous_file.filename != '' and allowed_file(previous_file.filename):
                previous_filename = secure_filename(previous_file.filename)
                previous_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{session_id}_{previous_filename}")
                previous_file.save(previous_file_path)
        
        # 初始化分析状态（在线程启动前）
        analysis_results[session_id] = {
            'result': None,
            'current_filename': current_filename,
            'previous_filename': previous_filename,
            'error': None
        }
        analysis_status[session_id] = False
        
        # 在后台线程中进行数据分析
        def analyze_data():
            try:
                result = process_data(current_file_path, previous_file_path, session_id)
                analysis_results[session_id] = {
                    'result': result,
                    'current_filename': current_filename,
                    'previous_filename': previous_filename,
                    'error': None
                }
                analysis_status[session_id] = True
                
                # 保存session到磁盘
                try:
                    session_manager.save_session(session_id, analysis_results[session_id])
                    logging.info(f"Session {session_id} 已保存到磁盘")
                    
                    # 保存到analysis_results目录
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # 使用带下划线的格式
                    analysis_dir = os.path.join(os.path.dirname(__file__), 'analysis_results')
                    os.makedirs(analysis_dir, exist_ok=True)
                    
                    # 保存JSON文件
                    json_file = os.path.join(analysis_dir, f'analysis_{timestamp}.json')
                    with open(json_file, 'w', encoding='utf-8') as f:
                        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
                    
                    # 创建完成标记文件
                    done_file = os.path.join(analysis_dir, f'analysis_{timestamp}.done')
                    with open(done_file, 'w') as f:
                        f.write('1')
                    
                    logging.info(f"分析结果已保存到: {json_file}")
                    
                except Exception as e:
                    logging.error(f"保存分析结果失败: {str(e)}")
                
            except Exception as e:
                logging.error(f"数据分析失败: {str(e)}")
                analysis_results[session_id] = {
                    'result': None,
                    'current_filename': current_filename,
                    'previous_filename': previous_filename,
                    'error': str(e)
                }
                analysis_status[session_id] = True
                
                # 即使出错也保存session
                try:
                    session_manager.save_session(session_id, analysis_results[session_id])
                    logging.info(f"错误session {session_id} 已保存到磁盘")
                except Exception as save_error:
                    logging.error(f"保存错误session失败: {str(save_error)}")
        
        # 启动分析线程
        analysis_thread = threading.Thread(target=analyze_data)
        analysis_thread.daemon = True
        analysis_thread.start()
        
        # 跳转到进度页面
        return redirect(url_for('progress', session_id=session_id))
        
    except Exception as e:
        logging.error(f"分析请求处理失败: {str(e)}")
        flash(f'分析失败: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/progress/<session_id>')
def progress(session_id):
    """显示分析进度页面"""
    # 从全局变量获取文件名，如果分析还未开始则使用默认值
    if session_id in analysis_results:
        current_filename = analysis_results[session_id]['current_filename']
        previous_filename = analysis_results[session_id]['previous_filename']
    else:
        current_filename = '未知文件'
        previous_filename = None
    
    return render_template('progress.html',
                         session_id=session_id,
                         current_filename=current_filename,
                         previous_filename=previous_filename)

@app.route('/api/progress/<session_id>')
def api_progress(session_id):
    """获取分析进度API"""
    return get_progress(session_id)

@app.route('/result/<session_id>')
def results(session_id):
    """显示分析结果页面"""
    try:
        analysis_data = None
        
        # 首先尝试从内存加载
        if session_id in analysis_results and analysis_status.get(session_id, False):
            analysis_data = analysis_results[session_id]
            logging.info(f"从内存加载session: {session_id}")
        else:
            # 从磁盘加载session
            disk_data = session_manager.load_session(session_id)
            if disk_data:
                analysis_data = disk_data
                # 同时加载到内存中以提高后续访问速度
                analysis_results[session_id] = disk_data
                analysis_status[session_id] = True
                logging.info(f"从磁盘加载session: {session_id}")
        
        # 如果都没有找到分析结果
        if not analysis_data:
            # 检查是否分析正在进行中 - 只有当analysis_status明确为False时才重定向到进度页面
            if session_id in analysis_results and analysis_status.get(session_id) == False:
                return redirect(url_for('progress', session_id=session_id))
            else:
                flash('未找到分析结果，可能已过期或不存在', 'error')
                return redirect(url_for('index'))
        
        # 检查是否有错误
        if analysis_data.get('error'):
            flash(f'分析失败: {analysis_data["error"]}', 'error')
            return redirect(url_for('index'))
        
        # 获取分析结果
        result = analysis_data.get('result')
        if not result:
            # 如果没有结果但分析状态未完成，重定向到进度页面
            if not analysis_status.get(session_id, True):
                return redirect(url_for('progress', session_id=session_id))
            flash('分析结果为空', 'error')
            return redirect(url_for('index'))

        return render_template('result.html',
                             result=result,
                             current_filename=analysis_data.get('current_filename', '未知'),
                             previous_filename=analysis_data.get('previous_filename'),
                             session_id=session_id)
        
    except Exception as e:
        logging.error(f"显示结果页面失败: {str(e)}")
        flash(f'显示结果失败: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/view_report/<filename>')
def view_report(filename):
    """在线查看Excel分析报告"""
    try:
        file_path = os.path.join(app.config['EXPORT_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            flash('报告文件不存在', 'error')
            return redirect(url_for('index'))
        
        # 获取文件信息
        file_size = os.path.getsize(file_path)
        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        
        file_info = {
            'filename': filename,
            'file_size': f"{file_size / 1024:.1f} KB",
            'modified_time': file_time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 读取Excel文件的所有工作表
        excel_data = {}
        try:
            with pd.ExcelFile(file_path) as xls:
                for sheet_name in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    # 转换为可序列化的格式
                    excel_data[sheet_name] = {
                        'data': df.values.tolist(),  # 转换为列表格式以匹配模板
                        'columns': df.columns.tolist(),
                        'shape': df.shape,
                        'total_rows': len(df)
                    }
        except Exception as e:
            logging.error(f"读取Excel文件失败: {str(e)}")
            flash(f'读取报告文件失败: {str(e)}', 'error')
            return redirect(url_for('index'))
        
        return render_template('view_report.html', 
                             excel_data=excel_data, 
                             file_info=file_info,
                             sheet_names=list(excel_data.keys()))
        
    except Exception as e:
        logging.error(f"查看报告失败: {str(e)}")
        flash(f'查看报告失败: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    """下载文件"""
    try:
        file_path = os.path.join(app.config['EXPORT_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            flash('文件不存在', 'error')
            return redirect(url_for('index'))
    except Exception as e:
        logging.error(f"下载文件失败: {str(e)}")
        flash(f'下载失败: {str(e)}', 'error')
        return redirect(url_for('index'))

def is_analysis_complete(session_id):
    """检查分析是否完成"""
    # 首先检查内存中的分析状态
    if session_id in analysis_status:
        # 如果内存中有明确的状态，直接返回
        return analysis_status[session_id]
    
    # 如果内存中没有状态，尝试从磁盘加载session
    disk_data = session_manager.load_session(session_id)
    if disk_data:
        # 如果能从磁盘加载到数据，检查是否有结果或错误
        return bool(disk_data.get('result') or disk_data.get('error'))
    
    # 如果内存和磁盘都没有数据，则分析未完成
    return False

if __name__ == '__main__':
    import os
    # 生产环境配置
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    port = int(os.getenv('PORT', 5001))
    host = os.getenv('HOST', '0.0.0.0')
    
    app.run(debug=debug_mode, port=port, host=host)