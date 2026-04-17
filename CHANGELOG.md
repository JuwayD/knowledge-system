# 变更记录

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
