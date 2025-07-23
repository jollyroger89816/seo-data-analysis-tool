#!/bin/bash

# 服务器同步脚本
SERVER="root@120.48.54.112"
SERVER_PATH="/opt/seo_analysis"
LOCAL_PATH="/Users/tang/Desktop/python/数据分析"

echo "正在从服务器同步文件..."
echo "服务器: $SERVER"
echo "服务器路径: $SERVER_PATH"
echo "本地路径: $LOCAL_PATH"

# 创建备份目录
BACKUP_DIR="${LOCAL_PATH}/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "创建本地备份到: $BACKUP_DIR"
cp -r "${LOCAL_PATH}"/* "$BACKUP_DIR/" 2>/dev/null

# 同步主要的Python文件
echo "同步keyword_rank_analyzer.py..."
rsync -avz "$SERVER:$SERVER_PATH/keyword_rank_analyzer.py" "$LOCAL_PATH/"

# 同步模板文件
echo "同步模板文件..."
rsync -avz "$SERVER:$SERVER_PATH/templates/" "$LOCAL_PATH/templates/"

# 同步其他重要文件
echo "同步其他重要文件..."
rsync -avz "$SERVER:$SERVER_PATH/session_manager.py" "$LOCAL_PATH/" 2>/dev/null
rsync -avz "$SERVER:$SERVER_PATH/config.json" "$LOCAL_PATH/" 2>/dev/null
rsync -avz "$SERVER:$SERVER_PATH/requirements.txt" "$LOCAL_PATH/" 2>/dev/null

echo "同步完成！"
echo "备份已保存到: $BACKUP_DIR"
echo "请检查同步的文件是否正确" 