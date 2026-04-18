# knowledge-system

统一知识教育系统 — 基于遗忘曲线的智能学习、沉淀与复习闭环，支持飞书知识库同步。

## 这是什么

一个为 AI 编程助手（opencode）设计的技能（skill），让 AI 能像私人教师一样：

- **规划学习路径** — 将复杂主题拆分为可执行的单元
- **即时教学** — 按教案逐步讲解，确认理解后再推进
- **知识沉淀** — 学完后自动整理为结构化知识条目，构建知识树
- **遗忘曲线复习** — 1→2→4→7→15→30 天自动提醒复习
- **每日待办聚合** — 一条命令查看今天该复习什么、有什么待办
- **飞书同步** — 知识自动同步到飞书 Wiki，本地为缓存，飞书为主存储

## 架构概览

```
用户对话 → SKILL.md 路由 → 6 个分支文档
  ├── teach.md    即时教学
  ├── plan.md     学习计划
  ├── digest.md   知识消化沉淀
  ├── review.md   遗忘曲线复习
  ├── memo.md     备忘录
  └── schedule.md 每日待办聚合
         ↓
      kb.py（本地数据读写）→ feishu.py（飞书同步）
         ↓                       ↓
    data/*.md（本地缓存）    飞书 Wiki（主存储）
```

## 学习生命周期

```
plan 制定计划 → teach 逐课教学 → digest 沉淀知识 → review 遗忘曲线复习
                    ↑                                  ↓
                    └──── 复习不通过，重新教学 ←─────────┘
```

知识通过 `parent` 字段自动构建为树形结构，AI 通过 `tree-roots` → `tree-children` 逐层导航，自动发现关联并挂载到正确的父节点下。

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/JuwayD/knowledge-system.git
cd knowledge-system

# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化
python kb.py init

# 4. 检查环境
python scripts/check_env.py
```

### 启用飞书同步（可选）

```bash
npm install -g @larksuite/cli
lark-cli config init --app-id "你的AppID" --app-secret-stdin --brand feishu
lark-cli auth login --recommend
python feishu.py setup   # 首次引导：选择或创建专用知识库
```

启用后，所有知识写入自动同步到飞书，本地不存在时自动从飞书拉取。

详细步骤见 [QUICKSTART.md](QUICKSTART.md)，完整流程图见 [FLOWCHART.md](FLOWCHART.md)。

## 核心命令

### 知识管理

```bash
python kb.py save-knowledge --topic "闭包" --summary "函数与其词法环境的绑定" --content "..."
python kb.py get-knowledge --id "knowledge-xxx"
python kb.py update-knowledge --id "knowledge-xxx" --content "更新内容"
python kb.py list-knowledge --topic "JS" --sort updated_at --desc
```

### 树形导航

```bash
python kb.py tree-roots                    # 列出所有根节点
python kb.py tree-children --parent "JS"   # 列出子节点（含 child_count）
python kb.py tree-summary                  # 整棵树骨架
python kb.py tree-check                    # 健康检查（>8 子节点建议拆分）
```

### 学习计划与教学

```bash
python kb.py save-plan --topic "React" --goal "系统学习 React" --content "..."
python kb.py save-lesson --topic "Hooks" --goal "理解 useState" --content "..."
python kb.py complete-lesson --id "lesson-xxx" --status mastered
```

### 复习调度

```bash
python kb.py due-reviews             # 今日到期复习
python kb.py due-reviews --days 7    # 未来 7 天到期
python kb.py record-review --id "knowledge-xxx"  # 标记已复习
```

### 每日待办

```bash
python kb.py agenda           # 聚合：到期复习 + 待办备忘 + 活跃计划
python kb.py agenda --days 7  # 含未来 7 天到期项
```

### 飞书同步

```bash
python feishu.py setup              # 首次配置
python feishu.py status             # 查看状态
python feishu.py pull --all         # 从飞书拉取全部到本地
python feishu.py sync-tree          # 推送本地知识树到飞书
```

## 数据结构

所有数据存储为 **Markdown + YAML frontmatter**，人类可读，Git 友好。

```markdown
---
id: knowledge-20260418-120000-abc
topic: 闭包
summary: 函数与其词法环境的绑定
tags: [JavaScript, 核心概念]
parent: JavaScript
prerequisites: [作用域]
related: [高阶函数, 柯里化]
learned_at: 2026-04-18T12:00:00
review_count: 2
updated_at: 2026-04-18T12:00:00
created_at: 2026-04-18T12:00:00
---

（知识正文，支持 [[双向链接]]）
```

## 目录结构

```
knowledge-system/
├── SKILL.md          # 主入口，路由规则
├── teach.md          # 教学分支
├── plan.md           # 学习计划分支
├── digest.md         # 知识消化分支
├── review.md         # 复习分支
├── memo.md           # 备忘分支
├── schedule.md       # 每日待办分支
├── kb.py             # 本地数据读写工具
├── feishu.py         # 飞书同步工具
├── data/             # 运行时数据（gitignored）
│   ├── plans/        # 学习计划
│   ├── lessons/      # 课堂记录
│   ├── digests/      # 消化记录
│   ├── knowledge/    # 知识树（核心）
│   └── memos/        # 备忘录
├── scripts/
│   └── check_env.py  # 环境检测
├── QUICKSTART.md     # 冷启动指南
├── FLOWCHART.md      # 完整流程图
├── CHANGELOG.md      # 变更记录
└── requirements.txt  # Python 依赖
```

## 版本历史

| 版本 | 里程碑 |
|---|---|
| v1.0 | 框架雏形 |
| v2.0 | plan/teach 职责分离 |
| v3.0 | Markdown 存储 + 知识关联 |
| v4.0 | 树形自动导航 |
| v5.0 | 遗忘曲线复习调度 |
| v6.0 | Git 版控 + ID 冲突修复 |
| v7.0 | memo 对齐 + 树形健康检查 |
| v7.1 | 飞书集成（lark-cli） |
| v7.2 | 每日待办聚合 |
| v7.3 | 飞书双写 + 增量同步 |
| v8.0 | 飞书主存储架构 + pull + 冷启动 |

## License

MIT
