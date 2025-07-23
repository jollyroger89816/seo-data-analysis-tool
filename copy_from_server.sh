#!/bin/bash

# 服务器文件复制脚本
SERVER="root@120.48.54.112"
SERVER_PATH="/opt/seo_analysis"
LOCAL_PATH="/Users/tang/Desktop/python/数据分析"

echo "正在从服务器复制文件..."
echo "服务器: $SERVER"
echo "服务器路径: $SERVER_PATH"
echo "本地路径: $LOCAL_PATH"

# 创建备份目录
BACKUP_DIR="${LOCAL_PATH}/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "创建本地文件备份..."
cp "${LOCAL_PATH}/keyword_rank_analyzer.py" "$BACKUP_DIR/" 2>/dev/null
cp -r "${LOCAL_PATH}/templates" "$BACKUP_DIR/" 2>/dev/null

# 直接复制服务器文件到本地
echo "复制keyword_rank_analyzer.py..."
scp "$SERVER:$SERVER_PATH/keyword_rank_analyzer.py" "$LOCAL_PATH/"

echo "复制templates目录..."
scp -r "$SERVER:$SERVER_PATH/templates" "$LOCAL_PATH/"

echo "复制session_manager.py..."
scp "$SERVER:$SERVER_PATH/session_manager.py" "$LOCAL_PATH/" 2>/dev/null

echo "复制config.json..."
scp "$SERVER:$SERVER_PATH/config.json" "$LOCAL_PATH/" 2>/dev/null

echo "复制requirements.txt..."
scp "$SERVER:$SERVER_PATH/requirements.txt" "$LOCAL_PATH/" 2>/dev/null

echo ""
echo "复制完成！"
echo "备份已保存到: $BACKUP_DIR"
echo "请检查复制的文件是否正确" 