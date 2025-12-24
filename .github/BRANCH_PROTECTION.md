# 分支保护配置指南

## 🔒 推荐的分支保护设置

### 主分支（main/master）保护规则

在GitHub仓库设置中配置以下规则：

#### 1. 基础保护设置
```
✅ Require pull request reviews before merging
   ✅ Require approvals from 1 reviewer
   ✅ Dismiss stale PR approvals when new commits are pushed
   ✅ Require review from CODEOWNERS
   ✅ Limit who can dismiss pull request reviews: @jollyroger89816

✅ Do not allow bypassing the above settings
✅ Require status checks to pass before merging (如果有CI/CD)
✅ Require branches to be up to date before merging
✅ Require conversation resolution before merging
```

#### 2. 限制推送权限
```
✅ Restrict who can push to matching branches
   - 只有 @jellyroger89816 可以推送

✅ Allow force pushes: ❌ 禁用
✅ Allow deletions: ❌ 禁用
```

### 其他分支规则

#### 开发分支（develop/*）
```
✅ Require pull request reviews before merging
✅ Require approvals from 1 reviewer
❌ 不限制推送权限（允许直接推送）
```

#### 功能分支（feature/*）
```
❌ 无保护规则（自由开发）
```

## 🛡️ 仓库级别安全设置

### 1. 协作者管理
- **仓库管理员**: @jellyroger89816
- **协作者**: 仅添加必要的贡献者
- **审查权限**: 只有管理员可以合并PR

### 2. Issue和PR管理
- **Issue权限**: 允许所有人创建
- **PR权限**: 允许所有人创建
- **合并权限**: 仅管理员

### 3. 分支权限
- **创建分支**: 允许协作者创建
- **删除分支**: 仅管理员可以删除主分支
- **强制推送**: 禁止在主分支强制推送

## ⚙️ 配置步骤

### 在GitHub上设置分支保护：

1. **进入仓库设置**
   - 访问仓库页面
   - 点击 "Settings" 标签

2. **进入分支设置**
   - 左侧菜单点击 "Branches"
   - 点击 "Add rule" 按钮

3. **配置主分支保护**
   ```
   Branch name pattern: main (或 master)
   
   ✅ Require pull request reviews before merging
      ✅ Number of required reviewers: 1
      ✅ Dismiss stale PR approvals when new commits are pushed
      ✅ Require review from CODEOWNERS
      ✅ Limit who can dismiss pull request reviews: @jellyroger89816
   
   ✅ Do not allow bypassing the above settings
   
   ✅ Require status checks to pass before merging (可选)
      - 如果有CI/CD流水线，选择必要的检查
   
   ✅ Require branches to be up to date before merging
   ✅ Require conversation resolution before merging
   
   ✅ Restrict who can push to matching branches
      - 添加 @jellyroger89816
   
   ✅ Allow force pushes: ❌ (取消勾选)
   ✅ Allow deletions: ❌ (取消勾选)
   ```

4. **保存设置**
   - 点击 "Create" 或 "Save changes"
   - 测试配置是否生效

## 🔍 验证配置

### 测试分支保护：
1. 尝试直接推送到主分支（应该被拒绝）
2. 创建Pull Request（应该需要审查）
3. 尝试合并未审查的PR（应该被拒绝）
4. 审查通过后合并（应该成功）

### 检查CODEOWNERS：
1. 修改文件并创建PR
2. 检查是否自动请求 @jellyroger89816 审查
3. 验证其他人无法批准PR

## 📋 维护建议

### 定期检查：
- 每月审查协作者权限
- 检查分支保护规则是否有效
- 更新CODEOWNERS文件（如有需要）

### 安全最佳实践：
- 使用强密码和2FA认证
- 定期轮换个人访问令牌
- 监控仓库活动日志
- 备份重要配置和代码

---

*配置完成后，项目将具有完善的分支保护机制，确保代码安全和质量。*