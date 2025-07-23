# Session历史记录管理系统

## 概述

增强的Session管理器现在能够自动保存和管理关键词提取和排名查询的历史记录，让您可以追踪和回顾所有的操作历史。

## 功能特性

### 📝 自动记录保存
- **关键词提取记录**: 每次完成关键词提取时自动保存
- **排名查询记录**: 每次完成排名查询时自动保存
- **详细信息保存**: 包括时间、参数、结果统计等完整信息

### 🔍 历史记录查看
- **分类查看**: 分别查看关键词提取和排名查询历史
- **详细统计**: 显示成功率、处理数量等关键指标
- **过滤条件**: 记录使用的过滤条件（如适用）

### 🗂️ 记录管理
- **记录删除**: 可以删除不需要的历史记录
- **过期清理**: 自动清理超过指定天数的旧记录
- **统计信息**: 实时显示历史记录统计

## 使用方法

### 1. 查看历史记录
访问历史记录页面：
```
http://localhost:5002/history
```

### 2. 自动记录保存
系统会在以下情况自动保存记录：

#### 关键词提取完成后
- 提取方法：`from_analysis`（从分析结果）或 `with_filter`（带过滤条件）
- 保存信息：总URL数、成功提取数、过滤条件、处理时间等

#### 排名查询完成后
- 查询方法：`from_keywords`（基于关键词查询）
- 保存信息：总查询数、成功查询数、处理时间等

### 3. API接口

#### 获取关键词提取历史
```http
GET /api/keyword_history?limit=20
```

#### 获取排名查询历史
```http
GET /api/rank_history?limit=20
```

#### 获取历史记录统计
```http
GET /api/history_statistics
```

#### 获取特定记录详情
```http
GET /api/keyword_history/{session_id}
GET /api/rank_history/{session_id}
```

#### 删除特定记录
```http
DELETE /api/delete_keyword_history/{session_id}
DELETE /api/delete_rank_history/{session_id}
```

#### 清理过期记录
```http
POST /api/cleanup_old_records
Content-Type: application/json

{
    "max_age_days": 30
}
```

## 存储结构

### 目录结构
```
sessions/
├── keyword_history/     # 关键词提取记录
│   ├── extract_1234567890.json
│   └── extract_1234567891.json
├── rank_history/        # 排名查询记录
│   ├── rank_1234567890.json
│   └── rank_1234567891.json
└── session_files/       # 原有的session文件
```

### 记录格式

#### 关键词提取记录
```json
{
    "session_id": "extract_1234567890",
    "type": "keyword_extraction",
    "timestamp": "2024-01-01T12:00:00",
    "extraction_data": {
        "session_id": "extract_1234567890",
        "total_urls": 100,
        "successful_extractions": 85,
        "extraction_method": "from_analysis",
        "filter_conditions": {
            "min_decline_uv": 10,
            "max_decline_uv": 1000,
            "min_decline_rate": 5.0,
            "max_decline_rate": 80.0
        },
        "max_workers": 5,
        "results": [...],
        "timestamp": "2024-01-01T12:00:00"
    }
}
```

#### 排名查询记录
```json
{
    "session_id": "query_1234567890",
    "type": "rank_query",
    "timestamp": "2024-01-01T12:00:00",
    "query_data": {
        "session_id": "query_1234567890",
        "total_queries": 85,
        "successful_queries": 78,
        "query_method": "from_keywords",
        "results": [...],
        "timestamp": "2024-01-01T12:00:00"
    }
}
```

## 配置选项

### 记录保留策略
- **默认保留期**: 30天
- **自动清理**: 支持手动或定期清理过期记录
- **存储限制**: 建议定期清理避免占用过多磁盘空间

### 性能优化
- **异步保存**: 记录保存不影响主要功能性能
- **索引优化**: 按时间戳排序，快速查找最新记录
- **批量操作**: 支持批量清理和导出

## 注意事项

1. **磁盘空间**: 历史记录会占用磁盘空间，建议定期清理
2. **隐私保护**: 记录包含URL和关键词信息，注意数据保护
3. **备份建议**: 重要的历史记录建议定期备份

## 故障排除

### 常见问题

1. **记录未保存**
   - 检查session_manager是否正确初始化
   - 检查磁盘空间是否充足
   - 查看应用日志中的错误信息

2. **历史记录页面无法访问**
   - 确认Flask应用运行在5002端口
   - 检查templates目录是否存在history.html

3. **记录格式错误**
   - 检查JSON文件格式是否正确
   - 清理损坏的记录文件

### 日志查看
检查应用日志中的相关信息：
```
关键词提取记录已保存: extract_1234567890
排名查询记录已保存: query_1234567890
保存关键词提取记录失败: 错误信息
```

## 升级说明

从旧版本升级到带历史记录功能的版本：

1. 更新session_manager.py
2. 重启应用服务
3. 新的记录将自动开始保存
4. 旧的session记录不受影响

## 技术支持

如有问题，请检查：
1. 应用日志文件
2. sessions目录的权限设置
3. 磁盘空间使用情况
4. Python依赖包是否完整 