# 变更记录

## v8.1.0 — 2026-04-22

### 学习生命周期打通

#### 核心变更

**1. complete-lesson 自动联动**

完成授课后自动更新学习计划状态：
- 同步 unit status（已有）+ 更新 `resume_from` 指向下一个 pending unit
- 所有 unit mastered 时，plan 自动标记为 `completed`

**2. complete-digest 回写 plan**

知识沉淀完成后自动回写关联的 plan：
- 如果 digest 有 `source_plan`，将 plan 标记为 `completed`（若尚未完成）

**3. 新增 reset-review 命令**

复习不通过重教后，重置 knowledge 的 `review_count=0` + `learned_at=now`，让遗忘曲线从新开始计算。

**4. 沉淀时机区分**

- 独立教学（无 plan_id）：lesson 完成后询问用户是否沉淀
- plan 内教学（有 plan_id）：等 plan 全部 unit 完成后统一沉淀

**5. 查找优先原则**

SKILL.md 强制要求新增：创建任何条目前必须先 search/list 检查已有，避免重复创建。

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `kb.py` | `complete-lesson` 增加 resume_from + plan 自动 completed；`complete-digest` 增加回写 plan；新增 `reset-review` 命令 |
| `SKILL.md` | 强制要求新增查找优先规则；CLI 加入 `reset-review` |
| `teach.md` | 区分独立教学 vs plan 内教学的沉淀时机 |
| `plan.md` | 明确 plan completed 后主动引导沉淀 |
| `review.md` | 复习不通过重教后调用 `reset-review`；补充追溯链说明 |
| `FLOWCHART.md` | 学习生命周期图、复习调度图、数据流图同步更新 |
| `README.md` | 学习生命周期描述更新；加入 `reset-review` 命令 |

---

## v8.0.0 — 2026-04-18

### 飞书主存储架构重构

#### 核心变更

**1. 飞书为主存储，本地为缓存**

- 移除 `FEISHU_SYNC` 环境变量，改为自动检测 `data/feishu-config.json` 存在即启用双写
- `_check_feishu_sync()` 惰性检测，首次调用后缓存结果

**2. 新增 `setup` 命令（feishu.py）**

首次运行时引导用户选择或创建专用知识库：
- 列出已有知识库供选择
- 支持一键新建"知识系统"专用知识库
- 配置自动保存

**3. 新增 `pull` 命令（feishu.py）**

从飞书拉取节点到本地缓存：
- `pull --all` — 拉取知识库全部节点
- `pull --node-token <token>` — 拉取单个节点
- 自动解析飞书文档块为 Markdown
- 自动建立 parent 映射关系

**4. `get-knowledge` 自动拉取（kb.py）**

本地不存在时自动从飞书拉取：
- 通过 mapping 查找 node_token
- 调用 `feishu.py pull --node-token` 拉取
- 拉取成功后正常返回数据

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `feishu.py` | 新增 `setup`、`pull` 命令；新增文档解析、知识文件读写函数 |
| `kb.py` | 移除环境变量检测，改为自动检测；`get-knowledge` 增加 fallback 拉取 |
| `SKILL.md` | 飞书集成章节重构为主存储架构说明 |

---

## v7.3.0 — 2026-04-18

### 飞书双写模式 + 增量同步 + 各子文档触发点

#### 核心变更

**1. 飞书双写（FEISHU_SYNC=1）**

`kb.py` 新增 `_try_feishu_sync()` 函数，在以下三个写入点自动触发飞书同步：
- `complete-digest` — knowledge 入库后
- `save-knowledge` — 创建/更新知识条目后
- `update-knowledge` — 更新知识内容后

设置 `FEISHU_SYNC=1` 环境变量启用，未设置则不影响现有行为。

**2. 增量同步（feishu.py）**

新增 `_sync_entry()` 统一处理创建/更新逻辑：
- 新条目 → 创建飞书文档节点
- 已有条目 `updated_at > synced_at` → `docs +update --mode overwrite` 更新
- 无变化 → 跳过
- 新增 `_update_doc()` 封装更新调用
- mapping 中增加 `synced_at` 字段追踪同步时间

**3. 各子文档加入飞书同步触发点**

| 文档 | 触发时机 |
|---|---|
| `digest.md` | `complete-digest` 后 `sync --id` |
| `teach.md` | 沉淀知识后由 digest 负责 |
| `plan.md` | 整个计划完成后 `sync-tree` |
| `review.md` | 更新 knowledge 内容后 `sync --id` |
| `schedule.md` | 每日待办处理后 `sync-tree` |

---

## v7.2.0 — 2026-04-18

### 每日待办聚合（schedule.md + agenda 命令）

#### 核心变更

**1. 新增 `schedule.md` 分支文档**

每日待办管家，当用户问"今天该做什么"时触发：
- 按优先级排列：逾期复习 > 高优备忘 > 活跃计划 > 即将到期复习 > 普通备忘
- 引导用户逐项处理，完成后路由到对应分支
- 包含输出格式模板

**2. 新增 `agenda` 命令（kb.py）**

一次调用聚合三类待办数据：
- `reviews_due`：到期/即将到期的复习条目（含逾期天数）
- `memos_open`：所有 status=open 的备忘（按优先级排序）
- `plans_active`：所有 status=active 的学习计划（含 pending/total 单元数）
- 支持 `--days <n>` 控制复习提前天数（默认 3）

**3. 路由规则新增第 6 条**

用户问"今天该做什么" → 读取 `schedule.md`

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `schedule.md` | 新增：每日待办分支文档 |
| `kb.py` | 新增 `cmd_agenda`、`agenda` argparse 注册、HELP_TEXT |
| `SKILL.md` | 路由规则新增第 6 条；分支文档列表加入 schedule.md；CLI 加入 agenda |

---

## v7.1.0 — 2026-04-18

### 飞书集成：基于 lark-cli 重写 + 端到端验证通过

#### 核心变更

**`feishu.py` 完全重写，底层从手动调飞书 REST API 改为委托 lark-cli**

- 移除 `requests` 依赖和手写的 Markdown→飞书文档块转换（约 200 行）
- 改用 `lark-cli docs +create --markdown` 和 `lark-cli wiki +node-create` 子进程调用
- 子节点创建：先 `wiki +node-create` 建节点，再 `docs +update --mode overwrite` 写内容
- 新增 `spaces` 命令：列出可用知识库
- 新增 `config --space-id` 命令：设置目标知识库
- 认证完全交给 lark-cli 管理（`lark-cli config init` + `lark-cli auth login`）
- 端到端验证通过：根节点 + 子节点均成功创建并写入 Markdown 内容

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `feishu.py` | 全面重写：移除 requests/API 手动调用，改为 lark-cli 子进程调用 |
| `SKILL.md` | 飞书集成章节更新为 lark-cli 方案 |

---

## v7.0.0 — 2026-04-17

### memo.md 对齐 + 树形健康检查 + 飞书集成

#### 核心变更

**1. memo.md 对齐到当前架构**

- 补充 Markdown 存储结构示例
- 补全 CLI 命令（`get-memo`、`--deadline` 等）
- 增加备忘生命周期（创建→跟踪→完成/引流）
- 增加与知识库双向链接关联说明
- 增加引流到 review.md 的路由

**2. 树形健康检查与拆分建议**

- 新增 `tree-check [--threshold <n>]` 命令：扫描全树，报告子节点过多的父节点、空根节点等
- `tree-children` 增强：每个子节点增加 `child_count`，超过阈值时输出 `_warnings`
- 新增 `_build_child_count_map()` 辅助函数

**3. 飞书知识库集成**

新增 `feishu.py` 独立脚本，负责将本地知识库同步到飞书 Wiki：
- `auth` — 配置飞书应用凭证和目标知识库
- `status` — 查看认证状态和已映射节点
- `sync` — 同步指定/全部知识条目到飞书
- `sync-tree` — 按树形结构同步（先根节点后子节点）
- 支持 Markdown → 飞书文档块转换（标题、段落、列表、代码块、表格）
- 支持 `--dry-run` 预览模式
- 节点映射存储在 `data/feishu-config.json`（gitignored）

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `memo.md` | 全面重写：存储结构、生命周期、完整 CLI 示例 |
| `kb.py` | 新增 `tree-check` 命令、`_build_child_count_map`；`tree-children` 增加 `child_count` 和 `_warnings` |
| `SKILL.md` | 新增"飞书集成"章节；树形健康检查说明；CLI 加入 `tree-check` |
| `digest.md` | 知识关联流程新增第 7 步"树形健康检查" |
| `feishu.py` | 新增：飞书 Wiki 同步脚本 |

---

## v6.0.0 — 2026-04-17

### 树形知识导航 + Git 版控

#### 核心变更

**1. 知识库改为树形结构，AI 通过逐层读取摘要自动发现关联**

```
JavaScript
├── 作用域
│   ├── 闭包
│   └── 变量提升
├── 函数式编程
│   ├── 高阶函数
│   └── 柯里化
React
├── Hooks
│   ├── useState
│   └── useEffect
```

关联发现流程（替换原 search 模式）：
1. `tree-roots` → 读所有根节点摘要
2. `tree-children --parent "xxx"` → 逐层下探
3. 找到最精确 parent → 同层兄弟 → related
4. 不需要搜索，不需要猜关键词

**2. 新增命令**

| 命令 | 作用 |
|---|---|
| `tree-roots` | 列出所有根节点（parent 为空）的 id + topic + summary + child_count |
| `tree-children --parent "topic"` | 列出指定父节点的直接子节点摘要 |
| `tree-summary` | 返回整棵树的骨架（嵌套 JSON） |

**3. 修复 ID 冲突 bug**

`generate_id` 加入毫秒后缀，同一秒内创建的条目不再覆盖。

**4. Git 版控**

- `git init` + `.gitignore`（排除 data/、__pycache__/）
- `v5.0.0` tag 标记基线
- 树形导航在 `tree-nav` 分支开发

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `kb.py` | 新增 `tree-roots`、`tree-children`、`tree-summary` 命令；修复 `generate_id` 毫秒冲突 |
| `digest.md` | 关联发现流程从 search 模式改为树形导航模式 |
| `SKILL.md` | 知识关联原则改为树形导航；CLI 加入 tree 命令 |

---

## v5.0.0 — 2026-04-17

### 遗忘曲线复习调度

#### 核心变更

**1. 艾宾浩斯遗忘曲线自动计算复习时间**

复习间隔：学完后 → 第1天 → 第2天 → 第4天 → 第7天 → 第15天 → 第30天

每个 knowledge 条目自动记录：
- `learned_at`：首次学习时间（`complete-digest` / `save-knowledge` 时自动设置）
- `review_count`：已复习次数
- `last_reviewed_at`：上次复习时间

**2. 新增命令**

| 命令 | 作用 |
|---|---|
| `due-reviews [--days n]` | 查询到期/即将到期的复习条目，按逾期天数排序 |
| `record-review --id xxx` | 复习通过后调用，review_count +1，下次间隔自动延长 |

**3. 复习逻辑**

- 记住了 → `record-review`，间隔自动延长
- 忘了 → 路由到 teach 重教，不更新 review_count
- 复习 6 轮后（间隔到达 30 天）不再出现在到期列表

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `kb.py` | 新增 `REVIEW_INTERVALS`、`next_review_date`、`cmd_due_reviews`、`cmd_record_review`；knowledge 自动记录 `learned_at` 和 `review_count` |
| `review.md` | 重写，加入遗忘曲线调度主线、结果处理逻辑、辅助脚本 |
| `SKILL.md` | 路由规则加入"今天该复习什么"；CLI 加入 due-reviews / record-review |

---

## v4.0.0 — 2026-04-17

### 自动知识关联 + complete-lesson 去掉自动 digest

#### 核心变更

**1. 自动知识关联（AI 自动发现，不需要用户提示）**

- 创建新 knowledge 时，AI 必须 `search --kind knowledge` 查找已有条目
- 自动分析 parent / prerequisites / related 关系并填入
- 正文用 `[[主题]]` 双向链接标注关联
- 新条目入库后，反向更新被引用条目的 related 字段
- 新增 `backlinks --query "主题"` 命令，扫描所有 `[[xxx]]` 生成反向链接报告

**2. complete-lesson 去掉自动 digest 草稿**

- lesson 完成后不再自动创建 digest 草稿
- AI 判断是否需要沉淀，需要时直接 `complete-digest` 一步到位
- 去掉 digest 的 `source_lesson` 自动填充

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `kb.py` | 新增 `backlinks` 命令；`complete-lesson` 去掉自动 digest 创建；新增 `import re` 用于 `[[xxx]]` 解析 |
| `SKILL.md` | 新增"知识关联原则"章节；CLI 加入 backlinks 和反向更新示例 |
| `digest.md` | 新增"自动知识关联"强制执行章节，含 5 步操作流程 |
| `teach.md` | 教学完成后改为 AI 主动询问是否沉淀，不再自动创建草稿 |

---

## v3.0.0 — 2026-04-16

### 存储格式全面 Markdown 化 + 知识图谱关联

#### 核心变更

**1. 全部存储从 JSON 改为 Markdown + YAML Frontmatter**

所有 `data/` 下的文件从 `.json` 改为 `.md`，结构为：

```markdown
---
id: xxx
topic: ...
status: ...
（YAML 元数据）
---

（Markdown 正文）
```

好处：人类可直接打开阅读，飞书可直接推送，AI 读写同样自然。

**2. 知识库新增关联字段**

knowledge 条目新增：
- `parent`：所属大主题
- `prerequisites`：前置知识 ID 列表
- `related`：相关知识 ID 列表

正文中支持 `[[双链]]` 语法标注知识关联。

**3. 依赖 PyYAML**

`kb.py` 新增 `import yaml` 用于 YAML frontmatter 解析。

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `kb.py` | `write_record`/`read_record` 改为 markdown 读写；所有 `.json` → `.md`；knowledge 新增 `--parent`/`--prerequisites`/`--related`；`complete-digest` 支持关联字段 |
| `SKILL.md` | 示例改为 markdown 格式；新增 knowledge 结构说明；CLI 加入关联参数 |
| `plan.md` | 学习计划结构示例改为 markdown 格式 |
| `teach.md` | 授课记录结构示例改为 markdown 格式 |
| `digest.md` | 消化记录结构示例改为 markdown 格式 |

#### 存储文件示例

```markdown
# data/plans/plan-xxx.md
---
id: plan-xxx
topic: React
units:
  - name: Basics
    status: mastered
---
（学习计划正文）

# data/lessons/lesson-xxx.md
---
id: lesson-xxx
plan_id: plan-xxx
unit: Basics
mastered:
  - 组件定义
---
（教案内容）

# data/knowledge/knowledge-xxx.md
---
id: knowledge-xxx
topic: React Hooks
parent: react
related:
  - hooks
---
# React Hooks
...核心概念...
## 知识关联
- 前置：[[作用域]]
- 相关：[[高阶函数]]
```

---

## v2.0.0 — 2026-04-16

### 架构重构：plan 与 teach 职责分离 + 新增 lesson / digest 存储模块

#### 核心变更

**1. plan（学习计划）与 teach（授课记录）彻底分离**

| | plan | teach |
|---|---|---|
| 职责 | 规划学习路径、阶段、模块 | 真正授课，记录单次教学内容 |
| 产出 | `data/plans/*.json` | `data/lessons/*.json` |
| 关联 | units 列表 | `plan_id` + `unit` 指向 plan 的某个 unit |

**2. 新增 lesson 存储模块**

- `save-lesson`：创建授课记录，可选关联 plan unit
- `update-lesson`：更新 mastered / weak / next
- `complete-lesson`：关闭授课记录，自动同步关联的 plan unit status
- `list-lessons`：按 plan-id / status / topic 筛选
- `get-lesson` / `search --kind lessons`

**3. 新增 digest 存储模块**

- `save-digest`：创建消化记录，可选关联 `source-plan`
- `update-digest`：更新 confirmed / pending 列表
- `complete-digest`：一步完成——关闭消化记录 + 自动生成 knowledge 条目（含 `source_digest` 回溯）
- `list-digests` / `get-digest` / `search --kind digests`

**4. plan 结构扩展**

新增字段：
- `basis`：搜索得到的权威依据与版本信息
- `baseline`：用户当前基础与风险盲区
- `units`：结构化分段列表（`[{name, goal, status}]`）
- `resume_from`：下次继续的位置
- `adjustments`：动态调整记录

新增命令：
- `update-units`：批量更新 units（通过 stdin 传入 JSON）
- `set-resume`：快捷设置下次继续位置

**5. 自动同步机制**

- `record-progress` / `upsert-progress`：自动同步对应 unit 的 status
- `complete-lesson`：自动同步关联 plan unit status

#### 文件变更清单

| 文件 | 变更 |
|---|---|
| `kb.py` | 新增 lessons 模块（save/get/list/update/complete-lesson）、digest 模块、update-units、set-resume、_sync_unit_status 自动同步 |
| `SKILL.md` | 教案要求改为 plan/lesson 双结构示例，CLI 命令速查更新 |
| `plan.md` | 聚焦学习规划职责，去掉授课内容，使用 save-plan/update-units |
| `teach.md` | 改用 lesson 存储，关联 plan，使用 save-lesson/update-lesson/complete-lesson |
| `review.md` | 适配 lesson，复习后路由到 teach |
| `digest.md` | 新增消化记录落地结构，使用 save-digest/complete-digest |
| `workflow.md` | 已删除（语义与 SKILL.md 重复） |

#### 数据目录结构

```
data/
├── plans/       学习计划（plan.md 产出）
├── lessons/     授课记录（teach.md 产出）
├── digests/     消化记录（digest.md 产出）
├── knowledge/   知识库（complete-digest 自动生成）
└── memos/       备忘录（memo.md 产出）
```

#### 分支间路由

```
plan ──开始上课──► teach (创建 lesson, plan_id + unit)
plan ──需要巩固──► review
plan ──全部完成──► digest (source_plan 关联)

teach ──独立完成──► digest
teach ──系统学习中──► 回到 plan (unit status 已自动同步)

review ──通过──► teach (继续下一课)
review ──不通过──► teach (重教)

digest ──完成──► knowledge (complete-digest 自动生成)

memo ──展开──► plan / teach / digest
```

---

## v1.0.0 — 2026-04-12

### 初始版本

- 基础技能框架：SKILL.md + plan/teach/review/digest/memo 五分支
- kb.py：plans/knowledge/memos 三类存储 + search
- workflow.md 公共流程文档
