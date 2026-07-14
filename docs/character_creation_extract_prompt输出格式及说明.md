# 一、最终 JSON 输出格式 v0.6

下面这份可以直接作为标准默认结构入库。

```json
{
  "schema_version": "persona_extract_v0.6",
  "visible_layer": {
    "display_name": null,
    "name_user_specified": false,
    "basic_info": {
      "gender": null,
      "age_or_life_stage": null,
      "identity_role": null,
      "location_context": null,
      "relationship_status": null
    },
    "relationship_with_user": {
      "known_context": null,
      "interaction_frequency": null,
      "current_interaction_summary": null
    },
    "explicit_personality_notes": [],
    "explicit_interests": [],
    "explicit_preferences": {
      "likes": [],
      "dislikes": []
    },
    "observable_chat_style": {
      "message_length": null,
      "emoji_usage": null,
      "initiative_pattern": null,
      "expression_features": [],
      "typical_phrases": []
    },
    "visible_background": null
  },
  "hidden_layer": {
    "inferred_core_profile": {
      "summary": null,
      "profile_tags": [],
      "emotional_expression_style": "unknown",
      "social_energy_level": "unknown",
      "self_protection_level": "unknown",
      "intimacy_attitude": "unknown"
    },
    "initial_relation_state": {
      "initial_relation_tendency": null,
      "initial_impression_baseline": null,
      "initial_hidden_state": {
        "comfort": 50,
        "interest": 50,
        "trust": 50,
        "alertness": 50,
        "baseline_compatibility": 50
      }
    },
    "interaction_preferences": {
      "positive_interaction_cues": [],
      "negative_interaction_cues": [],
      "sensitive_topics": []
    },
    "pacing_profile": {
      "pacing_tolerance": "unknown",
      "boundary_sensitivity": "unknown",
      "confession_threshold": "unknown"
    },
    "evolution_tendency": {
      "comfort_growth_rate": "unknown",
      "trust_growth_rate": "unknown",
      "interest_volatility": "unknown",
      "alertness_trigger_level": "unknown",
      "repair_difficulty": "unknown",
      "negative_memory_weight": "unknown"
    },
    "distinctive_hidden_notes": []
  }
}
```

---

# 二、全局输出规则

模型输出时必须遵守：

```text
1. 必须输出完整 JSON 对象。
2. 不得省略任何字段。
3. 不得输出 Markdown code fence。
4. 不得输出 JSON 以外的解释文字。
5. 字段名必须严格一致。
6. visible_layer：字符串事实字段、以及文档标明可为 null 的可枚举字段（如 observable_chat_style 内对应项），无法判断时一律填 null；不得以 "unknown" 顶替可见层不确定内容。
7. 数组字段无法判断时填 []。
8. hidden_layer：文档规定默认值为 "unknown" 的必填枚举字符串字段，无法判断时填 "unknown"（见第五章对应小节）。
9. initial_hidden_state 五键数值无法判断时填 50。
10. visible_layer 只写明确事实，不写推断。
11. hidden_layer 可以做保守推断，但不得编造具体经历、心理创伤、恋爱史、家庭问题、强烈好恶。
```

---

# 三、字段格式说明

## 1. 顶层字段

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `schema_version` | string | 否 | `"persona_extract_v0.6"` | 固定版本号 |
| `visible_layer` | object | 否 | 完整默认对象 | 用户可见层 |
| `hidden_layer` | object | 否 | 完整默认对象 | 系统隐藏层 |

---

# 四、`visible_layer` 可见层

可见层原则：

```text
只放用户明确提供的信息，或聊天记录中客观可见的信息。
不要放模型推断出来的性格分析、关系判断、心理倾向。
```

---

## 4.1 `display_name`

| 字段 | 类型 | 可空 | 默认值 | 无法判断时 |
|---|---|---:|---|---|
| `display_name` | string / null | 是 | `null` | 填 `null` |

说明：

- 角色展示名。
- 如果用户没有提供，不要虚构姓名。
- 只有用户明确要求“帮我起个名字”时，才允许生成。

示例：

```json
"display_name": "林晓舟"
```

---

## 4.1.1 `name_user_specified`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `name_user_specified` | bool | 否 | `false` | display_name 是否由用户主动指定 |

判断规则：

填 `true` 的条件（满足任一）：
1. 用户在对话中主动说出了名字，如"叫她林知夏""名字就叫X"；
2. 用户明确确认了草案中的名字，如"就用这个名字""名字可以"；
3. 用户明确要求"帮我起个名字"后助手起了名字，用户随后明确确认。

填 `false` 的条件：
- display_name 来自助手草案，用户只整体接受（"就按这个来""可以""A"），未单独确认名字；
- display_name 为 `null`。

注意：display_name 为 `null` 时，name_user_specified 必须填 `false`。

---

## 4.2 `basic_info`

```json
"basic_info": {
  "gender": null,
  "age_or_life_stage": null,
  "identity_role": null,
  "location_context": null,
  "relationship_status": null
}
```

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `gender` | string / null | 是 | `null` | 性别或性别呈现 |
| `age_or_life_stage` | string / null | 是 | `null` | 年龄、年级、人生阶段 |
| `identity_role` | string / null | 是 | `null` | 身份角色，如学生、同事、网友 |
| `location_context` | string / null | 是 | `null` | 城市、本地、异地、校园等 |
| `relationship_status` | string / null | 是 | `null` | 单身、有对象、暧昧中等，必须有明确依据 |

示例：

```json
"basic_info": {
  "gender": "女",
  "age_or_life_stage": "大四",
  "identity_role": "学生",
  "location_context": "同城校园",
  "relationship_status": null
}
```

注意：

```text
不要根据聊天语气推断对方是否单身。
不要把“可能有好感”写进 relationship_status。
```

---

## 4.3 `relationship_with_user`

```json
"relationship_with_user": {
  "known_context": null,
  "interaction_frequency": null,
  "current_interaction_summary": null
}
```

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `known_context` | string / null | 是 | `null` | 用户和目标对象的已知关系 |
| `interaction_frequency` | string / null | 是 | `null` | 互动频率 |
| `current_interaction_summary` | string / null | 是 | `null` | 当前互动内容的客观摘要 |

示例：

```json
"relationship_with_user": {
  "known_context": "同学",
  "interaction_frequency": "最近偶尔聊天",
  "current_interaction_summary": "主要围绕课程、实习、毕业论文和日常生活交流"
}
```

注意：

```text
这里可以写“聊什么”“多久聊一次”“什么关系”。
不要写“她对用户有好感”“她在试探用户”这类推断。
```

---

## 4.4 `explicit_personality_notes`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `explicit_personality_notes` | string[] | 否 | `[]` | 用户明确描述过的性格信息 |

示例：

```json
"explicit_personality_notes": [
  "用户描述她比较慢热",
  "用户描述她不太主动"
]
```

注意：

```text
只有用户明确说“她慢热”“她外向”“她不太主动”时才放这里。
如果是模型从聊天记录推断出来的，不放这里。
推断内容放 hidden_layer.inferred_core_profile。
```

---

## 4.5 `explicit_interests`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `explicit_interests` | string[] | 否 | `[]` | 明确出现过的兴趣爱好 |

示例：

```json
"explicit_interests": [
  "摄影",
  "独立音乐",
  "悬疑小说"
]
```

无法判断：

```json
"explicit_interests": []
```

---

## 4.6 `explicit_preferences`

```json
"explicit_preferences": {
  "likes": [],
  "dislikes": []
}
```

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `likes` | string[] | 否 | `[]` | 明确喜欢的东西 |
| `dislikes` | string[] | 否 | `[]` | 明确不喜欢的东西 |

示例：

```json
"explicit_preferences": {
  "likes": [
    "安静的咖啡馆",
    "傍晚散步"
  ],
  "dislikes": [
    "被催促",
    "太吵的环境"
  ]
}
```

注意：

```text
“她可能不喜欢强推进”属于隐藏层推断，不放这里。
```

---

## 4.7 `observable_chat_style`

```json
"observable_chat_style": {
  "message_length": null,
  "emoji_usage": null,
  "initiative_pattern": null,
  "expression_features": [],
  "typical_phrases": []
}
```

这里仍然属于可见层，但必须是**客观观察**，不是心理分析。

---

### `message_length`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `message_length` | string / null | 是 | `null` | 见下方 |

可选值：

```text
very_short
short
short_to_medium
medium
long
mixed
```

含义：

| 值 | 含义 |
|---|---|
| `very_short` | 经常只回一两个字 |
| `short` | 多数回复较短 |
| `short_to_medium` | 短句为主，偶尔展开 |
| `medium` | 回复长度中等 |
| `long` | 经常长段表达 |
| `mixed` | 长短变化明显 |

无法判断：

```json
"message_length": null
```

---

### `emoji_usage`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `emoji_usage` | string / null | 是 | `null` | 见下方 |

可选值：

```text
none
low
medium
high
mixed
```

含义：

| 值 | 含义 |
|---|---|
| `none` | 基本不用表情 |
| `low` | 很少使用表情 |
| `medium` | 偶尔使用表情 |
| `high` | 经常使用表情 |
| `mixed` | 使用情况不稳定 |

无法判断：

```json
"emoji_usage": null
```

---

### `initiative_pattern`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `initiative_pattern` | string / null | 是 | `null` | 见下方 |

可选值：

```text
mostly_replying
balanced
sometimes_initiates
often_initiates
unclear
```

含义：

| 值 | 含义 |
|---|---|
| `mostly_replying` | 多数时候是回应用户 |
| `balanced` | 双方主动程度接近 |
| `sometimes_initiates` | 偶尔主动开启话题 |
| `often_initiates` | 经常主动找用户或开启话题 |
| `unclear` | 有材料，但无法判断主动模式 |

无法判断：

```json
"initiative_pattern": null
```

说明：

```text
如果完全没有聊天记录，填 null。
如果有聊天记录但主动性无法判断，填 "unclear"。
```

---

### `expression_features`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `expression_features` | string[] | 否 | `[]` | 客观可见的表达特征 |

示例：

```json
"expression_features": [
  "回复克制",
  "少用感叹号",
  "偶尔反问",
  "不常连续发送多条消息"
]
```

注意：

```text
可以写“回复克制”“少用表情”“偶尔反问”。
不要写“内心防御强”“对亲密关系害怕”。
```

---

### `typical_phrases`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `typical_phrases` | string[] | 否 | `[]` | 聊天记录中高频或有代表性的表达 |

示例：

```json
"typical_phrases": [
  "还好吧",
  "看情况",
  "也不是不行"
]
```

无聊天记录或无法提取：

```json
"typical_phrases": []
```

---

## 4.8 `visible_background`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `visible_background` | string / null | 是 | `null` | 明确可见的背景信息 |

示例：

```json
"visible_background": "最近在准备毕业论文和实习，生活压力较大。"
```

注意：

```text
只写明确背景。
不要写心理解释。
不要编造家庭、前任、创伤经历。
```

---

# 五、`hidden_layer` 隐藏层

隐藏层原则：

```text
可以基于上下文做保守推断。
只抓最关键、最有特点、最能影响长期关系模拟的信息。
不为了填满字段而编造细节。
```

---

## 5.1 `inferred_core_profile`

```json
"inferred_core_profile": {
  "summary": null,
  "profile_tags": [],
  "emotional_expression_style": "unknown",
  "social_energy_level": "unknown",
  "self_protection_level": "unknown",
  "intimacy_attitude": "unknown"
}
```

---

### `summary`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `summary` | string / null | 是 | `null` | 对隐藏人格倾向的保守总结 |

示例：

```json
"summary": "整体偏慢热和观察型，表达克制，需要稳定互动才会逐渐放松。"
```

无法判断：

```json
"summary": null
```

---

### `profile_tags`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `profile_tags` | string[] | 否 | `[]` | 推断出的核心人格标签 |

示例：

```json
"profile_tags": [
  "慢热",
  "表达克制",
  "边界感较强"
]
```

无法判断：

```json
"profile_tags": []
```

注意：

```text
这里可以放推断，但必须保守。
不要使用心理诊断式标签。
不要写“回避型依恋”“讨好型人格”“创伤型人格”等。
```

---

### `emotional_expression_style`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `emotional_expression_style` | string | 否 | `"unknown"` | 见下方 |

可选值：

```text
unknown
direct
reserved
playful
avoidant
warm
mixed
```

含义：

| 值 | 含义 |
|---|---|
| `unknown` | 无法判断 |
| `direct` | 直接表达型 |
| `reserved` | 克制表达型 |
| `playful` | 玩笑化表达型 |
| `avoidant` | 回避表达型 |
| `warm` | 温和表达型 |
| `mixed` | 混合型 |

无法判断：

```json
"emotional_expression_style": "unknown"
```

---

### `social_energy_level`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `social_energy_level` | string | 否 | `"unknown"` | 见下方 |

可选值：

```text
unknown
low
medium_low
medium
medium_high
high
```

无法判断：

```json
"social_energy_level": "unknown"
```

---

### `self_protection_level`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `self_protection_level` | string | 否 | `"unknown"` | 见下方 |

可选值：

```text
unknown
low
medium_low
medium
medium_high
high
```

无法判断：

```json
"self_protection_level": "unknown"
```

---

### `intimacy_attitude`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `intimacy_attitude` | string | 否 | `"unknown"` | 见下方 |

可选值：

```text
unknown
open
cautious
avoidant
warm_slow
mixed
```

含义：

| 值 | 含义 |
|---|---|
| `unknown` | 无法判断 |
| `open` | 对亲密关系较开放 |
| `cautious` | 谨慎，需要铺垫 |
| `avoidant` | 明显回避过快亲密 |
| `warm_slow` | 慢热但可稳定升温 |
| `mixed` | 信号混合，态度不稳定或材料矛盾 |

无法判断：

```json
"intimacy_attitude": "unknown"
```

---

## 5.2 `initial_relation_state`

```json
"initial_relation_state": {
  "initial_relation_tendency": null,
  "initial_impression_baseline": null,
  "initial_hidden_state": {
    "comfort": 50,
    "interest": 50,
    "trust": 50,
    "alertness": 50,
    "baseline_compatibility": 50
  }
}
```

---

### `initial_relation_tendency`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `initial_relation_tendency` | string / null | 是 | `null` | 初始关系倾向的自然语言描述 |

示例：

```json
"initial_relation_tendency": "中性偏谨慎：愿意继续交流，但不会快速进入亲密状态。"
```

无法判断：

```json
"initial_relation_tendency": null
```

注意：

```text
不要因为用户喜欢对方，就写成对方也有明显好感。
```

---

### `initial_impression_baseline`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `initial_impression_baseline` | string / null | 是 | `null` | 对用户的初始印象基线 |

示例：

```json
"initial_impression_baseline": "对用户保持基本友好，但仍处在观察阶段。"
```

无法判断：

```json
"initial_impression_baseline": null
```

---

### `initial_hidden_state`

| 字段 | 类型 | 可空 | 默认值 | 范围 | 说明 |
|---|---|---:|---:|---|---|
| `comfort` | number | 否 | `50` | `0-100` | 舒适感 |
| `interest` | number | 否 | `50` | `0-100` | 兴趣度 |
| `trust` | number | 否 | `50` | `0-100` | 信任感 |
| `alertness` | number | 否 | `50` | `0-100` | 警惕度，越高越谨慎 |
| `baseline_compatibility` | number | 否 | `50` | `0-100` | 初始匹配基线 |

无法判断时：

```json
"initial_hidden_state": {
  "comfort": 50,
  "interest": 50,
  "trust": 50,
  "alertness": 50,
  "baseline_compatibility": 50
}
```

数值原则：

```text
0-30：明显偏低
31-45：略低
46-55：中性
56-70：略高
71-100：明显偏高
```

警惕：

```text
不要把 interest 写高，除非材料里有明确的正向兴趣信号。
不要把 trust 写高，除非双方已有稳定关系基础。
```

---

## 5.3 `interaction_preferences`

```json
"interaction_preferences": {
  "positive_interaction_cues": [],
  "negative_interaction_cues": [],
  "sensitive_topics": []
}
```

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `positive_interaction_cues` | string[] | 否 | `[]` | 可能让关系更舒服的互动线索 |
| `negative_interaction_cues` | string[] | 否 | `[]` | 可能造成反感、压力或警惕的互动线索 |
| `sensitive_topics` | string[] | 否 | `[]` | 需要谨慎触碰的话题 |

示例：

```json
"interaction_preferences": {
  "positive_interaction_cues": [
    "自然、低压力的交流",
    "尊重回复节奏",
    "具体而克制的关心"
  ],
  "negative_interaction_cues": [
    "过快推进关系",
    "频繁要求回应",
    "用情绪压力要求对方表态"
  ],
  "sensitive_topics": [
    "家庭经历",
    "过去感情经历"
  ]
}
```

无法判断：

```json
"interaction_preferences": {
  "positive_interaction_cues": [],
  "negative_interaction_cues": [],
  "sensitive_topics": []
}
```

注意：

```text
没有依据时，不要硬写“家庭经历”“前任”“外貌”“收入”等敏感点。
```

---

## 5.4 `pacing_profile`

```json
"pacing_profile": {
  "pacing_tolerance": "unknown",
  "boundary_sensitivity": "unknown",
  "confession_threshold": "unknown"
}
```

---

### `pacing_tolerance`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `pacing_tolerance` | string | 否 | `"unknown"` | 见下方 |

可选值：

```text
unknown
slow
slow_to_medium
medium
medium_to_fast
fast
```

含义：

| 值 | 含义 |
|---|---|
| `unknown` | 无法判断 |
| `slow` | 明显需要慢节奏 |
| `slow_to_medium` | 偏慢，但可逐渐推进 |
| `medium` | 普通节奏 |
| `medium_to_fast` | 接受较快熟悉 |
| `fast` | 对快速亲近接受度高 |

无法判断：

```json
"pacing_tolerance": "unknown"
```

---

### `boundary_sensitivity`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `boundary_sensitivity` | string | 否 | `"unknown"` | 见下方 |

可选值：

```text
unknown
low
medium_low
medium
medium_high
high
```

无法判断：

```json
"boundary_sensitivity": "unknown"
```

---

### `confession_threshold`

| 字段 | 类型 | 可空 | 默认值 | 枚举值 |
|---|---|---:|---|---|
| `confession_threshold` | string | 否 | `"unknown"` | 见下方 |

可选值：

```text
unknown
low
medium
high
very_high
```

含义：

| 值 | 含义 |
|---|---|
| `unknown` | 无法判断 |
| `low` | 较容易接受明确表达 |
| `medium` | 需要一定互动基础 |
| `high` | 需要较强信任和舒适感 |
| `very_high` | 对明确关系确认非常谨慎 |

无法判断：

```json
"confession_threshold": "unknown"
```

---

## 5.5 `evolution_tendency`

```json
"evolution_tendency": {
  "comfort_growth_rate": "unknown",
  "trust_growth_rate": "unknown",
  "interest_volatility": "unknown",
  "alertness_trigger_level": "unknown",
  "repair_difficulty": "unknown",
  "negative_memory_weight": "unknown"
}
```

### 字段契约

| 字段 | 类型 | 可空 | 默认值 | 枚举值 | 说明 |
|---|---|---:|---|---|---|
| `comfort_growth_rate` | string | 否 | `"unknown"` | `unknown` / `slow` / `medium` / `fast` | 舒适感增长速度 |
| `trust_growth_rate` | string | 否 | `"unknown"` | `unknown` / `slow` / `medium` / `fast` | 信任增长速度 |
| `interest_volatility` | string | 否 | `"unknown"` | `unknown` / `low` / `medium` / `high` | 兴趣波动程度 |
| `alertness_trigger_level` | string | 否 | `"unknown"` | `unknown` / `low` / `medium` / `medium_high` / `high` | 警惕被触发的容易程度 |
| `repair_difficulty` | string | 否 | `"unknown"` | `unknown` / `low` / `medium` / `high` / `very_high` | 关系受损后的修复难度 |
| `negative_memory_weight` | string | 否 | `"unknown"` | `unknown` / `low` / `medium` / `high` | 负面互动在长期关系中的权重 |

无法判断时：

```json
"evolution_tendency": {
  "comfort_growth_rate": "unknown",
  "trust_growth_rate": "unknown",
  "interest_volatility": "unknown",
  "alertness_trigger_level": "unknown",
  "repair_difficulty": "unknown",
  "negative_memory_weight": "unknown"
}
```

注意：

```text
信息不足时不要默认 medium。
unknown 比假装知道更好。
```

---

## 5.6 `distinctive_hidden_notes`

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---:|---|---|
| `distinctive_hidden_notes` | string[] | 否 | `[]` | 最有特点、但不适合结构化的隐藏判断 |

示例：

```json
"distinctive_hidden_notes": [
  "她不是单纯冷淡，而是需要稳定和低压力的互动环境。",
  "她对突然的关系确认比较敏感，容易把过快推进理解成压力。",
  "相比甜言蜜语，她更容易被长期一致的表达打动。"
]
```

无法判断：

```json
"distinctive_hidden_notes": []
```

注意：

```text
这里可以放推断，但必须保守。
不要写心理诊断。
不要编造创伤经历、前任经历、家庭问题。
```

---

# 六、最终空白默认 JSON

如果输入信息极少，模型仍然必须输出这份完整结构：

```json
{
  "schema_version": "persona_extract_v0.6",
  "visible_layer": {
    "display_name": null,
    "name_user_specified": false,
    "basic_info": {
      "gender": null,
      "age_or_life_stage": null,
      "identity_role": null,
      "location_context": null,
      "relationship_status": null
    },
    "relationship_with_user": {
      "known_context": null,
      "interaction_frequency": null,
      "current_interaction_summary": null
    },
    "explicit_personality_notes": [],
    "explicit_interests": [],
    "explicit_preferences": {
      "likes": [],
      "dislikes": []
    },
    "observable_chat_style": {
      "message_length": null,
      "emoji_usage": null,
      "initiative_pattern": null,
      "expression_features": [],
      "typical_phrases": []
    },
    "visible_background": null
  },
  "hidden_layer": {
    "inferred_core_profile": {
      "summary": null,
      "profile_tags": [],
      "emotional_expression_style": "unknown",
      "social_energy_level": "unknown",
      "self_protection_level": "unknown",
      "intimacy_attitude": "unknown"
    },
    "initial_relation_state": {
      "initial_relation_tendency": null,
      "initial_impression_baseline": null,
      "initial_hidden_state": {
        "comfort": 50,
        "interest": 50,
        "trust": 50,
        "alertness": 50,
        "baseline_compatibility": 50
      }
    },
    "interaction_preferences": {
      "positive_interaction_cues": [],
      "negative_interaction_cues": [],
      "sensitive_topics": []
    },
    "pacing_profile": {
      "pacing_tolerance": "unknown",
      "boundary_sensitivity": "unknown",
      "confession_threshold": "unknown"
    },
    "evolution_tendency": {
      "comfort_growth_rate": "unknown",
      "trust_growth_rate": "unknown",
      "interest_volatility": "unknown",
      "alertness_trigger_level": "unknown",
      "repair_difficulty": "unknown",
      "negative_memory_weight": "unknown"
    },
    "distinctive_hidden_notes": []
  }
}
```

---

# 七、可以直接写进提示词的强约束

你后面写 `character_creation_extract_prompt.md` 时，可以直接放这段：

```text
你必须输出一个严格 JSON 对象，结构必须完全符合 schema_version = "persona_extract_v0.6"。

要求：
1. 只输出 JSON，不要输出解释、Markdown、代码块标记。
2. 不得省略任何字段。
3. 不得新增未定义字段。
4. visible_layer 只放用户明确提供的信息，或聊天记录中客观可见的信息。
5. hidden_layer 可以做保守推断，但只能抓最关键、最有特点、最能影响长期关系模拟的信息。
6. 不得为了填满字段而编造具体经历、家庭问题、心理创伤、恋爱史、强烈好恶。
7. 如果信息不足，按层级区分：
   - visible_layer：字符串事实与文档可为 null 的字段填 null；数组填 []；不要用 "unknown" 顶替可见层不确定内容。
   - hidden_layer：文档规定默认 "unknown" 的必填枚举字符串填 "unknown"（见第五章）；initial_hidden_state 五键数值填 50。
8. 不要使用心理诊断式标签。
9. 不要把用户对目标对象的喜欢，推断成目标对象也喜欢用户。
10. 不要把轻微信号写成明确好感。
```

## 字段中文名称

| 字段路径 | 前端中文名称 |
|---|---|
| `visible_layer.display_name` | 角色名称 |
| `visible_layer.basic_info` | 基础信息 |
| `visible_layer.basic_info.gender` | 性别 |
| `visible_layer.basic_info.age_or_life_stage` | 年龄 / 阶段 |
| `visible_layer.basic_info.identity_role` | 身份 |
| `visible_layer.basic_info.location_context` | 所在环境 |
| `visible_layer.basic_info.relationship_status` | 感情状态 |
| `visible_layer.relationship_with_user` | 与你的关系 |
| `visible_layer.relationship_with_user.known_context` | 认识关系 |
| `visible_layer.relationship_with_user.interaction_frequency` | 互动频率 |
| `visible_layer.relationship_with_user.current_interaction_summary` | 当前互动概况 |
| `visible_layer.explicit_personality_notes` | 明确性格描述 |
| `visible_layer.explicit_interests` | 兴趣爱好 |
| `visible_layer.explicit_preferences` | 明确偏好 |
| `visible_layer.explicit_preferences.likes` | 喜欢 |
| `visible_layer.explicit_preferences.dislikes` | 不喜欢 |
| `visible_layer.observable_chat_style` | 聊天表现 |
| `visible_layer.observable_chat_style.message_length` | 回复长度 |
| `visible_layer.observable_chat_style.emoji_usage` | 表情使用 |
| `visible_layer.observable_chat_style.initiative_pattern` | 主动程度 |
| `visible_layer.observable_chat_style.expression_features` | 表达特征 |
| `visible_layer.observable_chat_style.typical_phrases` | 常用表达 |
| `visible_layer.visible_background` | 背景信息 |

可见层目前涉及枚举的字段只有 3 个：

1. `visible_layer.observable_chat_style.message_length`
2. `visible_layer.observable_chat_style.emoji_usage`
3. `visible_layer.observable_chat_style.initiative_pattern`


## 1. `message_length` 回复长度

| 枚举值 | 中文展示名 | 说明 |
|---|---|---|
| `very_short` | 非常简短 | 经常只回一两个字或极短句 |
| `short` | 偏短 | 多数回复较短 |
| `short_to_medium` | 短句为主，偶尔展开 | 大部分是短句，但有时会多说几句 |
| `medium` | 中等长度 | 回复长度较稳定，不算很短也不算很长 |
| `long` | 经常长段表达 | 经常会发较长内容 |
| `mixed` | 长短不固定 | 回复长度变化明显，没有稳定模式 |

---

## 2. `emoji_usage` 表情使用

| 枚举值 | 中文展示名 | 说明 |
|---|---|---|
| `none` | 基本不用 | 几乎不使用表情、emoji、颜文字 |
| `low` | 较少使用 | 偶尔使用，但整体不多 |
| `medium` | 偶尔使用 | 有一定使用频率，但不密集 |
| `high` | 经常使用 | 经常使用表情或 emoji |
| `mixed` | 使用不固定 | 有时很多，有时不用，风格不稳定 |

---

## 3. `initiative_pattern` 主动程度

| 枚举值 | 中文展示名 | 说明 |
|---|---|---|
| `mostly_replying` | 回应为主 | 多数时候是回应用户，很少主动开启话题 |
| `balanced` | 双方接近 | 双方主动程度比较接近 |
| `sometimes_initiates` | 偶尔主动 | 偶尔会主动开启话题或主动联系 |
| `often_initiates` | 经常主动 | 经常主动找用户或主动延续话题 |
| `unclear` | 暂不明确 | 有材料，但无法判断主动模式 |