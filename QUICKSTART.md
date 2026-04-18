# knowledge-system 冷启动指南

全新电脑上从零开始使用本技能。

## 前置依赖

| 依赖 | 用途 | 安装方式 |
|---|---|---|
| Python 3.8+ | kb.py / feishu.py 运行时 | [python.org](https://python.org) 或 `winget install Python.Python.3` |
| PyYAML | Markdown + YAML frontmatter 读写 | `pip install pyyaml` |
| Node.js 18+ | lark-cli 运行时 | [nodejs.org](https://nodejs.org) 或 `winget install OpenJS.NodeJS` |
| Git | 版本控制 | [git-scm.com](https://git-scm.com) 或 `winget install Git.Git` |
| lark-cli | 飞书知识库操作 | `npm install -g @larksuite/cli` |
| opencode | AI 编程助手（承载技能） | 见 [opencode.ai](https://opencode.ai) |

## 快速启动（5 步）

```bash
# 1. 克隆技能
git clone https://github.com/JuwayD/knowledge-system.git
cd knowledge-system

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 初始化本地数据目录
python kb.py init

# 4. 配置飞书（如需飞书同步）
npm install -g @larksuite/cli
lark-cli config init --app-id "你的AppID" --app-secret-stdin --brand feishu
lark-cli auth login --recommend
python feishu.py setup

# 5. 将技能目录放入 opencode skills 路径
#    Windows: %APPDATA%\opencode\skills\knowledge-system\
#    macOS:   ~/.config/opencode/skills/knowledge-system/
```

## 不需要飞书

如果只使用本地模式（不连接飞书），只需前 3 步。所有知识存储在本地 `data/` 目录，通过 Git 版控。

## 验证

```bash
python kb.py --help          # 查看所有命令
python feishu.py status      # 检查飞书连接（可选）
python kb.py agenda          # 查看今日待办
```
