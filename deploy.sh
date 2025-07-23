#!/bin/bash
# -*- coding: utf-8 -*-
# SEO数据分析工具自动化部署脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 服务器配置
SERVER_IP="120.48.54.112"
SERVER_USER="root"
SERVER_PATH="/opt/seo_analysis"
LOCAL_PATH="$(pwd)"

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

# 检查必要文件
check_files() {
    log "检查必要文件..."
    
    required_files=(
        "keyword_rank_analyzer.py"
        "rank_query_app.py"
        "session_manager.py"
        "start_services.py"
        "requirements.txt"
        "config.json"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            log_error "缺少必要文件: $file"
            exit 1
        fi
    done
    
    log_success "所有必要文件检查完成"
}

# 创建部署包
create_package() {
    log "创建部署包..."
    
    # 创建临时目录
    TEMP_DIR="/tmp/seo_analysis_deploy_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$TEMP_DIR"
    
    # 复制必要文件
    cp -r templates "$TEMP_DIR/"
    cp -r static "$TEMP_DIR/" 2>/dev/null || true
    cp *.py "$TEMP_DIR/"
    cp requirements.txt "$TEMP_DIR/"
    cp config.json "$TEMP_DIR/"
    cp start_services.sh "$TEMP_DIR/"
    
    # 创建必要目录
    mkdir -p "$TEMP_DIR/sessions"
    mkdir -p "$TEMP_DIR/uploads"
    mkdir -p "$TEMP_DIR/exports"
    mkdir -p "$TEMP_DIR/logs"
    
    # 创建服务器配置文件
    cat > "$TEMP_DIR/server_config.py" << 'EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务器配置文件
"""

# 服务器配置
SERVER_HOST = '0.0.0.0'
SERVER_PORT_DATA = 5001
SERVER_PORT_RANK = 5002
DEBUG = False

# 安全配置
SECRET_KEY = 'your-secret-key-here-change-in-production'

# 文件上传配置
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
UPLOAD_FOLDER = 'uploads'
EXPORT_FOLDER = 'exports'

# 日志配置
LOG_LEVEL = 'INFO'
LOG_FILE = 'logs/application.log'
EOF
    
    # 创建systemd服务文件
    cat > "$TEMP_DIR/seo-analysis-data.service" << 'EOF'
[Unit]
Description=SEO Analysis Data Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/seo_analysis
Environment=PYTHONPATH=/opt/seo_analysis
ExecStart=/usr/bin/python3 keyword_rank_analyzer.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    cat > "$TEMP_DIR/seo-analysis-rank.service" << 'EOF'
[Unit]
Description=SEO Analysis Rank Query Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/seo_analysis
Environment=PYTHONPATH=/opt/seo_analysis
ExecStart=/usr/bin/python3 rank_query_app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # 创建部署后脚本
    cat > "$TEMP_DIR/post_deploy.sh" << 'EOF'
#!/bin/bash
# 部署后配置脚本

# 更新系统
apt-get update

# 安装Python3和pip
apt-get install -y python3 python3-pip python3-venv

# 创建虚拟环境
cd /opt/seo_analysis
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 设置权限
chmod +x start_services.sh
chmod +x start_services.py
chown -R root:root /opt/seo_analysis

# 创建日志目录
mkdir -p /var/log/seo_analysis
chown -R root:root /var/log/seo_analysis

# 复制systemd服务文件
cp seo-analysis-data.service /etc/systemd/system/
cp seo-analysis-rank.service /etc/systemd/system/

# 重新加载systemd
systemctl daemon-reload

# 启用服务
systemctl enable seo-analysis-data
systemctl enable seo-analysis-rank

# 启动服务
systemctl start seo-analysis-data
systemctl start seo-analysis-rank

# 开放防火墙端口
ufw allow 5001
ufw allow 5002

echo "部署完成！"
echo "数据分析服务: http://120.48.54.112:5001"
echo "排名查询服务: http://120.48.54.112:5002"
EOF
    
    chmod +x "$TEMP_DIR/post_deploy.sh"
    
    # 创建压缩包
    cd /tmp
    tar -czf "seo_analysis_deploy.tar.gz" -C "$TEMP_DIR" .
    
    log_success "部署包创建完成: /tmp/seo_analysis_deploy.tar.gz"
    echo "$TEMP_DIR"
}

# 上传到服务器
upload_to_server() {
    local temp_dir=$1
    log "上传文件到服务器..."
    
    # 上传压缩包
    scp /tmp/seo_analysis_deploy.tar.gz "$SERVER_USER@$SERVER_IP:/tmp/"
    
    if [ $? -eq 0 ]; then
        log_success "文件上传成功"
    else
        log_error "文件上传失败"
        exit 1
    fi
}

# 在服务器上部署
deploy_on_server() {
    log "在服务器上部署..."
    
    ssh "$SERVER_USER@$SERVER_IP" << 'EOF'
        # 停止现有服务
        systemctl stop seo-analysis-data 2>/dev/null || true
        systemctl stop seo-analysis-rank 2>/dev/null || true
        
        # 备份现有部署
        if [ -d "/opt/seo_analysis" ]; then
            mv /opt/seo_analysis /opt/seo_analysis_backup_$(date +%Y%m%d_%H%M%S)
        fi
        
        # 创建部署目录
        mkdir -p /opt/seo_analysis
        
        # 解压部署包
        cd /opt/seo_analysis
        tar -xzf /tmp/seo_analysis_deploy.tar.gz
        
        # 执行部署后脚本
        chmod +x post_deploy.sh
        ./post_deploy.sh
        
        # 清理临时文件
        rm -f /tmp/seo_analysis_deploy.tar.gz
EOF
    
    if [ $? -eq 0 ]; then
        log_success "服务器部署完成"
    else
        log_error "服务器部署失败"
        exit 1
    fi
}

# 检查部署状态
check_deployment() {
    log "检查部署状态..."
    
    # 检查服务状态
    ssh "$SERVER_USER@$SERVER_IP" << 'EOF'
        echo "=== 服务状态 ==="
        systemctl status seo-analysis-data --no-pager
        systemctl status seo-analysis-rank --no-pager
        
        echo "=== 端口监听 ==="
        netstat -tlnp | grep -E ':500[12]'
        
        echo "=== 最近日志 ==="
        tail -20 /var/log/seo_analysis/application.log 2>/dev/null || echo "暂无日志"
EOF
}

# 主函数
main() {
    echo "=================================================="
    echo "           SEO数据分析工具自动化部署"
    echo "=================================================="
    echo "目标服务器: $SERVER_IP"
    echo "部署路径: $SERVER_PATH"
    echo "=================================================="
    
    # 检查SSH连接
    log "检查SSH连接..."
    if ! ssh -o ConnectTimeout=10 "$SERVER_USER@$SERVER_IP" "echo 'SSH连接正常'"; then
        log_error "无法连接到服务器，请检查："
        echo "1. 服务器IP地址是否正确"
        echo "2. SSH密钥是否配置正确"
        echo "3. 服务器是否在线"
        exit 1
    fi
    
    log_success "SSH连接正常"
    
    # 执行部署步骤
    check_files
    temp_dir=$(create_package)
    upload_to_server "$temp_dir"
    deploy_on_server
    check_deployment
    
    # 清理临时文件
    rm -rf "$temp_dir"
    rm -f /tmp/seo_analysis_deploy.tar.gz
    
    echo "=================================================="
    log_success "部署完成！"
    echo "数据分析服务: http://120.48.54.112:5001"
    echo "排名查询服务: http://120.48.54.112:5002"
    echo "=================================================="
}

# 如果直接运行脚本
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi 