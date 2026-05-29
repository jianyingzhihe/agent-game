# agent-game

一个让不同大模型彼此对战的多游戏实验场。

当前代码主体位于 `ai-game-platform/` 目录，支持把不同 provider、不同模型名的 AI 玩家混合进同一局游戏里对战、记录日志和回放。

## 当前支持的游戏

- `werewolf`：狼人杀
- `avalon`：阿瓦隆
- `codenames`：代号
- `texas_holdem`：德州扑克
- `doudizhu`：斗地主
- `sanguosha`：三国杀

## 项目结构

```text
agent-game/
├─ ai-game-platform/          # 主项目
│  ├─ core/                   # 通用引擎、模型封装、日志等
│  ├─ games/                  # 每个游戏独立目录
│  ├─ sgs_viewer/             # 三国杀 pygame 回放查看器
│  ├─ config/                 # 模型配置
│  ├─ data/                   # 图标等静态资源
│  └─ main.py                 # 统一启动入口
└─ README.md
```

## 快速开始

### 1. 安装依赖

```bash
cd ai-game-platform
pip install -r requirements.txt
```

### 2. 配置环境变量

在 `ai-game-platform/.env` 中填入你自己的模型 API Key。

常见示例：

```env
DEEPSEEK_KEY=sk-xxx
OPENAI_KEY=sk-xxx
GAME_TYPE=doudizhu
MAX_ROUNDS=50
VERBOSE=true
```

如果你使用项目里的多模型配置，也可以结合 `config/models.yaml` 或其他 provider 配置一起使用。

### 3. 启动游戏

```bash
python main.py doudizhu
python main.py sanguosha
python main.py werewolf
```

查看当前可用模型：

```bash
python main.py models
```

## 查看日志与回放

- 运行日志默认输出到 `ai-game-platform/logs/`
- 三国杀回放查看器：

```bash
python -m sgs_viewer logs/sanguosha/<session>/game.jsonl
```

## 说明

- 仓库根目录的 `.gitignore` 主要忽略本地开发环境目录
- 项目目录 `ai-game-platform/.gitignore` 负责忽略运行日志、缓存和临时截图
- 当前远程仓库适合作为项目代码主仓，后续可以继续在 `games/` 下扩展新游戏
