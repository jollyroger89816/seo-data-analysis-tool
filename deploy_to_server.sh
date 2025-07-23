#!/bin/bash

# 服务器信息
SERVER="root@120.48.54.112"
REMOTE_DIR="/opt/seo_analysis"

# 本地目录
LOCAL_DIR="."

# 创建排除文件列表
cat > exclude.txt << EOL
.DS_Store
__pycache__
*.pyc
*.log
*.pid
analysis_results/*
sessions/*
uploads/*
exports/*
tasks/*
.git
.gitignore
*.bak
*copy*
EOL

echo "=== SEO数据分析系统部署脚本 ==="
echo "目标服务器: $SERVER"
echo "目标目录: $REMOTE_DIR"

# 1. 检查远程目录是否存在，不存在则创建
echo "检查远程目录..."
ssh $SERVER "mkdir -p $REMOTE_DIR"

# 2. 备份远程配置文件
echo "备份远程配置文件..."
ssh $SERVER "cd $REMOTE_DIR && \
    if [ -f config.json ]; then cp config.json config.json.bak; fi && \
    if [ -f api_keys.json ]; then cp api_keys.json api_keys.json.bak; fi"

# 3. 同步文件
echo "开始同步文件..."
rsync -avz --progress --exclude-from=exclude.txt \
    $LOCAL_DIR/ \
    $SERVER:$REMOTE_DIR/

# 4. 恢复配置文件
echo "恢复配置文件..."
ssh $SERVER "cd $REMOTE_DIR && \
    if [ -f config.json.bak ]; then mv config.json.bak config.json; fi && \
    if [ -f api_keys.json.bak ]; then mv api_keys.json.bak api_keys.json; fi"

# 5. 创建必要的目录
echo "创建必要的目录..."
ssh $SERVER "cd $REMOTE_DIR && \
    mkdir -p analysis_results sessions uploads exports tasks static/css static/js templates"

# 6. 设置权限
echo "设置权限..."
ssh $SERVER "chown -R root:root $REMOTE_DIR && \
    chmod -R 755 $REMOTE_DIR"

# 7. 重启服务
echo "重启服务..."
ssh $SERVER "cd $REMOTE_DIR && \
    if [ -f start_services.py ]; then \
        python3 start_services.py stop 2>/dev/null; \
        nohup python3 start_services.py > start_services.log 2>&1 &
    fi"

# 8. 清理本地临时文件
rm -f exclude.txt

echo "部署完成！"
echo "请检查服务状态：http://120.48.54.112:5051" 