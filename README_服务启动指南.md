# SEO数据分析与排名查询服务启动指南

## 概述

本项目包含两个主要服务：
- **数据分析服务** (端口5001)：关键词排名分析工具
- **排名查询服务** (端口5002)：独立的排名查询工具

我们提供了两种方式来启动这些服务：Python脚本和Shell脚本。

## 🚀 快速启动

### 方式一：Shell脚本（推荐）

```bash
# 启动所有服务
./start_services.sh

# 或者明确指定启动命令
./start_services.sh start
```

### 方式二：Python脚本

```bash
# 启动所有服务
python start_services.py start

# 或者直接运行（默认启动）
python start_services.py
```

## 📋 命令说明

### Shell脚本命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `start` | 启动所有服务（默认） | `./start_services.sh start` |
| `stop` | 停止所有服务 | `./start_services.sh stop` |
| `restart` | 重启所有服务 | `./start_services.sh restart` |
| `status` | 检查服务状态 | `./start_services.sh status` |
| `help` | 显示帮助信息 | `./start_services.sh help` |

### Python脚本命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `start` | 启动所有服务（默认） | `python start_services.py start` |
| `stop` | 停止所有服务 | `python start_services.py stop` |
| `status` | 检查服务状态 | `python start_services.py status` |
| `help` | 显示帮助信息 | `python start_services.py help` |

## 🔧 服务详情

### 数据分析服务 (端口5001)

- **URL**: http://127.0.0.1:5001
- **功能**:
  - 关键词排名数据分析
  - 年度对比分析
  - Excel报告生成
  - 历史报告在线查看
  - Session持久化

### 排名查询服务 (端口5002)

- **URL**: http://127.0.0.1:5002
- **功能**:
  - 实时关键词排名查询
  - 批量URL排名检测
  - API密钥管理
  - 查询进度跟踪
  - 结果导出

## 🛠️ 使用示例

### 1. 启动服务

```bash
# 使用Shell脚本启动（推荐）
./start_services.sh

# 输出示例：
# [2025-07-11 17:52:45] === 启动所有服务 ===
# [2025-07-11 17:52:45] 启动数据分析服务...
# [2025-07-11 17:52:47] 数据分析服务启动成功！
# [2025-07-11 17:52:47] 启动排名查询服务...
# [2025-07-11 17:52:49] 排名查询服务启动成功！
# [2025-07-11 17:52:49] ✓ 成功启动 2/2 个服务
```

### 2. 检查服务状态

```bash
./start_services.sh status

# 输出示例：
# [2025-07-11 17:52:58] === 检查服务状态 ===
# [2025-07-11 17:52:58] ✓ 数据分析服务: 正常运行
# [2025-07-11 17:52:58] ✓ 排名查询服务: 正常运行
```

### 3. 停止服务

```bash
./start_services.sh stop

# 输出示例：
# [2025-07-11 17:53:15] === 停止所有服务 ===
# [2025-07-11 17:53:15] 停止 数据分析服务 (PID: 12345)...
# [2025-07-11 17:53:17] ✓ 数据分析服务 已停止
# [2025-07-11 17:53:17] 停止 排名查询服务 (PID: 12346)...
# [2025-07-11 17:53:19] ✓ 排名查询服务 已停止
```

### 4. 重启服务

```bash
./start_services.sh restart
```

## 📁 文件说明

| 文件 | 类型 | 描述 |
|------|------|------|
| `start_services.py` | Python脚本 | 跨平台启动脚本，支持监控和自动重启 |
| `start_services.sh` | Shell脚本 | Unix/Linux系统的轻量级启动脚本 |
| `keyword_rank_analyzer.py` | 主服务 | 数据分析服务主程序 |
| `rank_query_app.py` | 主服务 | 排名查询服务主程序 |
| `session_manager.py` | 模块 | Session持久化管理模块 |

## 📊 日志文件

启动脚本会自动生成日志文件：

| 日志文件 | 内容 |
|----------|------|
| `data_analysis.log` | 数据分析服务的运行日志 |
| `rank_query.log` | 排名查询服务的运行日志 |
| `data_analysis.pid` | 数据分析服务的进程ID文件 |
| `rank_query.pid` | 排名查询服务的进程ID文件 |

## ⚡ 高级功能

### Python脚本的额外功能

- **自动监控**：监控服务状态，异常退出时自动重启
- **健康检查**：定期检查服务响应，确保服务正常运行
- **错误处理**：完善的错误处理和日志记录
- **信号处理**：优雅地处理系统信号（Ctrl+C等）

### Shell脚本的优势

- **轻量级**：占用系统资源少
- **快速启动**：启动速度快
- **简单易用**：命令简洁明了
- **彩色输出**：友好的终端界面

## 🔍 故障排除

### 常见问题

1. **端口被占用**
   ```bash
   # 检查端口占用情况
   lsof -i :5001
   lsof -i :5002
   
   # 停止占用端口的进程
   kill -9 <PID>
   ```

2. **服务启动失败**
   ```bash
   # 检查日志文件
   tail -f data_analysis.log
   tail -f rank_query.log
   
   # 检查脚本文件是否存在
   ls -la keyword_rank_analyzer.py rank_query_app.py
   ```

3. **权限问题**
   ```bash
   # 确保脚本有执行权限
   chmod +x start_services.sh
   ```

### 手动启动服务

如果启动脚本出现问题，您也可以手动启动服务：

```bash
# 手动启动数据分析服务
python keyword_rank_analyzer.py &

# 手动启动排名查询服务
python rank_query_app.py &
```

## 📝 注意事项

1. **Python环境**：确保使用正确的Python环境（建议使用虚拟环境）
2. **依赖包**：确保所有必需的Python包已安装
3. **网络端口**：确保端口5001和5002没有被其他程序占用
4. **系统权限**：确保有足够的权限创建进程和写入日志文件

## 🎯 推荐使用方式

1. **开发环境**：使用Shell脚本 `./start_services.sh`，快速启动和停止
2. **生产环境**：使用Python脚本 `python start_services.py start`，更稳定的监控
3. **调试模式**：手动启动单个服务，便于查看详细输出

## 🔗 访问地址

启动成功后，您可以通过以下地址访问服务：

- **数据分析工具**: http://127.0.0.1:5001
- **排名查询工具**: http://127.0.0.1:5002

---

**提示**: 如有任何问题，请查看日志文件或使用 `status` 命令检查服务状态。 