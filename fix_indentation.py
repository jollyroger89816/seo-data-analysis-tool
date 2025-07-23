#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
修复Python文件的缩进问题
"""

import sys

def fix_indentation(filename):
    """修复文件的缩进问题"""
    print(f"正在修复文件: {filename}")
    
    # 读取文件
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 修复后的行
    fixed_lines = []
    
    # 处理每一行
    for i, line in enumerate(lines):
        # 修复特定行的缩进问题
        if i == 283:  # 第284行
            fixed_lines.append('            analysis_data = get_latest_analysis_result()\n')
        elif i == 208:  # 第209行
            fixed_lines.append('            return None\n')
        elif i == 254:  # 第255行
            fixed_lines.append('            return []\n')
        elif i == 446:  # 第447行
            fixed_lines.append('        try:\n')
        elif i == 464:  # 第465行
            fixed_lines.append('                final_result = None\n')
        elif i == 475:  # 第476行
            fixed_lines.append('                    final_result = {\n')
        elif i == 480:  # 第481行
            fixed_lines.append("                    final_result = {'rank': '未找到', 'title': '', 'url': '', 'site_count': 0, 'total_ranks': 0}\n")
        elif i == 492:  # 第493行
            fixed_lines.append('                set_cached_rank(domain, keyword, final_result)\n')
        elif i == 494:  # 第495行
            fixed_lines.append("            elif result.get('StateCode') == -1:  # API错误，不需要重试\n")
        elif i == 495:  # 第496行
            fixed_lines.append("                error_msg = result.get('Reason', '未知错误')\n")
        elif i == 506:  # 第507行
            fixed_lines.append('                    continue\n')
        elif i == 511:  # 第512行
            fixed_lines.append('            else:\n')
        elif i == 512:  # 第513行
            fixed_lines.append("                error_msg = f\"API状态码: {result.get('StateCode')}\"\n")
        elif i == 516:  # 第517行
            fixed_lines.append('                    continue\n')
        elif i == 519:  # 第520行
            fixed_lines.append('        else:\n')
        elif i == 520:  # 第521行
            fixed_lines.append("            return {'error': f'API请求失败，状态码: {response.status_code}'}\n")
        elif i == 526:  # 第527行
            fixed_lines.append('                    continue\n')
        elif i == 528:  # 第529行
            fixed_lines.append('            else:\n')
        elif i == 529:  # 第530行
            fixed_lines.append("                logging.error(f\"API请求超时 - 域名: {domain}, 关键词: {keyword}\")\n")
        elif i == 531:  # 第532行
            fixed_lines.append("    except requests.exceptions.RequestException as e:\n")
        elif i == 532:  # 第533行
            fixed_lines.append('        if attempt < max_retries:\n')
        elif i == 535:  # 第536行
            fixed_lines.append('                    continue\n')
        elif i == 537:  # 第538行
            fixed_lines.append('            else:\n')
        elif i == 538:  # 第539行
            fixed_lines.append("                logging.error(f\"API请求网络错误 - 域名: {domain}, 关键词: {keyword}: {str(e)}\")\n")
        elif i == 540:  # 第541行
            fixed_lines.append("    except Exception as e:\n")
        elif i == 541:  # 第542行
            fixed_lines.append("        logging.error(f\"API请求失败 - 域名: {domain}, 关键词: {keyword}: {str(e)}\")\n")
        elif i == 2062:  # 第2063行
            fixed_lines.append('        response = requests.get(quota_url, params=params, headers=headers, timeout=10, verify=False)\n')
        elif i == 2067:  # 第2068行
            fixed_lines.append("                user_info = result.get('Result', {})\n")
        elif i == 2068:  # 第2069行
            fixed_lines.append('                return jsonify({\n')
        elif i == 2074:  # 第2075行
            fixed_lines.append('            else:\n')
        elif i == 2075:  # 第2076行
            fixed_lines.append("                return jsonify({'error': result.get('Reason', '查询失败')})\n")
        elif i == 2077:  # 第2078行
            fixed_lines.append("        return jsonify({'error': f'请求失败，状态码: {response.status_code}'})\n")
        elif i == 2102:  # 第2103行
            fixed_lines.append('            return jsonify({\n')
        elif i == 2114:  # 第2115行
            fixed_lines.append('        return jsonify({\n')
        else:
            fixed_lines.append(line)
    
    # 写入修复后的文件
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print(f"文件修复完成: {filename}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"用法: {sys.argv[0]} <文件名>")
        sys.exit(1)
    
    fix_indentation(sys.argv[1])
