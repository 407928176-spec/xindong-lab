# 架构设计 — LangGraph 对话引擎

> 本文是对话引擎的设计事实源。它由项目开发期的阶段性设计文档整理而来，因此行文里
> 保留了「本阶段要做的事」这类过程性表述——描述的功能都已实现，可以按现状阅读。
> 代码与文档冲突时以代码为准。

## 1. 目标

用 LangGraph 构建端到端的对话引擎。
引擎接收用户消息，经过「上下文加载 → 回复生成 → 状态评估 → 记忆管理 → 条件路由」多个节点，
输出角色回复和更新后的隐藏状态，接入 FastAPI `/chat` 接口跑通前后端完整链路。

---

## 2. 核心数据结构：ConversationState

整个 LangGraph 图围绕一个 TypedDict 流转。所有节点共享这个 State，每个节点只修改自己负责的字段。

### 2.1 类型定义

class HiddenState(TypedDict):
    comfort: float                # 舒适度 0-100
    interest: float               # 兴趣度 0-100
    trust: float                  # 信任度 0-100
    alertness: float              # 警觉度 0-100
    baseline_compatibility: float # 基础契合度 0-100（创建时确定，不变）

class StateChanges(TypedDict):
    comfort_delta: float
    interest_delta: float
    trust_delta: float
    alertness_delta: float
    reason: str                   # 变化原因（供调试/复盘用）

class ConversationState(TypedDict):
    # ===== 输入层（每轮由 API 层填入） =====
    character_id: str
    user_message: str
    current_round: int

```
# ===== 上下文层（从 DB 加载，喂给 LLM） =====
system_prompt: str            # 通用规则层（所有角色共享）
persona_prompt: str           # 角色人设层（每个角色独有）
hidden_state: HiddenState
long_term_memory: str         # 长期记忆摘要文本（由异步压缩任务滚动更新，见 §2.3）
recent_messages: list         # 近期全量对话窗口 [{"role": "user"|"assistant", "content": "..."}]，见 §2.3

# ===== 节点输出层（逐步填充） =====
character_reply: str          # 角色回复文本（generate_reply 节点填）
intent: str                   # 意图标签（evaluate_state 节点填）
state_changes: StateChanges   # 本轮状态变化（evaluate_state 节点填）
new_hidden_state: HiddenState # 更新后的隐藏状态（evaluate_state 节点填）
new_heartbeat_score: float    # 更新后的心动值 0-100（evaluate_state 节点填）
should_update_memory: bool    # 本轮是否触发了「异步长记忆压缩」入队（或任务已完成并写回；memory_manager 填，语义见 §2.3）

# ===== 结局层（仅表白时填充） =====
ending_result: str | None     # "HE" / "BE" / "NE" / None
ending_evaluation: str | None # 结局评价文本
```

### 2.2 LLM 消息组装顺序

每次调用豆包 API 时，按以下顺序组装 messages 数组：

位置 1 — system 消息 → system_prompt（通用规则）
位置 2 — system 消息 → persona_prompt（角色人设）
位置 3 — system 消息 → 当前隐藏状态 JSON（让 LLM 知道当前关系阶段）
位置 4 — system 消息 → long_term_memory（长期记忆摘要）
位置 5 — user/assistant 交替消息 → recent_messages（最近 N 轮对话）
位置 6 — user 消息 → 本轮 user_message

### 2.2.1 接入形态（Chat Completions + 联网资料包）

- **角色最终回复**（见 `backend/app/engine/nodes/generate_reply.py`）：仍使用 OpenAI 兼容 **`POST .../chat/completions`**，请求体为 `messages` 数组；最终回复不直接启用联网搜索，保持角色口吻与流式输出稳定。
- **联网资料包**（见 `backend/app/engine/web_context.py`、`backend/app/engine/llm_client.py`）：在角色最终回复前，先由模型判断本轮是否需要联网；需要时通过火山 **Responses API** 调用内置 `web_search` 工具生成内部资料包，再插入最后一条 user 消息前供角色参考。
- **联网来源**：Responses API 的 `web_search` 工具固定传 `tools.sources = ["toutiao", "douyin", "moji"]`。
- **能力门禁**：联网是方舟私有能力，且需为 API Key 单独开通「联网内容插件」。是否可用以保存配置时的实测探测结果为准（`web_context.web_search_available()`）；不可用时整条联网链路直接短路——连「要不要联网」都不问模型，省掉一次无谓调用。前端聊天页有标识告知玩家当前状态。
- **手动探针**：`backend/scripts/prompt_obedience_probe.py`（`temperature=0`、4 组 × 流式/非流式、打印 SDK 原始输出与 `normalize_character_reply` 后文本）；在 `backend/` 下执行  
  `python scripts/prompt_obedience_probe.py [--runs N] [--verbose]`。  
  输出中的「最终展示链」对齐生产：`call_llm` 等价于对 assistant `content` 做 `.strip()` 后，角色回复再经 `no_reply.normalize_character_reply`。

### 2.2.2 附件

- 支持 jpg / png / webp / txt / docx，**不支持 PDF**（前后端 `attachment_policy` 均未放行 `application/pdf`）。
- 附件存在玩家本机 `backend/data/uploads/`，见 `backend/app/services/local_storage_service.py`。
- **图片必须转 base64 `data:` URI 内联进请求体**，不能给 URL——模型供应商的服务器访问不到玩家本机。
  这也是图片上限（4MB）比 txt/docx（10MB）更严的原因：base64 编码后体积膨胀约 1/3。
- TXT / DOCX 在服务端解析成文本片段后再送入 Chat，不进图片通道。

### 2.3 长期记忆与 `recent_messages`（滚动压缩，唯一策略）

本节为阶段 5 **长期记忆与近期窗口**的单一事实来源；**不再**使用「每固定轮数」「高 delta」等触发摘要的规则。

**一轮的定义**：**1 轮 = 1 条 user + 1 条 assistant（角色侧）** 成对出现。裁剪时以**完整成对**为准：末尾若仅有未配对的半轮，不单独算作一轮保留单位（实现时可选择丢弃不成对尾部或并入下一轮，须在代码注释中固定一种）。

**近期对话存放**：用户与角色的**全量对话内容**先持续累积在 `**recent_messages`**（及 DB 中与 `character_id` 关联的消息记录；加载进图时与持久化保持一致）。

**未满 1 万字**：对 `recent_messages` 中每条 `content` 做**字符数求和**（中文「字」= Python `len(str)` 字符数，**不是** UTF-8 字节数）。**总和 < 10000** 时：**不**触发长记忆压缩 LLM，不为此单独调用摘要模型。

**达到 1 万字（≥ 10000）**：**异步**触发一次「长记忆压缩」任务（**禁止**在 LangGraph 主路径内 `await` 该 LLM 调用；可由 API 层 `BackgroundTasks`、进程内队列或后续独立 worker 执行，实现阶段再选型）。

**压缩任务的 LLM 输入**（每次触发形式统一，便于实现）：

- **已有 `long_term_memory` 全文**（首次可为空串）**+ 当前 `recent_messages` 全文**（序列化为可读文本），交给摘要模型；
- 输出为**新的** `long_term_memory` 全文（合并、去重、保留关键事实与关系转折；具体风格与字数上限由摘要 prompt 约束，建议上限如 1000～2000 字并在实现中可配置）。

**压缩任务完成后的落库与裁剪**：

1. 将新摘要写回持久化字段（如 `Character.long_term_memory`）。
2. `**recent_messages` 仅保留最近 20 轮**（20 对 user+assistant）；**更早的对话**从「近期窗口」对应的数据中**删除**（实现上可物理删除 `Message` 行或迁移到归档表，由实现选定，但对外语义是：不再出现在 `recent_messages` / 近期加载结果中）。
3. 用户继续聊天时，**每轮新内容追加**到 `recent_messages`。
4. 当 `recent_messages` **再次**字符总和 **≥ 10000** 时，**重复**步骤「异步压缩：旧 `long_term_memory` + 当前全量 `recent_messages` → 新 `long_term_memory`」+「再裁成仅最近 20 轮」。**循环往复**。

**与当轮对话的关系**：触发检测可在 `memory_manager`（或 API 层在 `invoke` 之后）完成；**当轮** `generate_reply` 仍使用**触发前**已加载的上下文快照，不因异步任务未完成而阻塞用户。

### 2.4 Token 预算估算（默认对话模型 `doubao-seed-2-0-lite-260215`）

**说明**：实际上下文窗口以方舟控制台该接入点 / 官方文档为准；下表仍按 **约 128K 量级** 做 MVP 估算，若与实测不符可再改 `message_token_budget` 中的比例与上限。

system_prompt:          约 3,000-5,000 tokens
persona_prompt:         约 800-1,500 tokens
hidden_state JSON:      约 300 tokens
long_term_memory:       约 800-1,500 tokens
预留输出:               约 2,000 tokens
─────────────────────────────────
固定开销合计:           约 7,000-10,300 tokens
剩余给 recent_messages: 约 117,700-121,000 tokens
可支撑对话轮数:         约 55-60 轮（每轮约 2,000 tokens；实际近期窗口由 §2.3 的「满 1 万压缩 + 保留 20 轮」滚动约束，与 128K 预算互为补充）

---

## 3. LangGraph 图结构

```
                ┌─────────────┐
                │   入口       │
                │(load_context)│
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │ 角色回复生成  │
                │(generate_reply)│
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │ 状态评估     │
                │(evaluate_state)│
                └──────┬──────┘
                       │
                 ┌─────┴─────┐
                 │ 条件路由    │
                 │(route)     │
                 └─┬───────┬─┘
                   │       │
          intent≠表白   intent=表白
                   │       │
                   ▼       ▼
           ┌──────────┐  ┌──────────┐
           │ 记忆管理   │  │ 结局判定   │
           │(memory_   │  │(ending_   │
           │ manager)  │  │ judge)    │
           └─────┬────┘  └─────┬────┘
                 │             │
                 ▼             ▼
           ┌──────────┐  ┌──────────┐
           │ 保存并返回 │  │ 保存并返回 │
           │(save_and_ │  │(save_and_ │
           │ respond)  │  │ respond)  │
           └──────────┘  └──────────┘
```

---

## 4. 子步骤拆分

---

### 步骤 5.1 — LangGraph 基础骨架

**目标：**
创建空的 StateGraph，为**主链**注册节点（pass-through 占位），跑通一条最小链路（`ending_judge` 见上文，不在此步进图）。

**要做的事：**

- 安装依赖：将 langgraph、openai、tiktoken 添加到 requirements.txt，然后执行 pip install -r requirements.txt
- 创建文件 backend/app/engine/graph.py
- 定义 ConversationState TypedDict（完整结构见第 2 节）
- 创建 StateGraph(ConversationState)
- 注册 **5** 个节点名：`load_context`、`generate_reply`、`evaluate_state`、`memory_manager`、`save_and_respond`（直线顺序）。`ending_judge` **不在此步注册进图**（悬空节点会导致 LangGraph 编译失败）；仅保留 `nodes/ending_judge.py` 占位实现，留待步骤 5.6 接入条件边时再注册。
- 每个节点暂时是 pass-through 函数：接收 state，原样返回
- 设置边：load_context → generate_reply → evaluate_state → memory_manager → save_and_respond
- 条件路由先不加，走直线
- 编译图：实现中可导出 `build_compiled_graph()`（内部 `graph.compile()`），供测试与后续 API 注入

**新增文件结构：**

backend/app/engine/
├── **init**.py
├── graph.py                  # LangGraph 图定义与编译
├── state.py                  # ConversationState 等 TypedDict 定义
├── nodes/
│   ├── **init**.py
│   ├── load_context.py       # 上下文加载节点
│   ├── generate_reply.py     # 角色回复生成节点
│   ├── evaluate_state.py     # 状态评估节点
│   ├── memory_manager.py     # 记忆管理节点
│   ├── ending_judge.py       # 结局判定节点
│   └── save_and_respond.py   # 持久化与返回节点
└── prompts/
    └── system_prompt.md      # 通用 system prompt（persona_prompt 从 DB 加载）

**pass-through 节点示例（所有节点初始写法）：**

def load_context(state: ConversationState) -> dict:
    # TODO: 步骤 5.2 实现
    return {}

**验收标准：**

- pytest 能跑通一个测试：构造最小 state 输入，图能走完所有节点不报错
- 输入什么 state，输出的 state 与输入一致（pass-through）

**给 Cursor 的指令：**
请阅读 PHASE5_DESIGN.md 第 2 节与步骤 5.1 本节，完成步骤 5.1：

1. 将 langgraph、openai、tiktoken、pytest 添加到 requirements.txt，执行 pip install -r requirements.txt
2. 创建 backend/app/engine/ 目录结构；在仓库根或 `backend/` 下配置 `backend/pytest.ini`（`testpaths`、`pythonpath`）与 `backend/tests/conftest.py`（保证 `import app` 可用）
3. 在 state.py 中定义所有 TypedDict（可提供 `minimal_conversation_state()` 供测试）
4. 在 nodes/ 下每个文件写 pass-through 函数
5. 在 graph.py 中组装 StateGraph 并编译（导出 `build_compiled_graph()`）
6. 编写 `backend/tests/engine/test_graph_skeleton.py`：最小 state 跑通全链且输出与输入一致（pass-through）

---

### 步骤 5.2 — 上下文加载节点 (load_context) + 豆包 API 接入

**目标：**
实现 load_context 节点，从 DB 加载角色人设、隐藏状态、历史消息、长期记忆；
同时完成豆包 Doubao-Seed-Character API 的接入封装。

**要做的事：**

A. 大模型 API 封装

- `backend/app/engine/llm_client.py`：只使用 OpenAI 标准的 `chat/completions`，
  因此任何 OpenAI 兼容端点都能直接用（OpenAI / DeepSeek / 火山方舟 / 通义 / Ollama…）
- 配置来源是 `backend/app/config/llm_config.py`，**不读任何厂商专属环境变量**：
  玩家在网页向导（`/setup`）填写后存入 `backend/data/llm_config.json`；
  环境变量 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` / `LLM_AUX_MODEL` 优先级更高，
  可用于服务器部署时绕过向导
- 对外暴露 `call_llm` / `acall_llm`，支持流式和非流式两种调用方式
- **厂商差异必须条件化**，绝不能污染标准端点，判断入口统一是 `llm_config.is_ark_endpoint()`：
  - `extra_body={"thinking": {"type": "disabled"}}`：方舟 Seed 系列需要它关闭深度思考，
    但 OpenAI 官方接口收到未知字段会直接 400
  - 联网搜索：走方舟私有的 `/responses` 端点 + 内置 `web_search` 工具，别家没有对应能力

B. load_context 节点实现

- 根据 character_id 从 DB 加载：
  - persona_prompt（角色人设文本）
  - hidden_state（当前五维状态）
  - recent_messages（**当前近期窗口内的全量对话**：即自上次异步压缩裁剪后保留的最多 20 轮 + 之后新产生的所有消息，直到再次触发 §2.3 压缩；不是「永远只取 20 条消息」）
  - long_term_memory（滚动摘要；压缩任务完成后更新）
  - current_round（当前轮数）
- 从文件加载 system_prompt（读取 prompts/system_prompt.md）
- 将以上内容填入 state 对应字段并返回

**验收标准：**

- 单独调用 call_llm 能拿到豆包的回复
- load_context 节点能从测试 DB 中正确加载所有字段
- 加载后的 state 中 system_prompt、persona_prompt、hidden_state、recent_messages 均非空

**给 Cursor 的指令：**
请阅读 PHASE5_DESIGN.md 第 2.3 节与步骤 5.2 本节，完成步骤 5.2：

1. 创建 llm_client.py，封装豆包 API 调用（兼容 OpenAI SDK）
2. 实现 load_context 节点，从 DB 加载上下文
3. 在 prompts/system_prompt.md 中放一个初始版本的通用 prompt（可以先写占位内容）
4. 写测试验证 API 调用和上下文加载

---

### 步骤 5.3 — 角色回复生成节点 (generate_reply)

**目标：**
实现 generate_reply 节点，按 2.2 节的消息组装顺序构造 messages，调用豆包生成角色回复。

**要做的事：**

- 按以下顺序组装 messages 列表：
  1. {"role": "system", "content": system_prompt}
  2. {"role": "system", "content": persona_prompt}
  3. {"role": "system", "content": "当前关系状态：" + json.dumps(hidden_state, ensure_ascii=False) + "\n" + relationship_state_prompt}
  4. {"role": "system", "content": "长期记忆：" + long_term_memory}
  5. 遍历 recent_messages，依次添加 {"role": "user"|"assistant", "content": "..."}
  6. {"role": "user", "content": user_message}
- 调用 call_llm(messages) 获取回复
- 将回复写入 state["character_reply"]
- **持久化窗口**：不以「每轮从 DB 删除旧消息」来适配 128K；近期过长时由 **§2.3** 的「满 1 万字符异步压缩 + 裁成 20 轮」负责。
- **仅当轮 LLM 输入副本**：若组装后的 `messages` 仍超出单次上下文预算，允许只对**传入模型的那份列表**做临时截断（从最旧开始丢），**不得**借此破坏「压缩任务完成后 DB 中仍保留至少 20 轮成对消息」的约定（即：截断只作用于副本，不回写删库）。

**消息截断策略（与 §2.3 的关系）：**

- 用 tiktoken 或简单字符估算（1 中文字 ≈ 1.5 token）判断单次调用是否超限。
- 固定开销预留约 10,000 tokens 给 system / persona / hidden / long_term_memory / 输出。
- 剩余空间分配给 `recent_messages` + 本轮 `user_message`；**仅副本**可从最旧开始丢到预算内。

**验收标准：**

- 给定一个完整的 state（含 system_prompt、persona_prompt、hidden_state、recent_messages、user_message），能返回角色风格一致的回复
- 连续 3 轮对话，回复连贯、不出戏
- 超长场景：验证「副本截断」不会导致 DB 中近期窗口少于 20 轮（与 §2.3 一致）

**给 Cursor 的指令：**
请阅读 PHASE5_DESIGN.md 第 2.2、2.3、2.4 节与步骤 5.3 本节，完成步骤 5.3：

1. 在 generate_reply.py 中实现消息组装逻辑
2. 实现 token 预算控制；**仅**对当轮 LLM 输入副本做截断，不破坏 §2.3 的 20 轮落库约定
3. 调用 llm_client.call_llm 生成回复
4. 写测试：3 轮连续对话 + 超长输入副本截断行为

**实现摘要（仓库，与上文对齐）：**

- `backend/app/engine/nodes/generate_reply.py`：§2.2 顺序组装；`system_prompt` 经 `prompts/loader.read_prompt("system_prompt.md")`；`persona_prompt` 等来自 `ConversationState`（由 `load_context` 注入）；`call_llm` → `character_reply`。
- `backend/app/engine/message_token_budget.py`：`tiktoken` `cl100k_base` 估算；总预算约 `128000 * 0.88` 并预留输出 token；**仅裁减传入模型的 messages 副本**中「中间 recent」段，从最旧删起；**不写库**。
- `backend/app/engine/prompts/`：`loader.py` + 7 个 `.md` 占位（含后续 5.4–5.6 与对话式人设用文件名）；节点**不**在代码里硬编码正式 prompt 正文。
- `Character.persona_prompt`：`persona_generator.generate_persona_prompt` 当前**固定返回空串**，`load_context` 在 `not character.persona_prompt` 时回退人设表拼装；`init_db.py` / `tests/conftest.py` 为旧 SQLite 补 `ALTER COLUMN`。
- 测试：`tests/engine/test_generate_reply.py`（顺序、副本截断、三轮 `call_llm` 调用次数）；`tests/engine/test_evaluate_state.py`（mock `call_llm` 验证解析、clamp、心动值与占位符替换）；`test_graph_skeleton` 对 `generate_reply` 与 `evaluate_state` 的 `call_llm` 分别 patch 以无密钥跑全链。**书面验收**中「风格一致、三轮语义连贯」依赖真模型/人工；「DB 不少于 20 轮」由实现不写库保证，可再增加对 DB 的专项断言（待办）。

---

### 步骤 5.4 — 状态评估节点 (evaluate_state)

**目标：**
实现 evaluate_state 节点，分析本轮对话，输出意图标签、五维状态变化、新的心动值。

**要做的事：**

- **评估用正文**：仅从 `backend/app/engine/prompts/evaluate_state_prompt.md` 经 `prompts/loader.read_prompt` 读取；代码**不得**硬编码多行评估指令。实现侧将当前 `ConversationState` 中适合注入的字段打成 `dict[str, str]`（键名与 state 字段名一致，如 `persona_prompt`、`hidden_state`、`user_message`、`character_reply` 等），按模板内实际出现的 `{identifier}` 做通用替换；模板未使用的键忽略，模板出现而字典无键时替换为空串。**占位符命名以该 .md 定稿为准**。
- **模型输出格式**（工程解析目标，具体措辞与约束写在上述 `.md` 中）：
  - 根对象为 JSON。
  - `intent`：字符串（意图标签；允许取值见 `evaluate_state_prompt.md`）。
  - `state_changes`：对象，至少包含 `comfort_delta`、`interest_delta`、`trust_delta`、`alertness_delta`（数值）、`reason`（字符串）。工程侧对 delta 做 `[-10, +10]` clamp，再写入 `new_hidden_state`（四维与当前值相加后每维 clamp 到 `[0, 100]`；`baseline_compatibility` 不参与 delta，保持本轮输入值）。
- 解析 LLM 返回的 JSON
- 计算 new_hidden_state：当前值 + delta，clamp 到 [0, 100]
- 计算 new_heartbeat_score：
heartbeat = 50 + (comfort - 50) * 0.25 + (interest - 50) * 0.25 + (trust - 50) * 0.3 - (alertness - 50) * 0.15 + (baseline_compatibility - 50) * 0.2
clamp 到 [0, 100]
- 将 intent、state_changes、new_hidden_state、new_heartbeat_score 写入 state

**JSON 解析容错：**

- LLM 可能返回 markdown 包裹的 JSON，需要先剥离
- 如果解析失败，使用默认值：所有 delta 为 0，intent 为 "闲聊"
- 记录解析失败日志供排查

**验收标准：**

- 正面对话（"你说的好有道理"）→ comfort/interest/trust 上升
- 冒犯对话（"你好烦别说了"）→ alertness 上升，其他下降
- 表白（"我喜欢你做我女朋友吧"）→ intent 返回 "表白"
- JSON 解析失败时不崩溃，使用默认值

**给 Cursor 的指令：**
请阅读 PHASE5_DESIGN.md 步骤 5.4 本节，完成步骤 5.4：

1. 在 evaluate_state.py 中实现：`read_prompt("evaluate_state_prompt.md")`、state→字符串字典、通用占位符替换、`call_llm`（不在代码中硬编码评估正文）
2. 实现 JSON 解析和容错逻辑
3. 实现 hidden_state 更新计算和 heartbeat_score 公式
4. 写测试：正面/冒犯/表白三种场景的状态变化方向

**实现摘要（仓库，与上文对齐）：**

- `backend/app/engine/nodes/evaluate_state.py`：`read_prompt("evaluate_state_prompt.md")` → `state_to_replacement_map` → `apply_template_placeholders` → `call_llm`；`parse_evaluation_llm_output` 去围栏与容错；`apply_deltas_to_hidden`、`compute_heartbeat_score`；模板为空则跳过 LLM 并回退默认。
- 测试：`tests/engine/test_evaluate_state.py`；`test_graph_skeleton` 双 mock `call_llm`。

---

### 步骤 5.5 — 记忆管理节点 (memory_manager)

**目标：**
实现 `memory_manager` 节点（及/或 API 层协作逻辑）：按 **§2.3** 检测 `recent_messages` 字符总和是否达到 **10000**；若达到则**入队异步长记忆压缩**，**不在图内 await** 摘要 LLM；未达标则快速 pass-through。

**要做的事：**

A. 触发条件（**唯一**）

- 计算 `recent_messages` 中每条 `content` 的字符数之和 `total_chars`。
- 当 `**total_chars >= 10000`**：触发一次异步压缩任务（每轮最多入队一次；若上一轮任务尚未完成，实现上应合并或排队，避免并发写同一 `character_id` 导致撕裂——建议 per-character 队列或版本号，文档层要求「串行化写回」即可）。

B. 异步压缩任务（与节点关系）

- **不在** `memory_manager` 同步函数内调用阻塞式 `call_llm` 做全文摘要（除非 MVP 刻意简化且仍不阻塞 HTTP——不推荐）。
- 任务体逻辑：
  1. 读取当前持久化的 `long_term_memory`（可为空）与当前全量 `recent_messages` 文本；
  2. 调用 LLM 生成**新** `long_term_memory`（指令正文来自上节 C 所述 `memory_summary_prompt.md`；字数硬上限可在实现中配置，如 2000 字）；
  3. 写回 `Character.long_term_memory`；
  4. 将 DB / 状态中 `recent_messages` 对应部分**裁剪为仅最近 20 轮**（成对），删除更早记录（语义见 §2.3）。
- 同步 `memory_manager` 节点：设置 `state["should_update_memory"]`（`True` = 字符总和已达阈值，**由 API 在整图 invoke 结束且本轮消息已落库后**入队 `BackgroundTasks`；**不**表示异步压缩已完成。语义以 `state.py` 字段注释为准）。

C. 摘要用正文（供异步任务调用）

- 仅从 `backend/app/engine/prompts/memory_summary_prompt.md` 经 `read_prompt` 读取；代码用与 `evaluate_state` 相同的「state/上下文 → 字符串字典 + 模板占位符替换」思路注入变量，**不**在设计文档或 Python 中硬编码摘要指令正文。
- **输入变量**（实现时与模板占位符对齐，名称以该 `.md` 为准）：至少包括当前持久化的 `long_term_memory` 全文、由 `recent_messages` 序列化得到的近期对话全文（或等价文本）。
- **输出**：模型返回的**纯文本**新摘要，写入持久化 `long_term_memory`；字数与风格约束由 `memory_summary_prompt.md` 约定（实现可再配硬上限如 2000 字）。

D. 未触发时

- `total_chars < 10000`：`state["should_update_memory"] = False`，不调用摘要 LLM，不修改 `long_term_memory`。

**验收标准：**

- `< 10000` 字符：`should_update_memory == False`，无摘要 LLM 调用。
- `>= 10000` 字符：入队异步任务；任务完成后 `long_term_memory` 更新，且近期窗口仅剩 **20 轮** 成对消息、更早删除。
- 再次累积到 `>= 10000`：再次合并「旧长记忆 + 当前全量 recent」生成新长记忆并再次裁 20 轮（可用手工构造消息或集成测试模拟）。
- 并发快速发消息：不出现同一角色长记忆或消息表写乱序（至少单写者串行）。

**给 Cursor 的指令：**
请阅读 PHASE5_DESIGN.md **§2.3** 与步骤 5.5本节，完成步骤 5.5：

1. 实现字符计数与触发判断；实现异步入队（不与主图阻塞耦合）
2. 实现异步任务内：`read_prompt("memory_summary_prompt.md")`、占位符替换、`call_llm`、写回 `long_term_memory`、裁剪并删除旧 `recent_messages` 对应持久化数据
3. 为 `should_update_memory` 写清语义并在测试中断言
4. 写测试：未达阈值 / 首次达阈值 / 第二次达阈值 / 并发或串行写回（按你选的实现最小集）

**实现摘要（仓库，与上文对齐）：**

- `prompt_template.py`：`state_to_replacement_map` / `apply_template_placeholders`（与 `evaluate_state` 共用）。
- `memory_manager.py`：`recent_messages` 字符和与阈值 10000；仅写 `should_update_memory`。
- `memory_compression.py`：`run_long_memory_compression_job`（`read_prompt("memory_summary_prompt.md")`、占位符、`call_llm(..., model=get_summary_model())`、写 `Character.long_term_memory`、删消息仅保留最后 20 对）、`enqueue_long_memory_compression_after_graph`；`character_id` 级 `threading.Lock` 防并发写。
- `llm_client.py`：摘要使用辅助模型；`call_llm` / `acall_llm` 支持可选 `model`。
- `POST /characters/{id}/chat`：`graph.invoke` 完成后若 `should_update_memory` 为真则 `enqueue_long_memory_compression_after_graph`（见 `character_service.chat_with_character`）。
- 测试：`test_memory_manager.py`、`test_memory_compression.py`（mock `call_llm`、patch `SessionLocal` 绑定内存 SQLite）。

---

### 步骤 5.6 — 条件路由与结局判定 (ending_judge)

**目标：**
在 StateGraph 中加入条件边，表白意图跳转结局判定节点，其他意图走记忆管理。

**要做的事：**

A. 条件路由函数

- `intent in ("表白", "角色表白")` → `ending_judge`；否则 → `memory_manager`。
- **本步（5.6）**：仅用户主动表白由 `evaluate_state` 产出 `intent="表白"`（见 `evaluate_state_prompt.md` 定稿）；`"角色表白"` 为预留枚举值，路由已兼容，语义识别待扩展（见下文「终局触发扩展」）。

示意：

```python
def route_after_evaluation(state: ConversationState) -> str:
    if state.get("intent") in ("表白", "角色表白"):
        return "ending_judge"
    return "memory_manager"
```

B. 修改 graph.py

- 将 evaluate_state 之后的固定边改为条件边
- 条件边指向 ending_judge 或 memory_manager
- ending_judge 和 memory_manager 之后都连接到 save_and_respond

C. ending_judge 节点实现

- 根据本轮 `character_reply` 语义主判，再用 `new_heartbeat_score` 和 `new_hidden_state` 做兜底：
HE（好结局）：角色明确接受关系，或给出明显默认接受（如“那我们试试吧”“好，我们认真在一起看看”）；若 trust/comfort 明显过低或 alertness 过高，则降级为 NE。
NE（普通结局）：角色表达喜欢但还没准备好、希望慢一点、暂时不确认关系、先继续相处；NE 不结束角色线。
BE（坏结局）：角色明确拒绝、拉开距离、表达强烈不适或关系断裂；高警惕或极低心动值可作为兜底。
- **结局评价用正文**：仅从 `backend/app/engine/prompts/ending_judge_prompt.md` 经 `read_prompt` 读取；占位符与注入变量以该 `.md` 为准（典型输入包括：`ending_result`、结构化或序列化后的 `new_hidden_state`、`new_heartbeat_score`、`long_term_memory`、以及角色侧人设相关字段等，由实现从 state 映射）。
- **输出**：模型返回的**纯文本**评价，写入 `ending_evaluation`；长度与语气约束由 `ending_judge_prompt.md` 约定。
- 将 `ending_result` 和 `ending_evaluation` 写入 state

**验收标准：**

- 非表白意图 → 走 memory_manager 路径
- 表白 + 高心动值 → 返回 HE
- 表白 + 低心动值 → 返回 BE
- 表白 + 中间心动值 → 返回 NE
- 结局评价文本非空且风格合理

**给 Cursor 的指令：**
请阅读 PHASE5_DESIGN.md 第 3 节与步骤 5.6 本节，完成步骤 5.6：

1. 在 graph.py 中把 evaluate_state 后的边改为条件边
2. 实现 route_after_evaluation 路由函数
3. 在 ending_judge.py 中实现结局判定逻辑和评价生成
4. 写测试：分别模拟 HE/BE/NE 三种结局

**实现摘要（仓库，与上文对齐）：**

- `backend/app/engine/graph.py`：`route_after_evaluation`；`add_conditional_edges`；`ending_judge` 与 `memory_manager` 均汇入 `save_and_respond`。
- `backend/app/engine/nodes/ending_judge.py`：`classify_ending_result`（先 BE、再 HE、再 NE）；`read_prompt("ending_judge_prompt.md")` + `prompt_template` + `call_llm`；空模板或空模型返回时用短占位「（评价暂缺）」。
- 测试：`test_ending_judge.py`（阈值与评价）；`test_graph_routing.py`（分支与 invoke）；`test_graph_skeleton` 回归非表白路径。

**终局触发扩展（待实现，仅说明不写代码）**

- **a) 角色主动表白**：`intent` 使用 **`角色表白`**；`route_after_evaluation` 已与 `"表白"` 一并路由至 `ending_judge`。当角色本轮回复明确主动确认关系或明显默认接受关系时，本轮直接进入终局判定，不等待用户下一轮确认。
- **b) 时间到期强制终局**：见根目录 [`TIME_SYSTEM_PLAN.md`](TIME_SYSTEM_PLAN.md)。推荐在 **`load_context` 之后**增加可选 `time_gate` 节点（或等价检查点）：此时 state 已带 `character_id` 与 DB 加载结果，便于读取会话时钟/累计时长等；与 `route_after_evaluation` **正交**（时间终局可走独立分支或复用 `ending_judge` 的不同入口），待时间系统选型后再实现。

---

### 步骤 5.7 — 持久化节点 (save_and_respond) + 端到端集成

**目标：**
实现 save_and_respond 节点，将本轮结果写入 DB；
将 LangGraph 图接入 FastAPI `/chat` 接口，跑通完整链路。

**实现摘要（仓库，与 v3 计划对齐）：**

- `save_and_respond.py`：独立 `SessionLocal` 写两条 `Message`（user + character **同** `round_number`）；`persisted_round = user_message_count + 1`（与 `load_context` 的 user 条数一致）；回写 `hidden_state_snapshot`、`heartbeat_score`；若 state 含 `ending_result` 则记录评价，其中仅 `HE` / `BE` 设置 `is_ended` + `status=ended`，`NE` 允许继续聊天；返回 **`persisted_*`**（含 **`persisted_*_at` 为 `datetime`**）。**技术债**：与路由 `get_db` 非同事务；同角色并发可能撞同一 `persisted_round`（可选 per-character 锁或 DB 唯一约束 + 重试）。
- `prompt_template.state_to_replacement_map`：**排除** `persisted_` 前缀键，避免回执进模板。
- `load_context`：`recent_messages` 中角色侧 `role` 为 **`character`**（与 `MessageRole` 一致）；`message_token_budget` 在调用豆包前将 `character` 映射为 OpenAI 的 `assistant`。
- `character_service.chat_with_character`：终局后 **409**；`invoke` → 按 `persisted_*` + `result` 组装 `CharacterChatResponse`；**禁止**用 `ORDER BY created_at LIMIT 2` 推断消息。
- `chat_with_character_mock`：保留，同轮同 `round_number`，便于脚本；路由已走正式链路。

**API 返回格式（`CharacterChatResponse`，正式字段名为 `assistant_message`，无 `reply`）：**

```json
{
  "assistant_message": "角色本轮回复全文",
  "user_message": {
    "id": "uuid",
    "role": "user",
    "content": "string",
    "round_number": 12,
    "created_at": "2026-01-01T00:00:00Z"
  },
  "assistant_message_item": {
    "id": "uuid",
    "role": "character",
    "content": "string",
    "round_number": 12,
    "created_at": "2026-01-01T00:00:00Z"
  },
  "heartbeat_score": 65,
  "round": 12,
  "ending": null
}
```

表白结局时 `ending` 为 `{ "result": "HE|BE|NE", "evaluation": "评价正文" }`。

**验收标准（当前 MVP）：**

- `POST /chat`：`graph.invoke` + `save_and_respond` 真落库；响应与按 id 读库一致（见 `tests/api/test_character_chat_graph.py`）。
- 终局后再次发消息 → **409**。
- `python -m pytest tests/` 全绿；长链路 10 轮 / 表白结局可后续补测或人工联调。

**给 Cursor 的指令（已完成项摘要）：**

1. `save_and_respond.py`：双消息、快照、心动、`persisted_*`。
2. `/chat`：`chat_with_character` + `enqueue_long_memory_compression_after_graph`。
3. 响应模型与前端类型：`role` 使用 **`character`**；扩展 `heartbeat_score` / `round` / `ending`。

---

## 5. 实施顺序与依赖关系

步骤 5.1（骨架）    → 无依赖，直接开始
步骤 5.2（上下文加载）→ 依赖 5.1
步骤 5.3（回复生成）  → 依赖 5.2（需要 llm_client 和 load_context）
步骤 5.4（状态评估）  → 依赖 5.3（需要 character_reply）
步骤 5.5（记忆管理）  → 依赖 5.2 / 5.4（需要已加载的 recent_messages；路由上在 evaluate_state 之后；触发条件不依赖 delta）
步骤 5.6（结局判定）  → 依赖 5.4（需要 intent 和 new_hidden_state）
步骤 5.7（集成）     → 依赖 5.5 + 5.6（所有节点就绪）

严格按 5.1 → 5.2 → 5.3 → 5.4 → 5.5 → 5.6 → 5.7 顺序执行。
每步做完跑通测试再进下一步，不要跳步。

---

## 6. 技术栈与依赖

- LangGraph: 状态图编排
- OpenAI Python SDK: 调用豆包 API（兼容 OpenAI 格式）
- 模型: doubao-seed-2-0-lite-260215（上下文窗口以火山方舟接入点/文档为准；代码默认见 `llm_client.DEFAULT_CHAT_MODEL`）
- FastAPI: HTTP 接口
- SQLite: 数据持久化
- pytest + pytest-asyncio: 测试

需要安装的包：

- langgraph
- openai
- tiktoken（可选，用于精确 token 计算）

配置：

正常玩法下玩家不需要碰环境变量——网页向导（`/setup`）会把配置写进
`backend/data/llm_config.json`。以下环境变量供服务器部署 / 自动化场景使用，优先级高于该文件：

- `LLM_BASE_URL`：OpenAI 兼容接口地址
- `LLM_API_KEY`：API Key
- `LLM_MODEL`：角色回复使用的模型
- `LLM_AUX_MODEL`：**可选**。状态评估 / 结局评价 / 长记忆摘要使用的模型；留空则与 `LLM_MODEL` 相同
- `DATABASE_URL`：**可选**。未设置时使用 `backend/data/app.db`

`web_search_supported` 不由用户填写，而是保存配置时由 `app/services/llm_probe_service.py`
实测探测后落盘——方舟还要求为 API Key 单独开通「联网内容插件」，光看 Base URL 判断不出来。

---

## 7. 风险与注意事项

7.1 豆包 API 返回格式不稳定
状态评估节点要求 LLM 返回 JSON，但 LLM 可能返回带 markdown 包裹或多余文本的 JSON。
必须实现 JSON 提取和容错逻辑，解析失败时使用默认值不崩溃。

7.2 隐藏状态漂移
多轮对话后五维状态可能都漂向极端值（全 100 或全 0）。
需要在 evaluate_state 中加入衰减机制：每轮对远离 50 的值施加微小的回归力；**语义层**对 delta 合理区间的说明由 `evaluate_state_prompt.md` 承担（定稿后由维护者写入该文件），工程侧仍保留对 delta 的 clamp 等数值护栏。

7.3 记忆摘要质量
摘要可能丢失关键信息或产生幻觉。
**摘要应保留事实、控制幻觉**等语义要求由 `memory_summary_prompt.md` 承担；长期若需精确检索可再引入向量数据库等方案。

7.4 并发问题
用户快速连续发送消息时，可能出现状态竞争。
MVP 阶段先用简单的锁（per character_id），后续再优化。

7.5 成本控制
每轮对话固定约 **2 次** LLM（回复 + 评估）。长记忆摘要为 **异步** 且仅在 `recent_messages` 字符总和 **≥ 10000** 时额外触发，**不是**每轮三次调用。
以豆包 Seed-Character 价格（输入 ¥0.8/M，输出 ¥2/M）估算时，应把「压缩摘要」按稀疏事件摊入总成本。

7.6 终局触发扩展（待实现）
与步骤 5.6 末尾「终局触发扩展」一致：**角色主动表白**（`intent="角色表白"` + `evaluate_state_prompt.md` 规则）、**时间到期强制终局**（参考 `TIME_SYSTEM_PLAN.md`，在 `load_context` 后预留 `time_gate` 与现有条件路由正交）。不在本节展开实现代码。