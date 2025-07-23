# 排名查询工具优化说明

## 主要改进

### 1. 排名显示优化
- **问题**: 排名1-3显示不够直观
- **解决**: 排名1-3现在显示为"1页第X名"，其他排名显示为"X页第Y名"
- **示例**: 
  - 排名1 → "1页第1名"
  - 排名15 → "2页第5名"
  - 排名0 → "未上榜"

### 2. 查询结果持久化
- **问题**: 中断后无法继续查询
- **解决**: 
  - 每个关键词查询后立即保存状态
  - 支持中断后继续查询
  - 详细的进度统计和状态管理
  - 查询历史记录

### 3. 2分钟重试机制
- **问题**: 查询失败后没有重试
- **解决**: 
  - 查询失败后自动重试，间隔2分钟
  - 最多重试3次
  - 重试过程中显示详细日志

### 4. API配置管理
- **问题**: API密钥暴露在页面中
- **解决**: 
  - 创建独立的配置文件 `config.json`
  - API密钥安全存储
  - 配置工具 `setup_config.py` 管理设置

### 5. 随机批次名生成
- **问题**: 批次名称重复或不够友好
- **解决**: 
  - 自动生成随机批次名
  - 格式: "形容词+名词+随机数字"
  - 示例: "智能排名_456", "高效监控_789"

### 6. 批次响应优化
- **问题**: 页面刷新批次列表无响应
- **解决**: 
  - 改进批次数据结构
  - 添加更新时间和进度统计
  - 优化批次信息获取逻辑

## 使用方法

### 1. 配置API密钥
```bash
# 设置API密钥
python setup_config.py setup

# 查看当前配置
python setup_config.py show
```

### 2. 新功能说明

#### 持久化查询
- 查询过程中会自动保存每个关键词的状态
- 支持以下状态：
  - `pending`: 等待查询
  - `querying`: 查询中
  - `completed`: 查询完成
  - `error`: 查询失败

#### 中断后继续查询
```python
# 恢复指定批次的查询
manager = RankQueryManager()
result = manager.resume_batch_query(batch_id, callback=progress_callback)
```

#### 获取批次进度
```python
# 获取查询进度
progress = manager.get_batch_progress(batch_id)
print(f"总数: {progress['total']}")
print(f"已完成: {progress['completed']}")
print(f"错误: {progress['error']}")
print(f"待查询: {progress['pending']}")
```

#### 批次结果查看
```python
# 获取完整的批次查询结果
results = manager.get_batch_results(batch_id)
for result in results:
    if result['status'] == 'completed':
        print(f"关键词: {result['keyword']}")
        print(f"排名: {result['formatted_rank']}")
        print(f"URL: {result['rank_url']}")
```

### 3. 配置文件说明

`config.json` 配置项：
```json
{
  "api_key": "your_api_key_here",
  "api_url": "https://openapi.chinaz.net/v1/1001/baidupc_keywordranking",
  "timeout": 10,
  "retry_interval": 120,
  "max_retries": 3,
  "request_delay": 1
}
```

- `api_key`: 站长工具API密钥
- `api_url`: API接口地址
- `timeout`: 请求超时时间（秒）
- `retry_interval`: 重试间隔（秒）
- `max_retries`: 最大重试次数
- `request_delay`: 请求间隔（秒）

## 新增方法

### RankQueryManager类新增方法

1. `generate_random_batch_name()` - 生成随机批次名
2. `format_rank_display(rank)` - 格式化排名显示
3. `update_batch_progress(batch_data)` - 更新批次进度
4. `get_batch_progress(batch_id)` - 获取批次进度
5. `get_pending_keywords(batch_id)` - 获取待查询关键词
6. `resume_batch_query(batch_id, callback)` - 恢复批次查询
7. `query_rank_batch_with_persistence(batch_id, keywords, api_key, callback)` - 持久化批量查询
8. `get_batch_results(batch_id)` - 获取批次结果

### 改进的现有方法

1. `query_rank()` - 添加重试机制和格式化排名
2. `create_batch()` - 支持随机批次名和更完整的数据结构
3. `update_keyword_status()` - 支持更完整的状态管理
4. `get_exam_type_stats()` - 改进统计逻辑

## 错误处理

- 所有API调用都有完整的错误处理
- 重试机制确保临时网络问题不会导致查询失败
- 详细的日志记录帮助调试问题
- 状态持久化确保数据不会丢失

## 性能优化

- 使用配置文件管理请求间隔
- 支持中断后继续查询，避免重复工作
- 改进的数据结构减少文件I/O
- 批次进度统计提供实时反馈

## 注意事项

1. 首次使用需要设置API密钥
2. 重试间隔设置为2分钟，请耐心等待
3. 批次查询会自动保存状态，可以随时中断和恢复
4. 建议定期清理过期的批次数据

## 故障排除

### 1. API密钥问题
```bash
# 检查配置
python setup_config.py show

# 重新设置API密钥
python setup_config.py setup
```

### 2. 查询失败
- 检查网络连接
- 确认API密钥有效
- 查看日志文件获取详细错误信息

### 3. 批次数据损坏
- 检查 `rank_batches/` 目录下的JSON文件
- 必要时可以手动修复或删除损坏的批次文件

## 更新日志

- ✅ 修复排名显示逻辑
- ✅ 实现查询结果持久化
- ✅ 添加2分钟重试机制
- ✅ 创建API配置管理
- ✅ 实现随机批次名生成
- ✅ 优化批次响应逻辑 