# AI Game Platform — Multi-Game AI Arena

不同 AI 模型互相对战。支持四款游戏，统一接口一键切换模型。

## 游戏列表

| 游戏 | GAME_TYPE | 类型 | 玩家数 |
|------|-----------|------|--------|
| 狼人杀 (Werewolf) | `werewolf` | 隐藏角色 / 淘汰制 | 5-10 |
| 阿瓦隆 (Avalon) | `avalon` | 隐藏角色 / 无淘汰 | 5-8 |
| Codenames | `codenames` | 词语联想 / 团队 | 4 |
| 德州扑克 (Texas Hold'em) | `texas_holdem` | 扑克博弈 | 2-6 |

## 快速开始

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```env
DEEPSEEK_KEY=sk-your-deepseek-key
DASHSCOPE_KEY=sk-your-dashscope-key

# DashScope 一个 key 拉多个模型: Qwen + Kimi + GLM 混战
PLAYER_CONFIG=deepseek:2,dashscope:qwen-max:2,dashscope:kimi-k2-thinking:2,dashscope:glm-5.1:2
```

所有支持的配置项见 `.env.example` 中的注释，包括：
- 自定义 `base_url`（`DEEPSEEK_BASE_URL`, `OPENAI_BASE_URL` 等）
- 自定义模型名（`DEEPSEEK_MODEL`, `OPENAI_MODEL` 等）
- 温度/最大 token 等参数

### 3. 选择游戏 & 运行

在 `.env` 里切换 `GAME_TYPE`：

```env
GAME_TYPE=avalon        # 阿瓦隆
# GAME_TYPE=werewolf    # 狼人杀
# GAME_TYPE=codenames   # Codenames
# GAME_TYPE=texas_holdem # 德州扑克
```

```bash
python main.py
```

## 项目结构

```
ai-game-platform/
├── core/                       # 可复用基础设施（所有游戏共用）
│   ├── models/                 # 统一模型接口
│   │   ├── base.py             #   ModelInterface 抽象基类
│   │   ├── openai_compat.py    #   OpenAI 兼容接口（GPT/DeepSeek/Qwen/智谱...）
│   │   ├── gemini_model.py     #   Gemini 专用接口
│   │   └── factory.py          #   create_model("deepseek", key="...")
│   ├── player.py               # Player 基类（模型 + 人格 + 记忆）
│   ├── engine.py               # GameEngine 基类（回合管理、胜负判定）
│   └── utils.py                # 通用工具（文本解析、投票统计、颜色输出）
│
├── games/                      # 游戏模块（每个游戏独立目录）
│   └── werewolf/               # 狼人杀
│       ├── roles.py            #   角色定义（狼人/村民/预言家/女巫/猎人）
│       ├── prompts.py          #   Prompt 模板
│       ├── player.py           #   WerewolfPlayer
│       └── engine.py           #   完整游戏引擎
│
├── .env.example                # 环境变量模板（复制为 .env 使用）
├── config.py                   # Python 编程式配置（高级用法）
├── main.py                     # 入口
└── requirements.txt
```

## 统一模型接口

```python
from core.models.factory import create_model

# 一行切换 provider，接口完全一致
model = create_model("deepseek", api_key="sk-xxx")
model = create_model("openai",   api_key="sk-xxx")
model = create_model("gemini",   api_key="xxx")
model = create_model("qwen",     api_key="sk-xxx")
model = create_model("zhipu",    api_key="xxx")

# 自定义 base_url
model = create_model("qwen", api_key="sk-xxx",
                     base_url="https://your-proxy.com/v1")

# 统一调用
response = model.chat([
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello!"}
])
```

## 编程式配置（Python 代码控制）

如果不想用 `.env`，可以在代码中直接配置：

```python
from config import build_from_dict
from games.werewolf.engine import WerewolfEngine

players = build_from_dict({
    "deepseek": {"key": "sk-xxx", "model": "deepseek-chat", "count": 2},
    "openai":   {"key": "sk-xxx", "model": "gpt-4o",       "count": 2},
    "gemini":   {"key": "xxx",    "model": "gemini-2.0-flash", "count": 1},
    "qwen":     {"key": "sk-xxx", "model": "qwen-max",     "count": 2,
                 "base_url": "https://custom.endpoint.com/v1"},
})

engine = WerewolfEngine(players)
engine.run()
```

## 游戏规则

7 人标准局角色分配：狼人×2、预言家×1、女巫×1、猎人×1、村民×2

- **村民阵营胜**：所有狼人被消灭
- **狼人阵营胜**：狼人数 ≥ 村民数

## 添加新游戏

在 `games/` 下新建目录，实现四个文件即可：

```
games/avalon/
├── roles.py       # 角色定义
├── prompts.py     # Prompt 模板
├── player.py      # 游戏专用 Player 子类
└── engine.py      # 继承 core.engine.GameEngine
```

`core/` 中的模型接口和基础类完全复用，无需修改。

## 支持的 Provider

| provider | 默认模型 | 说明 |
|----------|----------|------|
| `deepseek` | deepseek-chat | DeepSeek |
| `openai` | gpt-4o | OpenAI GPT |
| `gemini` | gemini-2.0-flash | Google Gemini |
| `qwen` | qwen-max | 阿里通义千问 |
| `zhipu` | glm-4-flash | 智谱 GLM |
| `moonshot` | moonshot-v1-8k | Moonshot Kimi |
| `siliconflow` | DeepSeek-V3 | SiliconFlow |
| `groq` | llama-3.1-70b | Groq 高速推理 |
| `doubao` | doubao-pro-32k | 字节豆包 (火山引擎) |
| `dashscope` | qwen-max | 阿里云百炼 — Qwen/Kimi/GLM/MiniMax 统一网关 |
| `xai` | grok-2 | xAI Grok |
| `openrouter` | openai/gpt-4o | OpenRouter 网关 |

### DashScope 多模型玩法

`dashscope` 一个 key 可以拉多个模型，通过 `PLAYER_CONFIG` 的 `provider:model:count` 格式指定：

```env
DASHSCOPE_KEY=sk-your-key
PLAYER_CONFIG=dashscope:qwen-max:2,dashscope:kimi-k2-thinking:2,dashscope:glm-5.1:2,deepseek:2
```

这会产生 8 个玩家：2 个 Qwen + 2 个 Kimi + 2 个 GLM + 2 个 DeepSeek，只用两个 API key。

DashScope 可用的模型名：`qwen-max`、`qwen-plus`、`kimi-k2-thinking`、`glm-5.1`、`MiniMax-M2.5` 等。

添加新 provider：如果是 OpenAI 兼容 API，在 `core/models/factory.py` 的 `PROVIDER_CONFIGS` 加一行即可。
