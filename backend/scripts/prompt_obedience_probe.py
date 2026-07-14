#!/usr/bin/env python3
"""提示词服从度探针（4 组 × 流式/非流式）—— 开发调试用，不参与游戏运行。

用来判断「角色不听指令」到底是 prompt 的问题还是模型能力的问题：给一条极简的硬性
指令，看模型照不照做。换模型后如果角色表现变差，可以先跑它定位。

与生产链路一致：走 create_sync_client() / get_chat_model() / get_base_url()，
temperature=0。需要先配好大模型（网页向导或环境变量均可）。

用法（在 backend 目录）：
  python scripts/prompt_obedience_probe.py
  python scripts/prompt_obedience_probe.py --runs 10

勿将本脚本加入默认 CI；勿在日志中打印 API Key。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 保证可导入 app.*
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import app.dotenv_load  # noqa: F401 — 与 uvicorn 一致，读取 backend/.env

from app.engine.llm_client import create_sync_client, get_base_url, get_chat_model
from app.engine.no_reply import normalize_character_reply

CONSTRAINT = (
    "硬性规则：你的本次回复正文必须以「111」三个字符开头，不得省略、不得放在引号或其它符号后，其它内容跟在 111 后面即可。"
)
USER_TASK = "请回复：你好"
NEUTRAL_SYSTEM = "你是对话助手，按用户要求回复。"  # 组 2 若纯 user 被拒时的兜底


def _messages_summary(msgs: list[dict[str, Any]], max_each: int = 120) -> list[dict[str, Any]]:
    """缩略 content 便于打印，保留 role 与条数。"""
    out: list[dict[str, Any]] = []
    for m in msgs:
        c = str(m.get("content", ""))
        if len(c) > max_each:
            c = c[:max_each] + f"…(len={len(str(m.get('content','')))})"
        out.append({"role": m.get("role"), "content": c})
    return out


def build_message_sets() -> dict[str, list[dict[str, str]]]:
    return {
        "1_system_only": [
            {"role": "system", "content": CONSTRAINT},
            {"role": "user", "content": USER_TASK},
        ],
        "2_user_only": [
            {"role": "user", "content": CONSTRAINT + "\n\n" + USER_TASK},
        ],
        "2b_user_only_neutral_system": [
            {"role": "system", "content": NEUTRAL_SYSTEM},
            {"role": "user", "content": CONSTRAINT + "\n\n" + USER_TASK},
        ],
        "3_system_and_user": [
            {"role": "system", "content": CONSTRAINT},
            {"role": "user", "content": CONSTRAINT + "\n\n" + USER_TASK},
        ],
        "4_multi_system": [
            {"role": "system", "content": CONSTRAINT},
            {"role": "system", "content": "【人设占位】昵称：探针；性格：中性；聊天风格：短句。"},
            {
                "role": "system",
                "content": "当前关系状态："
                + json.dumps(
                    {
                        "comfort": 50.0,
                        "interest": 50.0,
                        "trust": 50.0,
                        "alertness": 50.0,
                        "baseline_compatibility": 50.0,
                    },
                    ensure_ascii=False,
                ),
            },
            {"role": "system", "content": "长期记忆：（空）"},
            {"role": "user", "content": USER_TASK},
        ],
    }


def _invoke_non_stream_raw(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        stream=False,
    )
    choice0 = completion.choices[0]
    content = choice0.message.content
    return content if content is not None else ""


def _invoke_stream_raw(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        stream=True,
    )
    parts: list[str] = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            parts.append(delta.content)
    return "".join(parts)


def obey_111(text: str) -> bool:
    return text.strip().startswith("111")


@dataclass
class TrialResult:
    sdk_raw: str = ""
    after_strip: str = ""
    character_reply: str = ""
    character_no_reply: bool = False
    obey_strip: bool = False
    obey_normalized: bool = False


@dataclass
class GroupStreamStats:
    trials: list[TrialResult] = field(default_factory=list)
    obey_strip_rate: float = 0.0
    obey_norm_rate: float = 0.0


def run_group_stream(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    *,
    stream: bool,
    runs: int,
) -> GroupStreamStats:
    stats = GroupStreamStats()
    for _ in range(runs):
        if stream:
            raw = _invoke_stream_raw(client, model, messages)
        else:
            raw = _invoke_non_stream_raw(client, model, messages)
        stripped = (raw or "").strip()
        char_r, char_nr = normalize_character_reply(stripped)
        tr = TrialResult(
            sdk_raw=raw,
            after_strip=stripped,
            character_reply=char_r,
            character_no_reply=char_nr,
            obey_strip=obey_111(stripped),
            obey_normalized=obey_111(char_r),
        )
        stats.trials.append(tr)
    n = len(stats.trials)
    if n:
        stats.obey_strip_rate = sum(1 for t in stats.trials if t.obey_strip) / n
        stats.obey_norm_rate = sum(1 for t in stats.trials if t.obey_normalized) / n
    return stats


def print_trial_detail(label: str, messages: list[dict[str, str]], tr: TrialResult) -> None:
    print(f"\n--- {label} ---")
    print("messages_sample:", json.dumps(_messages_summary(list(messages)), ensure_ascii=False))
    raw_preview = tr.sdk_raw[:800] + ("…" if len(tr.sdk_raw) > 800 else "")
    print("sdk_raw_repr:", repr(raw_preview))
    print("after_call_llm_strip:", repr(tr.after_strip))
    print("normalize_character_reply ->", repr(tr.character_reply), "no_reply=", tr.character_no_reply)
    print("obey_111(stripped):", tr.obey_strip, "| obey_111(normalized):", tr.obey_normalized)


def print_markdown_table(rows: list[tuple[str, str, float, float]]) -> None:
    print("\n## 结果汇总（obey 率 = 回复 strip 后以 111 开头）\n")
    print("| 组别 | 模式 | obey(strip) | obey(normalized) |")
    print("|------|------|-------------|------------------|")
    for group_label, mode, sr, nr in rows:
        print(f"| {group_label} | {mode} | {sr:.0%} | {nr:.0%} |")


def print_final_judgment(
    g1: float,
    g2: float,
    g3: float,
    g4: float,
    *,
    stream: bool,
    group2_note: str,
) -> None:
    mode = "stream" if stream else "non-stream"
    print(f"\n## 判断草案（{mode}，以 obey_strip 为主）\n")
    parts: list[str] = []
    if group2_note:
        parts.append(f"- **组2 说明**：{group2_note}")

    if g2 > g1 + 0.15:
        parts.append("- **user 权重更高**：组2 服从率明显高于组1（约束仅在 system）。")
    elif g1 > g2 + 0.15:
        parts.append("- **system 路径相对更有效**：组1 高于 组2。")
    else:
        parts.append("- **组1 vs 组2 接近**：难以单独归因 system/user，或模型对两者均不稳定。")

    if g4 + 0.15 < g1:
        parts.append("- **多 system 稀释**：组4 明显低于组1，首条规则易被后续 system 冲淡。")
    elif abs(g4 - g1) <= 0.15:
        parts.append("- **多 system 未显著稀释**：组4 与 组1 接近。")

    if g3 >= max(g1, g2, g4) - 0.05 and g3 >= 0.8:
        parts.append("- **双保险有效**：组3 服从率最高或并列最高。")

    parts.append(
        "- **接口形态**：本探针仅覆盖 Chat Completions；**未**验证 Responses API / `instructions`；若需对比须另做实验。"
    )
    print("\n".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(description="提示词 111 前缀服从度探针")
    parser.add_argument("--runs", type=int, default=5, help="每组每模式重复次数（默认 5）")
    parser.add_argument("--verbose", action="store_true", help="打印每次 trial 详情（输出很长）")
    args = parser.parse_args()
    runs = max(1, args.runs)

    client = create_sync_client()
    model = get_chat_model()
    base = get_base_url()

    print("## 环境（与 llm_client 生产一致）")
    print(f"- base_url: {base}")
    print(f"- model: {model}")
    print(f"- temperature: 0")
    print(f"- runs per cell: {runs}")
    print(f"- USER_TASK: {USER_TASK!r}")

    sets = build_message_sets()
    group_ids = ["1", "2", "3", "4"]
    id_to_key = {
        "1": "1_system_only",
        "2": "2_user_only",
        "3": "3_system_and_user",
        "4": "4_multi_system",
    }
    # (group_id, stream) -> stats; msgs_used[group_id] = 实际 messages
    results: dict[tuple[str, bool], GroupStreamStats] = {}
    msgs_used: dict[str, list[dict[str, str]]] = {}
    group2_note = ""

    for gid in group_ids:
        key = id_to_key[gid]
        msgs = [dict(m) for m in sets[key]]
        if gid == "2":
            try:
                _invoke_non_stream_raw(client, model, msgs)
            except Exception as e:
                print(f"\n[WARN] 组2 纯 user 请求失败，改用 neutral system 兜底: {e}")
                msgs = [dict(m) for m in sets["2b_user_only_neutral_system"]]
                group2_note = "纯 user 单条消息被 API 拒绝，已改为 system=中性 + user（含约束与任务）。"
        msgs_used[gid] = msgs

    for gid in group_ids:
        msgs = msgs_used[gid]
        for stream in (False, True):
            label = f"组{gid}/{'stream' if stream else 'non_stream'}"
            stats = run_group_stream(client, model, msgs, stream=stream, runs=runs)
            results[(gid, stream)] = stats
            print(
                f"\n### {label} obey_strip={stats.obey_strip_rate:.0%} "
                f"obey_norm={stats.obey_norm_rate:.0%}"
            )
            if args.verbose:
                for i, tr in enumerate(stats.trials):
                    print_trial_detail(f"{label} run#{i+1}", msgs, tr)

    id_label = {
        "1": "1_system_only",
        "2": "2_user_only",
        "3": "3_system_and_user",
        "4": "4_multi_system",
    }
    table_rows: list[tuple[str, str, float, float]] = []
    for stream in (False, True):
        mode = "stream" if stream else "non-stream"
        for gid in group_ids:
            st = results[(gid, stream)]
            table_rows.append((id_label[gid], mode, st.obey_strip_rate, st.obey_norm_rate))
            if not args.verbose:
                print_trial_detail(
                    f"组{gid} {mode}（末次 run 样例）",
                    msgs_used[gid],
                    st.trials[-1],
                )

    print_markdown_table(table_rows)

    for stream in (False, True):
        g1 = results[("1", stream)].obey_strip_rate
        g2 = results[("2", stream)].obey_strip_rate
        g3 = results[("3", stream)].obey_strip_rate
        g4 = results[("4", stream)].obey_strip_rate
        print_final_judgment(g1, g2, g3, g4, stream=stream, group2_note=group2_note)

    print("\n完成。若需完整逐条输出请加 --verbose。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
