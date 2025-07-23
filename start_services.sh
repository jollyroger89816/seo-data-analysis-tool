#!/bin/bash
# -*- coding: utf-8 -*-
# SEO数据分析与排名查询服务启动脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# PID文件
DATA_ANALYSIS_PID_FILE="data_analysis.pid"
RANK_QUERY_PID_FILE="rank_query.pid"

# 日志函数
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] ✓${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ✗${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] ⚠${NC} $1"
}

# 检查端口是否被占用
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 1  # 端口被占用
    else
        return 0  # 端口可用
    fi
}

# 等待服务启动
wait_for_service() {
    local url=$1
    local service_name=$2
    local timeout=30
    local count=0
    
    log "等待 $service_name 启动..."
    
    while [ $count -lt $timeout ]; do
        if curl -s "$url" >/dev/null 2>&1; then
            log_success "$service_name 启动成功！"
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done
    
    log_error "$service_name 启动超时"
    return 1
}

# 启动数据分析服务
start_data_analysis() {
    log "启动数据分析服务..."
    
    # 检查端口5001
    if ! check_port 5001; then
        log_error "端口 5001 已被占用，请先关闭相关进程"
        return 1
    fi
    
    # 检查脚本文件
    if [ ! -f "keyword_rank_analyzer.py" ]; then
        log_error "数据分析服务脚本不存在: keyword_rank_analyzer.py"
        return 1
    fi
    
    # 启动服务
    nohup python keyword_rank_analyzer.py > data_analysis.log 2>&1 &
    local pid=$!
    echo $pid > "$DATA_ANALYSIS_PID_FILE"
    
    log "数据分析服务启动，PID: $pid"
    
    # 等待服务启动
    if wait_for_service "http://127.0.0.1:5001" "数据分析服务"; then
        return 0
    else
        return 1
    fi
}

# 启动排名查询服务
start_rank_query() {
    log "启动排名查询服务..."
    
    # 检查端口5002
    if ! check_port 5002; then
        log_error "端口 5002 已被占用，请先关闭相关进程"
        return 1
    fi
    
    # 检查脚本文件
    if [ ! -f "rank_query_app.py" ]; then
        log_error "排名查询服务脚本不存在: rank_query_app.py"
        return 1
    fi
    
    # 启动服务
    nohup python rank_query_app.py > rank_query.log 2>&1 &
    local pid=$!
    echo $pid > "$RANK_QUERY_PID_FILE"
    
    log "排名查询服务启动，PID: $pid"
    
    # 等待服务启动
    if wait_for_service "http://127.0.0.1:5002" "排名查询服务"; then
        return 0
    else
        return 1
    fi
}

# 停止服务
stop_service() {
    local pid_file=$1
    local service_name=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            log "停止 $service_name (PID: $pid)..."
            kill $pid
            sleep 2
            
            # 检查是否已停止
            if ps -p $pid > /dev/null 2>&1; then
                log_warning "强制停止 $service_name"
                kill -9 $pid
            fi
            
            log_success "$service_name 已停止"
        else
            log_warning "$service_name 进程不存在"
        fi
        rm -f "$pid_file"
    else
        log_warning "$service_name PID文件不存在"
    fi
}

# 启动所有服务
start_all() {
    log "=== 启动所有服务 ==="
    
    local success_count=0
    
    # 启动数据分析服务
    if start_data_analysis; then
        success_count=$((success_count + 1))
    fi
    
    # 启动排名查询服务
    if start_rank_query; then
        success_count=$((success_count + 1))
    fi
    
    if [ $success_count -gt 0 ]; then
        log_success "成功启动 $success_count/2 个服务"
        show_service_info
        return 0
    else
        log_error "所有服务启动失败"
        return 1
    fi
}

# 停止所有服务
stop_all() {
    log "=== 停止所有服务 ==="
    
    stop_service "$DATA_ANALYSIS_PID_FILE" "数据分析服务"
    stop_service "$RANK_QUERY_PID_FILE" "排名查询服务"
    
    log_success "所有服务已停止"
}

# 检查服务状态
check_status() {
    log "=== 检查服务状态 ==="
    
    # 检查数据分析服务
    if curl -s "http://127.0.0.1:5001" >/dev/null 2>&1; then
        log_success "数据分析服务: 正常运行"
    else
        log_error "数据分析服务: 无法连接"
    fi
    
    # 检查排名查询服务
    if curl -s "http://127.0.0.1:5002" >/dev/null 2>&1; then
        log_success "排名查询服务: 正常运行"
    else
        log_error "排名查询服务: 无法连接"
    fi
}

# 显示服务信息
show_service_info() {
    echo ""
    log "=== 服务信息 ==="
    echo -e "${GREEN}✓ 数据分析工具: http://127.0.0.1:5001${NC}"
    echo -e "${GREEN}✓ 排名查询工具: http://127.0.0.1:5002${NC}"
    echo ""
    echo -e "${YELLOW}使用方法:${NC}"
    echo "  ./start_services.sh start   - 启动所有服务"
    echo "  ./start_services.sh stop    - 停止所有服务"
    echo "  ./start_services.sh restart - 重启所有服务"
    echo "  ./start_services.sh status  - 检查服务状态"
    echo ""
    echo -e "${BLUE}日志文件:${NC}"
    echo "  data_analysis.log - 数据分析服务日志"
    echo "  rank_query.log    - 排名查询服务日志"
}

# 重启所有服务
restart_all() {
    log "=== 重启所有服务 ==="
    stop_all
    sleep 2
    start_all
}

# 信号处理器
cleanup() {
    echo ""
    log "接收到停止信号，正在关闭所有服务..."
    stop_all
    exit 0
}

# 注册信号处理器
trap cleanup SIGINT SIGTERM

# 主逻辑
case "${1:-start}" in
    start)
        start_all
        if [ $? -eq 0 ]; then
            log "服务启动完成，按 Ctrl+C 停止所有服务"
            # 保持脚本运行
            while true; do
                sleep 1
            done
        fi
        ;;
    stop)
        stop_all
        ;;
    restart)
        restart_all
        ;;
    status)
        check_status
        ;;
    help)
        echo "SEO数据分析与排名查询服务管理器"
        echo ""
        echo "使用方法:"
        echo "  ./start_services.sh [命令]"
        echo ""
        echo "命令:"
        echo "  start   - 启动所有服务 (默认)"
        echo "  stop    - 停止所有服务"
        echo "  restart - 重启所有服务"
        echo "  status  - 检查服务状态"
        echo "  help    - 显示帮助信息"
        ;;
    *)
        log_error "未知命令: $1"
        echo "使用 './start_services.sh help' 查看帮助"
        exit 1
        ;;
esac 