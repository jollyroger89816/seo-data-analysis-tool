# API配置说明

## 🔑 API Key配置

为了安全起见，系统不再在界面中输入API Key，而是使用配置文件管理。

### 配置步骤

1. **复制示例配置文件**
   ```bash
   cp api_keys.json.example api_keys.json
   ```

2. **编辑配置文件**
   ```bash
   vim api_keys.json
   # 或使用其他编辑器
   nano api_keys.json
   ```

3. **填入你的API Key**
   ```json
   {
     "chinaz_api_key": "你的站长之家API Key",
     "other_api_keys": {
       "baidu_api_key": "",
       "google_api_key": ""
     },
     "settings": {
       "auto_retry": true,
       "cache_enabled": true,
       "default_concurrent": 2,
       "max_retries": 2,
       "cache_expire_minutes": 30
     }
   }
   ```

### 获取站长之家API Key

1. 访问 [站长之家开放平台](https://data.chinaz.com/api)
2. 注册账号并登录
3. 申请API接口权限
4. 获取API Key

### 配置说明

**API Key设置:**
- `chinaz_api_key`: 站长之家API密钥（必填）
- `other_api_keys`: 其他API密钥（预留）

**系统设置:**
- `auto_retry`: 是否启用自动重试（推荐: true）
- `cache_enabled`: 是否启用结果缓存（推荐: true）
- `default_concurrent`: 默认并发查询数（推荐: 2）
- `max_retries`: 最大重试次数（推荐: 2）
- `cache_expire_minutes`: 缓存过期时间（推荐: 30分钟）

### 安全注意事项

⚠️ **重要:** 
- `api_keys.json` 文件已添加到 `.gitignore`，不会被提交到版本控制
- 请勿在代码中硬编码API Key
- 定期更换API Key确保安全

### 故障排除

**API Key配置状态检查:**
- 启动服务后，访问系统页面
- 查看"API配置"区域的状态显示
- 绿色"已配置"表示正常
- 黄色"未配置"表示需要配置API Key
- 红色"检查失败"表示配置文件有问题

**常见问题:**
1. **配置文件不存在**: 复制 `api_keys.json.example` 为 `api_keys.json`
2. **JSON格式错误**: 检查JSON语法是否正确
3. **API Key无效**: 检查站长之家平台上的API Key是否正确

### 验证配置

配置完成后，重启服务：
```bash
python start_services.py
```

然后访问系统页面，检查API配置状态是否显示为"已配置"。 