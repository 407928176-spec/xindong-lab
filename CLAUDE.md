# CLAUDE.md

给用 Claude Code（或其他 AI 编码助手）参与本项目的人。人类贡献者读这个也一样有用。

## 项目定位

「心动实验室」是一个关系对话模拟游戏：AI 人设生成 → 长期关系对话 → 隐藏状态演化 → 复盘分析。

**开源版是单机游戏**：没有账号系统、没有对象存储、没有服务器。玩家填自己的大模型 API Key，
数据全部存在本机 SQLite 和本地磁盘上。做任何改动前先理解这个前提——它解释了代码里很多设计。

前后端分离：浏览器中的 Next.js 前端直接调用 FastAPI REST 接口，不经过 Next.js API Routes 中转。

## 参考文档

- [docs/PRD.md](docs/PRD.md)：产品设计（隐藏状态、心动值、结局判定）
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：LangGraph 链路的设计事实源
- [docs/PROMPT_IO_CONTRACT.md](docs/PROMPT_IO_CONTRACT.md)：**撰写或修改任何 prompt 前必读**
- [docs/character_creation_extract_prompt输出格式及说明.md](docs/character_creation_extract_prompt输出格式及说明.md)：抽取 JSON schema 的权威定义

## 技术栈（不得擅自更换）

- 前端：Next.js App Router + TypeScript + shadcn/ui + Tailwind CSS
- 后端：Python FastAPI + SQLAlchemy 2.0+
- 数据库：SQLite
- 智能体编排：LangGraph，**仅用于核心对话链路**
- LLM 接入：OpenAI 兼容接口，见 `backend/app/engine/llm_client.py`
- 依赖锁定：Python 用 `backend/requirements.txt` 固定版本；Node 用 `package-lock.json`。禁止 `>=` / `*`

## 常用命令

```bash
# 一键启动（含依赖安装、建库、构建）
start.bat            # Windows
bash start.sh        # macOS / Linux

# 后端（在 backend/ 下）
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pytest
pytest tests/engine/test_llm_client.py::test_ark_endpoint_gets_thinking_disabled

# 前端（在 frontend/ 下）
npm run dev
npm run build
npm run lint
```

后端默认端口 8000，前端 3000。

## 架构约束

- 前端直连 FastAPI，不用 Next.js API Routes 中转。
- 所有数据库访问走 SQLAlchemy ORM，禁止写业务原生 SQL。
- LangGraph 只用于核心对话链路：意图识别、回复生成、状态更新、心动值计算、记忆更新、终局判定。
  人设 CRUD、附件、复盘记录等普通业务走 FastAPI 普通路由 + service 层。
- 复盘模块与对话主链路物理隔离：只读链路，不走状态图，不回写角色状态。
- **LLM 负责语义理解和定性判断；数值逻辑由规则引擎负责。**
  隐藏状态加减分、心动值计算都是工程代码算的——不让 LLM 直接输出最终分数，否则数值会飘得没法玩。

## 大模型接入的两个坑

改 `llm_client.py` 前必须知道：

1. **厂商专属参数必须条件化。** `extra_body={"thinking": {"type": "disabled"}}` 是火山方舟私有的，
   发给 OpenAI 官方接口会直接 400。统一用 `llm_config.is_ark_endpoint()` 判断后再加。
   `backend/tests/engine/test_llm_client.py` 里有专门钉这条的回归测试，别绕过。
2. **联网搜索是方舟私有能力**（`/responses` + 内置 `web_search` 工具）。其他供应商没有对应物，
   `use_web_search=True` 在非方舟端点会被静默忽略。

配置只来自 `backend/app/config/llm_config.py`，**不要在任何地方读厂商专属环境变量，更不要硬编码 Key**。

## 附件为什么要 base64

图片送模型时必须转成 `data:image/png;base64,...` 内联进请求体，**不能给 URL**——
附件存在玩家自己硬盘上，模型供应商的服务器访问不到 `127.0.0.1`。
这也是图片上限（4MB）比普通文件（10MB）严的原因：base64 编码后体积膨胀约 1/3。

`backend/app/config/attachment_policy.py` 和 `frontend/src/lib/attachment-policy.ts` 是一份策略的两处镜像，改一个必须同步改另一个。

## Prompt

Prompt 模板统一放在 `backend/app/engine/prompts/`，每个用途一个 `.md`，通过 `loader.py` 读取。
**禁止在 Python 代码里硬编码多行正式 prompt 正文。**

`evaluate_state_prompt.md`、`ending_judge_prompt.md`、`memory_summary_prompt.md` 使用
`apply_template_placeholders` 做占位符替换（见 `prompt_template.py`）；
`system_prompt.md` 和 `persona_generator_prompt.md` 是静态文本，不走占位符引擎。

## 编码规范

前端：函数式组件；组件文件 PascalCase，目录 kebab-case；props 用 TypeScript interface，不用 `any`；
优先 shadcn/ui，不额外引入 UI 库。

后端：用 type hints；路由 / 业务逻辑 / 数据模型分层；请求响应用 Pydantic 模型；
错误用 HTTPException，不吞异常；snake_case。

避免：在前端直接操作数据库；把业务逻辑写在路由函数里；在状态图里塞 CRUD；
让 LLM 直接输出具体数值；用 `any` / `type: ignore` 绕过类型检查；外部调用不做错误处理。

关键逻辑、非显而易见的设计决策处，写中文注释解释**为什么这么做**，而不是在说这行代码做了什么。

## 安全

- 禁止把真实 API Key、Token 写进仓库。玩家的 Key 存在 `backend/data/llm_config.json`（已 gitignore）。
- 禁止在日志、HTTP 响应体、异常 `detail` 里输出完整 API Key。
  回显给前端一律走 `llm_config.masked_api_key()`。
- `object_key` 会参与拼接本地文件路径，任何改动都必须保持
  `local_storage_service.validate_object_key_strict()` 的防穿越校验。
