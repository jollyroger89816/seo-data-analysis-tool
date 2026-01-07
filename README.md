# SEO数据分析工具

一个专业的SEO数据分析和排名监控平台，为企业提供全方位的SEO数据洞察和竞争情报分析。

## 🌟 项目特色

- **双服务架构**：数据分析服务 + 排名查询服务
- **智能算法**：URL ID提取、下降词识别、考种自动分类
- **实时监控**：24/7排名监控和异常预警
- **自动化分析**：节省90%人工时间的数据处理

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip
- 4GB+ 内存

### 安装依赖

```bash
# 克隆项目
git clone https://github.com/jollyroger89816/seo-data-analysis-tool.git
cd seo-data-analysis-tool

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### API配置

```bash
# 复制配置文件
cp api_keys.json.example api_keys.json

# 编辑配置文件，填入API密钥
{
  "chinaz_api_key": "你的API密钥",
  "settings": {
    "auto_retry": true,
    "cache_enabled": true,
    "default_concurrent": 2,
    "max_retries": 2,
    "cache_expire_minutes": 30
  }
}
```

### 启动服务

```bash
# 启动所有服务
./start_services.sh

# 或者使用Python脚本
python start_services.py start
```

### 访问地址

- 数据分析服务：http://127.0.0.1:5001
- 排名查询服务：http://127.0.0.1:5002

## 📊 核心功能

### 🔍 数据分析服务
- **Excel智能处理**：支持多种列名格式自动映射
- **URL标准化**：多种URL模式匹配和去重处理
- **下降词识别**：智能识别UV>10且降幅>50%的关键词
- **对比分析**：同比/环比数据对比和趋势分析
- **报告生成**：Excel格式分析报告和可视化图表

### 🎯 排名查询服务
- **实时排名查询**：支持批量关键词排名检测
- **智能关键词提取**：从页面meta标签自动提取关键词
- **缓存机制**：30分钟缓存，减少重复查询
- **进度跟踪**：实时显示查询进度和状态
- **结果导出**：支持多种格式导出查询结果

### ⚙️ 管理功能
- **会话持久化**：历史记录长期保存和查看
- **后台任务系统**：支持大批量查询和失败重试
- **配置管理**：统一的API密钥和系统配置

## 🏗️ 技术架构

```
SEO数据分析平台
├── 数据分析服务 (端口5001)
│   ├── keyword_rank_analyzer.py - 主服务程序
│   ├── Excel智能处理引擎
│   ├── 关键词排名分析算法
│   └── 自动化报告生成
├── 排名查询服务 (端口5002)
│   ├── rank_query_app.py - 主服务程序
│   ├── rank_query_executor.py - 查询执行器
│   ├── 实时排名查询API
│   └── 批量查询处理系统
└── 支撑系统
    ├── session_manager.py - 会话持久化管理
    ├── task_manager.py - 后台任务队列
    ├── config_manager.py - 配置管理系统
    └── start_services.py - 统一服务管理
```

### 技术栈

- **Web框架**：Flask 3.1.0
- **数据处理**：Pandas 2.2.3, NumPy 1.23.5
- **Excel处理**：OpenPyXL 3.1.5
- **网络请求**：Requests 2.32.3, BeautifulSoup4
- **并发处理**：ThreadPoolExecutor, asyncio
- **缓存存储**：Redis 5.2.1

## 📖 使用指南

### 数据分析流程

1. **上传数据**：将SEO数据Excel文件上传到数据分析服务
2. **选择对比**：选择对比期间的数据文件
3. **启动分析**：点击开始分析，系统自动处理
4. **查看结果**：在线查看分析结果或下载报告
5. **优化建议**：根据分析建议进行SEO优化

### 排名查询流程

1. **提取关键词**：从分析结果自动提取目标下降词
2. **开始查询**：启动排名查询，系统自动处理
3. **监控进度**：实时查看查询进度和状态
4. **查看结果**：查询完成后查看排名结果
5. **导出数据**：导出查询结果用于进一步分析

## 🔧 配置说明

### API配置

项目使用站长之家API进行排名查询，需要配置API密钥：

```json
{
  "chinaz_api_key": "your_api_key_here",
  "settings": {
    "auto_retry": true,
    "cache_enabled": true,
    "default_concurrent": 2,
    "max_retries": 2,
    "cache_expire_minutes": 30
  }
}
```

### 服务配置

```json
{
  "data_analysis": {
    "port": 5001,
    "host": "127.0.0.1"
  },
  "rank_query": {
    "port": 5002,
    "host": "127.0.0.1"
  }
}
```

## 📁 项目结构

```
seo-data-analysis-tool/
├── keyword_rank_analyzer.py    # 数据分析主服务
├── rank_query_app.py           # 排名查询主服务
├── session_manager.py          # 会话管理模块
├── task_manager.py             # 任务管理模块
├── config_manager.py           # 配置管理模块
├── start_services.py           # 服务启动脚本
├── templates/                  # HTML模板文件
├── static/                     # 静态资源文件
├── sessions/                   # 会话数据存储
├── analysis_results/           # 分析结果存储
├── uploads/                    # 文件上传目录
└── docs/                       # 文档目录
    ├── IFLOW.md               # 项目上下文文档
    ├── 功能使用说明.md        # 功能使用指南
    ├── 项目介绍.md            # 项目详细介绍
    └── 部署指南.md            # 生产环境部署指南
```

## 🚀 部署指南

### 开发环境

```bash
# 启动开发服务
python start_services.py start

# 检查服务状态
python start_services.py status

# 停止服务
python start_services.py stop
```

### 生产环境

```bash
# 自动化部署
./deploy.sh

# 手动部署
# 1. 上传文件到服务器
# 2. 安装Python环境和依赖
# 3. 配置systemd服务
# 4. 启动服务并验证
```

详细的部署指南请参考：[部署指南.md](docs/部署指南.md)

## 🤝 贡献指南

欢迎提交Issue和Pull Request来改进项目！

### 开发规范

- 遵循PEP 8代码规范
- 添加适当的类型注解
- 编写清晰的文档字符串
- 保持代码简洁和可读性

### 提交流程

1. Fork项目到个人仓库
2. 创建功能分支：`git checkout -b feature/new-feature`
3. 提交更改：`git commit -am 'Add new feature'`
4. 推送分支：`git push origin feature/new-feature`
5. 创建Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 联系方式

- 项目主页：https://github.com/jollyroger89816/seo-data-analysis-tool
- 问题反馈：[GitHub Issues](https://github.com/jollyroger89816/seo-data-analysis-tool/issues)

## 🙏 致谢

感谢所有为这个项目做出贡献的开发者和用户！

---

**注意**：使用本项目需要配置有效的API密钥。请确保遵守相关API服务的使用条款和限制。