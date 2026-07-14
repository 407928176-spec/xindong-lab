# 心动实验室

> 一个用大模型驱动的关系对话模拟游戏。你描述一个想认识的人，AI 把他/她变成活的角色，
> 然后你们从陌生人开始聊。**你看不到自己在对方心里的样子**——就像现实里那样。

单机运行，数据全部存在你自己电脑上。填入你自己的大模型 API，双击一下就能玩。

## 这游戏是什么

大多数恋爱模拟给你一个进度条，告诉你好感度 +5。这个不给。

- **人设由你创造**：跟 AI 聊天描述你想认识的人——性格、说话方式、在意什么、讨厌什么。
  AI 把这段对话变成一个完整角色。
- **隐藏状态在暗处演化**：舒适感、兴趣度、信任感、警惕度、初始匹配基线，五个维度实时变化。
  **你永远看不到它们。** 你只能从对方的回复里去感觉——回得短了？主动问你了？还是敷衍了一句？
- **表白会有结局**：说出口的那一刻，规则引擎根据隐藏状态判定 HE / NE / BE，AI 写下一段旁白式评价，
  告诉你这段关系为什么走到这里。
- **失败不能回档**。同一个人设可以再生成一个角色实例，但那是另一条线、另一个人。

设计哲学是「通过 A 最终找到 B」：让失败被**感觉到**，而不是被通知。

## 快速开始

### 1. 装好这两个

- [Python](https://www.python.org/downloads/) 3.11 或更新（Windows 安装时**务必勾选 Add Python to PATH**）
- [Node.js](https://nodejs.org/) 20 或更新

### 2. 下载本项目

点右上角绿色 `Code` → `Download ZIP` → 解压。或者：

```bash
git clone https://github.com/<your-name>/xindong-lab.git
```

### 3. 启动

- **Windows**：双击 `start.bat`
- **macOS / Linux**：终端里执行 `bash start.sh`

首次启动要装依赖、构建前端，**大约 3-8 分钟**，只有第一次这么久。之后再启动几秒就好。

脚本会自动装依赖、建数据库、拉起前后端，然后打开浏览器。

### 4. 填入你的大模型

浏览器会自动停在配置页，填三样东西：

| 填什么 | 说明 |
|---|---|
| **Base URL** | 你的大模型服务地址。点预设按钮自动填 |
| **API Key** | 你在供应商那里申请的 Key |
| **模型名称** | 用哪个模型 |

点「测试连接」确认能用，再点「保存并开始」，就进游戏了。

**关掉游戏**：Windows 双击 `stop.bat`；macOS / Linux 在终端按 `Ctrl+C`。

## 支持哪些大模型

任何 **OpenAI 兼容**的服务都行。常见的：

| 供应商 | Base URL | 模型名填什么 |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` 等 |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 火山方舟（豆包） | `https://ark.cn-beijing.volces.com/api/v3` | 推理接入点 ID，形如 `ep-2024...` |
| 阿里通义 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-max` 等 |
| Ollama（本地跑） | `http://localhost:11434/v1` | `qwen2.5:14b` 等，Key 随便填 |
| OpenRouter | `https://openrouter.ai/api/v1` | 该平台的模型 ID |

> **模型选择建议**：这游戏对角色回复的**文笔和分寸感**要求较高，太小的模型会让角色说话很塑料。
> 主模型建议用各家的旗舰级别；辅助模型（状态评估、结局评价、记忆总结）可以在「高级」里单独指定
> 一个更便宜的，这些环节不需要文采，能省不少钱。

### 关于联网搜索

游戏支持角色聊实时话题（今天天气、最近的新闻），但**这个功能只有火山方舟支持**——
它依赖方舟私有的联网内容插件，OpenAI 标准接口没有对应能力。

- 用**火山方舟**且为该 Key 开通了「联网内容插件」：联网可用，配置页测试连接时会告诉你
- 用**其他任何供应商**：角色无法获取实时信息，**其余玩法完全不受影响**

聊天界面顶部有个小标签显示当前状态（`联网已开启` / `联网不支持`），不用猜。

## 常见问题

**配置页提示「API Key 无效」**
Key 填错了，或者这个 Key 没开通你填的那个模型的权限。去供应商控制台确认一下。

**配置页提示「找不到模型」**
模型名拼错了。注意有些供应商（比如火山方舟）要填的是**接入点 ID**，不是模型的展示名称。

**配置页提示「连不上 Base URL」**
地址填错了。大多数供应商需要以 `/v1` 结尾。如果你在国内访问 OpenAI，还需要代理。

**页面提示「连不上后端服务」**
后端没起来。看一眼启动时那个最小化的黑色窗口里有没有报错。

**双击 start.bat 一闪就没了**
多半是 Python 或 Node 没装，或者装了但没加进 PATH。用 `stop.bat` 旁边的方式手动跑一次
`powershell -ExecutionPolicy Bypass -File start.ps1` 能看到具体报错。

**我想换个模型 / 换个 Key**
进游戏后点左侧「设置」，随时改。

**我的 API Key 会被传到哪里去吗**
不会。Key 只存在你自己电脑的 `backend/data/llm_config.json`，只用来直连你填的那个 Base URL。
这个项目没有任何自己的服务器，也没有任何统计上报。

**游戏数据存在哪**
全部在 `backend/data/` 下：`app.db` 是存档（人设、角色、聊天记录），`uploads/` 是你发过的图片。
想备份就整个复制走；想重开就删掉这个目录再启动一次。

**背景音乐能换吗**
能。`frontend/public/bgm/` 下换成你自己的 mp3 即可，文件名保持一致。

## 项目结构

```
├── start.bat / start.ps1     Windows 一键启动（stop.bat 停止）
├── start.sh                  macOS / Linux 一键启动（Ctrl+C 停止）
├── backend/                  FastAPI 后端
│   ├── app/
│   │   ├── api/routes/       HTTP 接口（薄路由层）
│   │   ├── config/           大模型配置、附件策略
│   │   ├── engine/           LangGraph 对话链路
│   │   │   ├── graph.py      主状态图
│   │   │   ├── nodes/        各节点：载入上下文/生成回复/状态评估/结局判定…
│   │   │   └── prompts/      全部 prompt 模板（.md，不硬编码在代码里）
│   │   ├── models/           SQLAlchemy 模型
│   │   └── services/         业务逻辑
│   ├── data/                 你的存档（gitignore，不会进仓库）
│   └── scripts/init_db.py    建表 + 种入本地玩家
├── frontend/                 Next.js 前端
│   └── src/
│       ├── app/              页面路由
│       ├── components/       UI 组件
│       └── lib/              工具与 API 封装
└── docs/                     设计文档（PRD / 架构 / Prompt 契约）
```

## 想改代码

```bash
# 后端
cd backend
.venv/Scripts/activate        # Windows；macOS/Linux 用 source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pytest                        # 跑测试

# 前端
cd frontend
npm run dev                   # 开发模式，改代码自动刷新
npm run lint
```

想了解设计思路，看 `docs/`：

- [`docs/PRD.md`](docs/PRD.md) —— 产品设计：隐藏状态怎么演化、结局怎么判定、为什么不给进度条
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) —— 技术架构：LangGraph 链路、分层约定、边界
- [`docs/PROMPT_IO_CONTRACT.md`](docs/PROMPT_IO_CONTRACT.md) —— 每个 prompt 的输入输出契约（**改 prompt 前必读**）

一条重要约定：**LLM 负责语义理解和定性判断，数值计算由规则引擎负责**。
心动值、隐藏状态加减分都是工程代码算的，不让模型直接输出分数——否则数值会飘得没法玩。

## 许可

[MIT](LICENSE)。随便用、随便改、随便商用，保留版权声明即可。

背景音乐由项目作者自制，一并以 MIT 授权。
