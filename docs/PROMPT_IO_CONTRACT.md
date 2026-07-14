# Prompt I/O Contract Spec（心动实验室）

本文档描述 `backend/app/engine/prompts/` 下 **7 个** `.md` 提示词文件与后端代码之间的 **输入 / 输出契约**，依据 **当前仓库实现** 编写；与产品文档不一致处见文末「设计 vs 实现差异」。

---

## 全局约定

### `read_prompt`（[`backend/app/engine/prompts/loader.py`](backend/app/engine/prompts/loader.py)）

- 路径：`backend/app/engine/prompts/{filename}`，UTF-8。
- 文件不存在：**返回空字符串** `""`（不抛错）。
- 返回值：读入全文后 **`.strip()`** 去掉首尾空白。

### 占位符模板引擎（[`backend/app/engine/prompt_template.py`](backend/app/engine/prompt_template.py)）

- **仅当**调用方显式执行 `apply_template_placeholders(template, state_to_replacement_map(state))` 时，才对模板中的 `{identifier}` 做替换。
- `identifier` 正则：`[a-zA-Z_][a-zA-Z0-9_]*`（**不支持** `a.b` 等嵌套键名）。
- 替换表来自 `state_to_replacement_map(state)`：
  - 遍历 [`ConversationState`](backend/app/engine/state.py) 的**每一项键值**；
  - **排除**所有以 `persisted_` 开头的键（持久化回执，不进模板、减少噪音）；
  - 值转字符串规则：`None` → `""`；`bool` → `true`/`false`；数值 → 十进制字符串；`dict`/`list` → `json.dumps(..., ensure_ascii=False)`；其余 → `str(value)`。
  - 模板中出现 `{foo}` 而替换表无 `foo`：**替换为空串**。
- **未使用** `str.format`，避免模板内 JSON 花括号与 `.format` 冲突。

### `ConversationState` 中可被占位符引用的键（理论全集）

以下键在走 `state_to_replacement_map` 时**可能**出现在替换表中（若 state 含该键且非 `persisted_*`）：

| 键 | 类型（语义） |
|----|----------------|
| `character_id` | `str` |
| `user_message` | `str` |
| `current_round` | `int` |
| `system_prompt` | `str`（来自 `load_context` 读入的 `system_prompt.md` 全文；与 `generate_reply` 实际使用的 system 同源内容，但见各小节说明） |
| `persona_prompt` | `str` |
| `hidden_state` | `HiddenState` → JSON 字符串 |
| `relationship_state_prompt` | `str`（由工程规则把五维翻译成稳定关系提示） |
| `long_term_memory` | `str` |
| `recent_messages` | `list[dict]` → JSON 字符串 |
| `character_reply` | `str` |
| `intent` | `str` |
| `state_changes` | `StateChanges` → JSON 字符串 |
| `new_hidden_state` | `HiddenState` → JSON 字符串 |
| `new_heartbeat_score` | `float` |
| `should_update_memory` | `bool` |
| `ending_result` | `str \| None` → 模板中为字符串化 |
| `ending_evaluation` | `str \| None` |

**不在替换表中**：`persisted_user_message_id`、`persisted_assistant_message_id`、`persisted_round`、`persisted_heartbeat_score`、`persisted_user_message_at`、`persisted_assistant_message_at`。

### 当前实现状态（三档）

每个 prompt 小节第 1 节会标明其一：

| 档位 | 含义 |
|------|------|
| **已生效** | 代码按设计路径读取该文件，并参与 LLM 调用或下游逻辑（含条件分支上的节点）。 |
| **占位实现** | 可能被 `read_prompt` 触及，但**不参与有效推理**，或输出被代码**固定覆盖**（如始终返回空串）；契约需区分「现状」与「未来接入」。 |
| **未接线** | 业务代码路径中**没有**对该文件的 `read_prompt` 或模板注入；仅有占位文件或规划注释。 |

### 主链与异步压缩（便于对照「调用时机」）

- LangGraph（[`backend/app/engine/graph.py`](backend/app/engine/graph.py)）：`START → load_context → generate_reply → evaluate_state →` 条件边（`intent ∈ {"表白","角色表白"}` → `ending_judge`，否则 `memory_manager`）`→ save_and_respond → END`。
- 长记忆压缩：图执行完毕且 `should_update_memory` 为真时，由 API 入队 `BackgroundTasks`（[`enqueue_long_memory_compression_after_graph`](backend/app/engine/memory_compression.py)），**不在图内 await**。

### `read_prompt` 覆盖自检（仓库 `app` 包内）

以下调用与 7 个文件对应：

- `system_prompt.md` ← `load_context.py`、`generate_reply.py`
- `evaluate_state_prompt.md` ← `evaluate_state.py`
- `ending_judge_prompt.md` ← `ending_judge.py`
- `memory_summary_prompt.md` ← `memory_compression.py`
- `persona_generator_prompt.md` ← `persona_generator.py`
- `character_creation_chat_prompt.md` ← [`persona_service.handle_persona_chat`](backend/app/services/persona_service.py)
- `character_creation_extract_prompt.md` ← [`persona_service.confirm_generate_persona`](backend/app/services/persona_service.py)

---

## 1. `system_prompt.md`

### 1. 基本信息

- **文件名**：`system_prompt.md`
- **当前实现状态**：**已生效**
- **所属节点 / 调用位置**：
  - [`load_context`](backend/app/engine/nodes/load_context.py)：读入后写入 `state["system_prompt"]`。
  - [`generate_reply`](backend/app/engine/nodes/generate_reply.py) / [`stream_character_reply_tokens`](backend/app/engine/nodes/generate_reply.py)：再次 `read_prompt`，将正文作为 **第一条 `system` 消息** 参与 [`build_truncated_llm_messages`](backend/app/engine/message_token_budget.py)。
- **调用时机**：每轮用户发消息、图进入 `load_context` 时写入 state；进入 `generate_reply`（或 SSE 流式）组装当轮对话 **角色回复** 模型请求时再次读取。
- **是否主链关键路径**：**是**（每轮角色回复必经）。若文件为空，`generate_reply` 仍会组装 messages，但第一条 system 为空串并打日志告警。

### 2. 输入契约

- **定性**：本文件为 **静态通用文本 prompt**。
  - **不支持**占位符，**不做** `apply_template_placeholders` 或任何模板替换。
  - **没有**与本文件绑定的「动态输入字段清单」；会话动态信息由同一次 `call_llm` 的 **后续** `system` / `user` 消息携带（见 [`build_messages_phase52`](backend/app/engine/message_token_budget.py)：persona、隐藏状态 JSON、长期记忆、历史消息、本轮用户句）。
- **代码实际传入本文件的「原始输入」**：无。仅 `read_prompt("system_prompt.md")`，无额外参数。
- **来源**：磁盘模板文件，非 DB、非 API body（除间接意义上「用户触发了一轮对话」）。
- **`.md` 中可用占位符**：**无**（勿写 `{identifier}`：不会被替换，且可能干扰模型阅读）。
- **不建议在正文中模拟的「伪字段」**：避免写依赖每轮替换才能正确的句子；应写通用规则，把「当前用户句」交给最后一条 user 消息。

### 3. 输出契约

- **消费方**：聊天补全 API 中 **`role: system` 的第一条消息**的 `content`。
- **输出类型**：**自然语言**（整文件即一段或多段连续文本，代码不拆分章节）。
- **是否允许 Markdown**：代码不校验；由产品与模型约束。
- **是否允许多段 / 标题 / 列表**：代码不校验；注意与后续 system 消息拼接后的总长度与 token 预算（见 `message_token_budget`）。

> 注意：本文件的「输出」指 **进入模型的 system 文本**，不是模型返回值。模型当轮输出是 **角色回复**（下一条 assistant），由 `generate_reply` 写入 `character_reply`。

### 4. 当前代码解析方式

- 无 JSON 解析。
- 无 markdown code fence 剥离。
- 无字段缺失逻辑（整段字符串直接使用）。
- 异常 / 空文件：空串参与组装；`generate_reply` 对**模型返回**的回复做 `.strip()`（不作用于本文件）。

### 5. 写 prompt 时必须遵守的约束

- **不得**使用 `{placeholder}` 形态（无引擎替换）。
- 保持 **通用**：不要写死某个角色名或某次对话专有事实（角色专有内容应在 `persona_prompt` 与历史消息中）。
- 若需约束模型输出形态（长度、人称），在此静态层写清即可。

### 6. 建议

- **风格**：短而稳的全局行为规则（安全、人称、节奏）优于冗长设定；细节人设放在 DB `persona_prompt`。
- **易踩坑**：误以为 `{character_id}` 等会被替换；与 `state["system_prompt"]` 重复维护两份认知——实际上 **角色回复路径以文件再读为准**，与 state 中字段内容应保持一致源文件。

---

## 2. `evaluate_state_prompt.md`

### 1. 基本信息

- **文件名**：`evaluate_state_prompt.md`
- **当前实现状态**：**已生效**
- **所属节点 / 调用位置**：[`evaluate_state`](backend/app/engine/nodes/evaluate_state.py)
- **调用时机**：每轮在 **`generate_reply` 之后**；此时 `state` 已含 DB 加载的上下文及本轮 `character_reply`。
- **是否主链关键路径**：**是**（每轮必经）。模板经替换后若为空，则 **跳过 LLM**，使用默认 intent 与零 delta（见第 4 节）。

### 2. 输入契约

- **代码实际传入 LLM 的方式**：单条消息 `[{"role":"user","content": user_content}]`，其中 `user_content = apply_template_placeholders(read_prompt(...), state_to_replacement_map(state))`。
- **原始输入来源**：整份 `ConversationState`（除 `persisted_*`）序列化进替换表；关键字段来源概览：
  - **API / 图入口**：`character_id`、`user_message`。
  - **DB（经 `load_context`）**：`persona_prompt`、`hidden_state`、`relationship_state_prompt`、`long_term_memory`、`recent_messages`、`current_round`、`system_prompt`。
  - **前序节点**：`character_reply`（`generate_reply`）。
  - **仍可能为初始值或未同步**：`intent`、`state_changes`、`new_hidden_state`、`new_heartbeat_score` 等在首轮评估前多为 `minimal_conversation_state` 的默认值；`new_hidden_state` **未必**已与本轮 `hidden_state`（DB）对齐，模板中若同时引用二者需注意语义（见第 6 节）。
- **`.md` 中可用占位符**：凡 `ConversationState` 非 `persisted_*` 键名均可写 `{键名}`；常用建议：`user_message`、`character_reply`、`persona_prompt`、`hidden_state`、`long_term_memory`、`recent_messages`（大段 JSON）、`current_round`。
- **必有占位符**：无硬性要求；若模板为空则不调 LLM。
- **不建议 prompt 依赖的字段**：`system_prompt`（与评估角色无关且冗长）、过大的 `recent_messages` 全文（易超上下文）；可按需让模板只引用最近片段（需在 `.md` 中自行说明裁剪策略，代码侧**不会**自动裁剪模板结果）。

### 3. 输出契约

- **输出类型**：**严格 JSON 对象**（根级 **object**）。工程上允许外层被 markdown code fence 包裹（见第 4 节剥离）。
- **字段定义**（解析见 `parse_evaluation_llm_output`）：

| 字段路径 | 类型 | 必填 | 说明 |
|-----------|------|------|------|
| `intent` | `string` | 可选 | 非空字符串则 trim 使用；否则默认 **`"闲聊"`** |
| `state_changes` | `object` | 可选 | 若非 object，四维 delta 按 0 |
| `state_changes.comfort_delta` | `number` \| 可解析数字的 `string` | 可选 | clamp 到 **`[-10, 10]`** |
| `state_changes.interest_delta` | 同上 | 可选 | 同上 |
| `state_changes.trust_delta` | 同上 | 可选 | 同上 |
| `state_changes.alertness_delta` | 同上 | 可选 | 同上 |
| `state_changes.reason` | `string` | 可选 | 非 string 则 `""` |

- **枚举 / 路由硬编码**：图条件边仅识别 **`intent == "表白"`** 或 **`intent == "角色表白"`**（精确字符串）进入 [`ending_judge`](backend/app/engine/nodes/ending_judge.py)。其余 intent 走 `memory_manager`。**不在代码中**维护更多 intent 枚举，但 `.md` 内应自洽列出允许标签并与上述两值对齐。
- **`baseline_compatibility`**：不出现于 `state_changes`；新隐藏状态由 `apply_deltas_to_hidden` 只改四维，`baseline_compatibility` **保持本轮 `hidden_state` 原值**。

**示例 JSON**（结构示意）：

```json
{
  "intent": "闲聊",
  "state_changes": {
    "comfort_delta": 2.5,
    "interest_delta": 0,
    "trust_delta": 1,
    "alertness_delta": -0.5,
    "reason": "用户语气友好"
  }
}
```

### 4. 当前代码解析方式

- 读取：`raw = call_llm(..., temperature=0.3, stream=False)` → `str`。
- **JSON**：`stripped = _strip_markdown_code_fence(raw)`；`json.loads(stripped)`。
- **strip fence**：若整体以 ``` 开头，去掉首行与末尾围栏行（支持 ```json）。
- **根非 object**：整轮按解析失败处理。
- **缺字段**：`intent` 默认 `"闲聊"`；`state_changes` 缺失或非 dict → 全 delta `0`，`reason` `""`。
- **多字段 / 未知字段**：忽略未列出的顶层键；`state_changes` 内未知键忽略。
- **异常 / 解析失败 fallback**：`intent="闲聊"`，全 delta `0`，`reason=""`；仍计算 `new_hidden_state = apply_deltas_to_hidden(hidden_state, ...)`（即不变）与 `new_heartbeat_score`。
- **模板为空**：不调 LLM，同上默认。

### 5. 写 prompt 时必须遵守的约束

- 模型最终输出应 **仅为可解析的 JSON**（或带 fence，因会被剥离）；避免 JSON 前大段自然语言前缀导致 `json.loads` 失败。
- **不要**输出解释性前缀（如「好的，分析如下：」）除非能确保剥离后仍以 `{` 开头。
- `intent` 为 **`"表白"`** / **`"角色表白"`** 时须谨慎：会触发结局分支与额外 LLM。
- 避免在 JSON 外夹杂第二段文本。

### 6. 建议

- **风格**：冷启动、短指令 + 清晰字段说明 + 小示例。
- **易踩坑**：`recent_messages` 占位符展开为 **整表 JSON**，极长；`intent` 字符串与 `graph.py` **必须完全一致**；四维 delta 超出 ±10 会被硬截断，reason 无法反向解释截断结果。

---

## 3. `ending_judge_prompt.md`

### 1. 基本信息

- **文件名**：`ending_judge_prompt.md`
- **当前实现状态**：**已生效**
- **所属节点 / 调用位置**：[`ending_judge`](backend/app/engine/nodes/ending_judge.py)
- **调用时机**：**仅当** `evaluate_state` 之后路由判定 `intent ∈ {"表白", "角色表白"}`。
- **是否主链关键路径**：**条件关键**（非表白轮永不调用）。`ending_result`（`BE`/`HE`/`NE`）由 **规则** [`classify_ending_result`](backend/app/engine/nodes/ending_judge.py) 决定，**不**由本 prompt 的模型输出解析。

### 2. 输入契约

- **LLM 调用形式**：`[{"role":"user","content": user_content}]`。
- **`user_content`**：`apply_template_placeholders(read_prompt(...), state_to_replacement_map(merged_state))`。
- **`merged_state`**：在模板替换前将 **`ending_result`** 写入副本（规则已算好），故模板可用 `{ending_result}` 展示 **`BE` / `HE` / `NE`**。
- **数据来源**：与 `evaluate_state` 相同的 `ConversationState` 字段集；重点含 `new_heartbeat_score`、`new_hidden_state`、`character_reply`、`user_message`、`persona_prompt`、`long_term_memory`、`recent_messages` 等。
- **占位符**：同「全局」非 `persisted_*` 键；**推荐**包含 `ending_result`、`new_heartbeat_score`、`new_hidden_state`、`character_reply`、`user_message`。
- **必有**：无；模板空则不调 LLM，`ending_evaluation` 为 **`"（评价暂缺）"`**。

### 3. 输出契约

- **输出类型**：**自然语言，单段文本**（代码整段 `strip()` 存库 / 返回）。
- **消费方**：API 响应 [`EndingPayload.evaluation`](backend/app/schemas/character.py)（经 [`character_service._build_chat_response_from_merged_state`](backend/app/services/character_service.py)）；终局时随 `assistant_message` 等一并返回。
- **Markdown / 多段**：代码不校验；产品可约定为纯文本短评。

### 4. 当前代码解析方式

- **无** `json.loads`；**无** code fence 专门剥离（整段当正文）。
- 空或仅空白：`ending_evaluation = "（评价暂缺）"`。
- `ending_result` **不**从模型输出读取，仅以规则结果为准。

### 5. 写 prompt 时必须遵守的约束

- 模型输出应为 **可直接展示给用户的评价正文**，避免输出 JSON。
- 不要在正文要求用户「再选一次 BE/HE/NE」——类型已由服务端固定。
- 避免暴露内部规则细节（若产品要求「沉浸感」）。

### 6. 建议

- **风格**：第三人称或「旁白式」短评，与结局类型 `ending_result` 情绪一致。
- **易踩坑**：误以为要模型输出结局代码；实际上 **只需评价**；模板未含 `ending_result` 时模型不知道服务端判定结果。

---

## 4. `memory_summary_prompt.md`

### 1. 基本信息

- **文件名**：`memory_summary_prompt.md`
- **当前实现状态**：**已生效**
- **所属节点 / 调用位置**：[`run_long_memory_compression_job`](backend/app/engine/memory_compression.py)
- **调用时机**：`memory_manager` 将 `should_update_memory` 置为真后，API 在图完成后 **异步** 入队；任务内读 DB 全量消息，再调 LLM 生成摘要，写回 `Character.long_term_memory` 并裁剪旧消息（保留最近 **20 对** user→character，见 `PAIR_KEEP`）。
- **是否主链关键路径**：**异步关键**（不阻塞当轮 HTTP 完成；仅当字符阈值触发）。

### 2. 输入契约

- **状态构造**：[`_build_state_for_template`](backend/app/engine/memory_compression.py)：`character_id`、`long_term_memory`、`recent_messages` 来自 DB；其余键来自 **`minimal_conversation_state()`** 默认值。
- **LLM 消息**：`[{"role":"user","content": apply_template_placeholders(...)}]`。
- **占位符**：理论上可用全部非 `persisted_*` 键；**有语义**的主要是 `character_id`、`long_term_memory`、`recent_messages`（通常极大）、`current_round` 等。**常为默认空或无意义**：`character_reply`、`user_message`、`persona_prompt`（空串）、`hidden_state`（默认 50 全维）等——**不建议**在摘要任务中依赖这些占位内容代表「当前真实会话态」。
- **来源**：DB `Character` + `Message` 表，非当轮 API body。

### 3. 输出契约

- **输出类型**：**自然语言**（整段摘要）。
- **消费方**：写回 **`Character.long_term_memory`**（`.strip()` 后赋值）；随后配合消息删除策略。
- **Markdown**：代码不校验。

### 4. 当前代码解析方式

- `new_summary = call_llm(..., temperature=0.4, model=get_summary_model()).strip()`。
- **无** JSON 解析；**无** fence 剥离。
- 模板为空：任务提前 return，**不**调 LLM、不改写 DB。

### 5. 写 prompt 时必须遵守的约束

- 输出应为 **摘要正文本身**，避免「以下是摘要：」等元话语过多（仍会写入 DB）。
- 避免输出仅 JSON（除非产品明确把长期记忆存为 JSON 字符串；当前字段语义为自然语言摘要）。

### 6. 建议

- **风格**：时间线清晰、人名与关系稳定指代、压缩掉寒暄重复。
- **易踩坑**：`recent_messages` JSON 超长；误用默认的 `persona_prompt` / `hidden_state` 占位；与 `evaluate_state` 模板混用同一套占位说明。

---

## 5. `persona_generator_prompt.md`

### 1. 基本信息

- **文件名**：`persona_generator_prompt.md`
- **当前实现状态**：**已接入**
- **所属节点 / 调用位置**：[`generate_persona_prompt`](backend/app/engine/persona_generator.py)，由 [`character_service.create_character`](backend/app/services/character_service.py) 在创建 `Character` 时调用。
- **调用时机**：用户通过 API 创建角色实例时。
- **是否主链关键路径**：**否**（对话主链不读此文件）。影响 **创建时** `Character.persona_prompt` 初值；生成失败或为空时，`load_context` 回退到从 `Persona` 表拼装人设文本。

### 2. 输入契约

- **代码实际行为**：`read_prompt("persona_generator_prompt.md")` 作为 system 指令，`character_info["extract_snapshot"]` 序列化为 user 输入，调用辅助链路 LLM。
- **`character_info` 字典键**（来自 `create_character`）：`persona_id`、`display_name`、`identity_summary`、`personality_summary`、`interests`、`chat_style`、`visible_background`、`hidden_initial_tendency`、`hidden_impression_baseline`、`hidden_key_judgment`、`hidden_pacing_tolerance`、`hidden_sensitivity_points`、`hidden_evolution_params`、`extract_snapshot`。
- **`.md` 可用占位符（现状）**：无占位符替换；写 `{foo}` 不会被替换。
- **来源**：`extract_snapshot`。

### 3. 输出契约（现状 vs 规划）

- **现状**：输出自然语言角色人设提示词，写入 `Character.persona_prompt`，供 `load_context` 优先于 `Persona` 表拼装使用。
- **长度约束**：提示词要求 2000 字符以内；代码侧若首次生成超过 2000 字符，会请求模型压缩重写一次，仍超限则返回空字符串并回退表拼装。

### 4. 当前代码解析方式

- 不解析结构化输出；仅对模型返回文本做 `.strip()` 与长度检查。超长时触发一次压缩重写，仍超长则回退为空字符串。

### 5. 写 prompt 时必须遵守的约束（未来接线时）

- 正文应保持短而明确，避免大段示例挤占上下文。
- 输出必须控制在 2000 字符以内；信息丰富时建议 600-1200 字符。
- 应避免与 `load_context._build_persona_prompt` 重复冲突；生成失败时才使用表拼装回退。

### 6. 建议

- **现状**：创建角色时会按模板生成 `persona_prompt`；失败或超长压缩失败时回退到表拼装。
- **易踩坑**：误以为 prompt 内 `{foo}` 会做占位符替换；本链路当前不做模板变量替换。

---

## 6. `character_creation_chat_prompt.md`

### 1. 基本信息

- **文件名**：`character_creation_chat_prompt.md`
- **当前实现状态**：**已生效**（助手自然语言）；右侧预览仍为 **`build_mock_persona_extract`**，「确认生成」后以 §7 静默抽取为准。
- **所属节点 / 调用位置**：[`persona_service.iter_persona_chat_sse_lines`](backend/app/services/persona_service.py)（[`POST /api/personas/chat/stream`](backend/app/api/routes/personas.py)，SSE）；[`persona_service.handle_persona_chat`](backend/app/services/persona_service.py)（[`POST /api/personas/chat`](backend/app/api/routes/personas.py)，兼容 JSON）；前端人设创建页使用 **`chat/stream`** 流式消费 **`token`** 帧，末帧 **`done`** 含完整 **`assistant_message`** 与 mock **`extract`**。
- **调用时机**：人设创建页每轮用户发送后（前端携带完整 `messages`，末条为 `user`）。
- **是否主链关键路径**：**否**（与人设创建链路绑定，非角色实例对话图）。

### 2. 输入契约（实现）

- **服务端拼装**：第一条 **`system`**：`read_prompt("character_creation_chat_prompt.md")`；其后按 **`payload.messages` 顺序**追加 `{"role": "user"|"assistant", "content": ...}`，与 OpenAI `messages` 一致；**不做**占位符模板替换。
- **来源**：API body [`PersonaChatRequest.messages`](backend/app/schemas/persona.py)。

### 3. 输出契约（实现）

- **类型**：自然语言字符串，作为响应字段 **`assistant_message`**；不要求 JSON。
- **预览**：同响应中的 **`extract`** 仍为启发式 mock；真结构化快照见 **`POST /api/personas/confirm-generate`**。

### 4. 当前代码解析方式

- **JSON**：`raw = call_llm(..., stream=False)` → `.strip()`；若为空则 **`RuntimeError`** → HTTP **502**。
- **SSE（`/chat/stream`）**：`call_llm(..., stream=True)` 逐段 yield **`{"type":"token","text":...}`**；结束后 yield **`{"type":"done", ...PersonaChatResponse}`**（与 [`character_service.iter_character_chat_sse_lines`](backend/app/services/character_service.py) 同类约定）。错误帧 **`type:error`**。

### 5. 写 prompt 时必须遵守的约束

- 与阶段 3 / mock 预览分流：**勿**依赖右侧字段反向注入（当前未注入）；确认路径仍以 §7 JSON 为准。

### 6. 建议

- 与 `character_creation_extract_prompt.md` 分工：**聊天引导** vs **静默结构化提取**。
- **易踩坑**：误以为右侧预览来自本链路模型输出（实为 `build_mock_persona_extract`，直至用户确认生成）。

---

## 7. `character_creation_extract_prompt.md`

### 1. 基本信息

- **文件名**：`character_creation_extract_prompt.md`
- **当前实现状态**：已接线（`POST /api/personas/confirm-generate`）
- **所属节点 / 调用位置**：[`persona_service.confirm_generate_persona`](backend/app/services/persona_service.py)，经 [`validate_and_normalize_persona_extract`](backend/app/engine/persona_extract_validator.py) 收口后入库。
- **调用时机**：人设创建页「确认生成」；输入为多轮对话转写字符串。
- **模型**：辅助模型（[`get_extract_model`](backend/app/engine/llm_client.py)）。
- **是否主链关键路径**：**否**。

### 2. 输入契约（实现）

- **服务端拼装**：[`persona_service._messages_to_extract_transcript`](backend/app/services/persona_service.py)：`用户：` / `人设助手：` 前缀的行文本，`messages` 顺序即时间顺序。

### 3. 输出契约（persona_extract_v0.6）

- **版本**：根字段 `schema_version`，固定字符串 **`"persona_extract_v0.6"`**。
- **顶层**：单个 JSON 对象，必须包含 **`schema_version`**、**`visible_layer`**、**`hidden_layer`**；不得省略字段（默认值规则见专项文档）。
- **语义**：`visible_layer` 仅客观事实与用户明确陈述；`hidden_layer` 可保守推断，内含 `inferred_core_profile`、`initial_relation_state`（含数值对象 `initial_hidden_state` 五键，默认 `50`）、`interaction_preferences`、`pacing_profile`、`evolution_tendency`、`distinctive_hidden_notes` 等嵌套结构。
- **权威定义**：键路径、枚举取值、`null` / `[]` / `"unknown"` / `50` 的分场景约定见 **[`docs/character_creation_extract_prompt输出格式及说明.md`](docs/character_creation_extract_prompt输出格式及说明.md)**（仓库根目录 `docs/`）。
- **Python 契约**：[`backend/app/schemas/persona_extract_v06.py`](backend/app/schemas/persona_extract_v06.py)（根模型 `PersonaExtractV06`）。
- **与持久层**：入库列 **`Personas.extract_snapshot`**（JSON）存完整快照；扁平列由 [`persona_extract_mapping.extract_to_persona_flat_fields`](backend/app/services/persona_extract_mapping.py) 派生。
- **格式**：模型不得输出 Markdown 代码围栏；服务端使用 [`strip_json_fence`](backend/app/services/persona_extract_parse.py) 容错解析。

### 4. 当前代码解析方式

- [`parse_persona_extract_v06`](backend/app/services/persona_extract_parse.py)：剥离可选 fence 后对 **`PersonaExtractV06`** 校验。

### 5. 写 prompt 时必须遵守的约束

- 静默 JSON：不向终端用户展示原始 JSON（见 `personas.py` 注释）；指令正文放在 [`backend/app/engine/prompts/character_creation_extract_prompt.md`](backend/app/engine/prompts/character_creation_extract_prompt.md)，字段契约以 **`docs/character_creation_extract_prompt输出格式及说明.md`** 为准。

### 6. 建议

- 抽取与聊天 **模型分离** 时可降本；映射入库时对齐 DB NOT NULL 与业务约束。
- **易踩坑**：与 `evaluate_state` 的输出 JSON **schema 完全不同**，勿复用其解析逻辑。
- **易踩坑**：抽取 JSON 键名与 [`persona.py`](backend/app/models/persona.py) 扁平列 **不一致**，须经映射层转换。

---

## 附录 A：各 prompt 调用参数（`call_llm`）

| 文件 | temperature | stream | model |
|------|-------------|--------|--------|
| `evaluate_state_prompt.md` | `0.3` | `False` | 默认聊天模型 [`get_chat_model`](backend/app/engine/llm_client.py) |
| `ending_judge_prompt.md` | `0.5` | `False` | 默认聊天模型 |
| `memory_summary_prompt.md` | `0.4` | `False` | [`get_summary_model()`](backend/app/engine/llm_client.py)（未配置环境变量时与聊天模型相同） |
| `system_prompt.md` | 不适用（非直接单次 user 模板调用） | — | 角色回复：`generate_reply` 使用 `0.8` |
| `character_creation_extract_prompt.md` | `0.25` | `False` | [`get_extract_model()`](backend/app/engine/llm_client.py)（辅助模型） |
| `character_creation_chat_prompt.md` | `0.8` | **`True`**（人设创建页 `POST /personas/chat/stream`）；兼容 JSON `POST /personas/chat` 为 **`False`** | [`get_chat_model()`](backend/app/engine/llm_client.py)（主模型） |

---

## 附录 B：设计 vs 实现差异（摘要）

| 主题 | 设计 / 文档倾向 | 当前实现 |
|------|-----------------|----------|
| `system_prompt.md` | PHASE5 称通用 system（§2.2） | **静态通用文本**，无占位符引擎；`generate_reply` 再次 `read_prompt`，与 state 中 `system_prompt` 同源文件、**非模板化**。 |
| `persona_generator_prompt.md` | 生成 `Character.persona_prompt` | **已接入**：创建角色时调用辅助模型；结果需 ≤2000 字符，超长会压缩重写一次，失败则回退表拼装。 |
| `character_creation_*` | 对话式创建 + 静默 **persona_extract_v0.6** JSON（见 `docs/character_creation_extract_prompt输出格式及说明.md`） | **`POST /api/personas/chat`**：助手正文走 **`character_creation_chat_prompt.md`** + `call_llm`，预览仍为 **`build_mock_persona_extract`**；**静默抽取并入库**：`POST /api/personas/confirm-generate`（`character_creation_extract_prompt.md` + 辅助模型），写入 **`personas.extract_snapshot`** + 扁平列。 |
| `ending_result` | 文档多处描述综合判定 | **规则函数** `classify_ending_result`；LLM 仅生成 **评价文本**。 |
| `evaluate_state` intent | 文档示例多种意图 | 仅 **`"表白"`/`"角色表白"`** 与图路由硬编码联动；其余值走普通路径。 |
| 记忆压缩并发 | 文档建议队列/版本 | MVP：**进程内** `threading.Lock` per `character_id`，持锁失败则跳过本次压缩。 |

---

*文档版本与仓库实现同步维护；修改 `read_prompt` 或解析逻辑时请同步更新本文档。*
