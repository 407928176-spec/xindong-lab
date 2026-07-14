"""步骤 5.7：/chat 真实 LangGraph + save_and_respond，仅 patch LLM 读 prompt。"""

from __future__ import annotations

import concurrent.futures
import json
import threading
from unittest.mock import patch

import app.db.session as db_session_module
from app.engine.llm_client import WebSearchLLMResult
from app.engine.no_reply import NO_REPLY_DISPLAY_TEXT, NO_REPLY_TOKEN
from app.engine.web_context import WebContextBuildResult, WebContextDecision
from app.models.character import Character
from app.models.ending import Ending
from app.models.enums import CharacterStatus
from app.schemas.character import CharacterChatRequest
from app.services.character_service import CharacterChatBusyError, chat_with_character


def test_post_chat_real_graph_persists_and_matches_db(character_chat_api_client) -> None:
    client, cid = character_chat_api_client

    with patch("app.engine.nodes.generate_reply.read_prompt", return_value="系统层"):
        with patch("app.engine.nodes.evaluate_state.read_prompt", return_value=""):
            with patch("app.engine.nodes.generate_reply.decide_web_context", return_value=WebContextDecision(False, "", "无需联网")):
                with patch("app.engine.nodes.generate_reply.build_web_context", return_value=WebContextBuildResult("")):
                    with patch("app.engine.nodes.generate_reply.call_llm", return_value="  合成回复  "):
                        res = client.post(f"/api/characters/{cid}/chat", json={"content": "hello"})

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["assistant_message"] == "合成回复"
    assert data["user_message"]["role"] == "user"
    assert data["user_message"]["content"] == "hello"
    assert data["assistant_message_item"]["role"] == "character"
    assert data["assistant_message_item"]["content"] == "合成回复"
    assert data.get("assistant_no_reply") is False
    assert data.get("assistant_display_text") == "合成回复"
    assert data.get("assistant_message_type") == "normal"
    assert data["assistant_message_item"].get("is_no_reply") is False
    assert data["assistant_message_item"].get("display_text") == "合成回复"
    assert data["round"] == 1
    assert data["user_message"]["round_number"] == 1
    assert data["assistant_message_item"]["round_number"] == 1
    assert isinstance(data["heartbeat_score"], int)
    assert data["ending"] is None

    detail = client.get(f"/api/characters/{cid}").json()
    msgs = detail["messages"]
    assert len(msgs) == 2
    by_id = {m["id"]: m for m in msgs}
    assert by_id[data["user_message"]["id"]]["content"] == "hello"
    listed = client.get("/api/characters").json()
    row = next(x for x in listed if x["id"] == cid)
    assert row["last_message_preview"] == data["assistant_message_item"]["display_text"]
    assert by_id[data["assistant_message_item"]["id"]]["content"] == "合成回复"


def test_post_chat_exact_no_reply_persists_and_api_fields(character_chat_api_client) -> None:
    client, cid = character_chat_api_client

    with patch("app.engine.nodes.generate_reply.read_prompt", return_value="系统层"):
        with patch("app.engine.nodes.evaluate_state.read_prompt", return_value=""):
            with patch("app.engine.nodes.generate_reply.decide_web_context", return_value=WebContextDecision(False, "", "无需联网")):
                with patch("app.engine.nodes.generate_reply.build_web_context", return_value=WebContextBuildResult("")):
                    with patch("app.engine.nodes.generate_reply.call_llm", return_value=NO_REPLY_TOKEN):
                        res = client.post(f"/api/characters/{cid}/chat", json={"content": "越界纠缠"})

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["assistant_message"] == ""
    assert data["assistant_no_reply"] is True
    assert data["assistant_display_text"] == NO_REPLY_DISPLAY_TEXT
    assert data["assistant_message_type"] == "no_reply"
    assert data["assistant_message_item"]["content"] == ""
    assert data["assistant_message_item"]["is_no_reply"] is True
    assert data["assistant_message_item"]["message_type"] == "no_reply"
    assert data["assistant_message_item"]["display_text"] == NO_REPLY_DISPLAY_TEXT

    detail = client.get(f"/api/characters/{cid}").json()
    asst = next(m for m in detail["messages"] if m["role"] == "character")
    assert asst["content"] == ""
    assert asst["is_no_reply"] is True
    assert asst["display_text"] == NO_REPLY_DISPLAY_TEXT


def test_post_chat_stream_no_reply_no_token_in_sse(character_chat_api_client) -> None:
    client, cid = character_chat_api_client

    def _mock_llm(messages, *, temperature=0.8, stream=False, model=None, **kwargs):
        if stream:
            return iter([NO_REPLY_TOKEN])
        return "unused"

    with patch("app.engine.nodes.generate_reply.read_prompt", return_value="系统层"):
        with patch("app.engine.nodes.evaluate_state.read_prompt", return_value=""):
            with patch("app.engine.nodes.generate_reply.decide_web_context", return_value=WebContextDecision(False, "", "无需联网")):
                with patch("app.engine.nodes.generate_reply.build_web_context", return_value=WebContextBuildResult("")):
                    with patch("app.engine.nodes.generate_reply.call_llm", side_effect=_mock_llm):
                        res = client.post(f"/api/characters/{cid}/chat/stream", json={"content": "hi"})

    assert res.status_code == 200, res.text
    assert NO_REPLY_TOKEN not in res.text
    done = None
    for line in res.text.splitlines():
        if line.startswith("data: "):
            obj = json.loads(line.removeprefix("data: "))
            if obj.get("type") == "done":
                done = obj
    assert done is not None
    assert done["assistant_no_reply"] is True
    assert done["assistant_display_text"] == NO_REPLY_DISPLAY_TEXT
    assert done["assistant_message_type"] == "no_reply"


def test_post_chat_feeds_web_context_into_reply_prompt(character_chat_api_client) -> None:
    """联网查到的资料必须真的进到角色回复的 prompt 里，否则联网等于白做。"""
    client, cid = character_chat_api_client
    captured: dict = {}

    def _capture(messages, **kwargs):
        captured["messages"] = messages
        return "我刚看到一个挺新的消息"

    with patch("app.engine.nodes.generate_reply.read_prompt", return_value="系统层"):
        with patch("app.engine.nodes.evaluate_state.read_prompt", return_value=""):
            with patch(
                "app.engine.nodes.generate_reply.decide_web_context",
                return_value=WebContextDecision(True, "今天 娱乐新闻", "用户询问实时新闻"),
            ):
                with patch(
                    "app.engine.web_context.web_search_available",
                    return_value=True,
                ):
                    with patch(
                        "app.engine.web_context.call_llm_with_web_search_result",
                        return_value=WebSearchLLMResult(
                            text="新闻资料包",
                            sources=[{"title": "来源标题", "site": "toutiao"}],
                            used_web_search=True,
                        ),
                    ):
                        with patch("app.engine.nodes.generate_reply.call_llm", side_effect=_capture):
                            res = client.post(
                                f"/api/characters/{cid}/chat",
                                json={"content": "今天有什么娱乐新闻？"},
                            )

    assert res.status_code == 200, res.text
    blob = str(captured.get("messages"))
    assert "新闻资料包" in blob


def test_post_chat_skips_web_context_when_unsupported(character_chat_api_client) -> None:
    """非方舟供应商不支持联网：不得发起联网调用，且聊天必须照常完成。"""
    client, cid = character_chat_api_client

    with patch("app.engine.nodes.generate_reply.read_prompt", return_value="系统层"):
        with patch("app.engine.nodes.evaluate_state.read_prompt", return_value=""):
            with patch("app.engine.web_context.web_search_available", return_value=False):
                with patch("app.engine.web_context.call_llm_with_web_search_result") as web_call:
                    with patch("app.engine.nodes.generate_reply.call_llm", return_value="今天过得还行"):
                        res = client.post(
                            f"/api/characters/{cid}/chat",
                            json={"content": "今天有什么娱乐新闻？"},
                        )

    assert res.status_code == 200, res.text
    web_call.assert_not_called()


def test_post_chat_when_character_ended_returns_409(character_chat_api_client) -> None:
    client, cid = character_chat_api_client
    db = db_session_module.SessionLocal()
    try:
        ch = db.get(Character, cid)
        assert ch is not None
        ch.is_ended = True
        db.commit()
    finally:
        db.close()

    res = client.post(f"/api/characters/{cid}/chat", json={"content": "再来一句"})
    assert res.status_code == 409
    assert "结束" in res.json().get("detail", "")


def test_post_chat_ne_ending_stays_on_home_until_acknowledged(character_chat_api_client) -> None:
    client, cid = character_chat_api_client

    eval_payload = {
        "intent": "表白",
        "state_changes": {
            "comfort_delta": 0,
            "interest_delta": 0,
            "trust_delta": 0,
            "alertness_delta": 0,
            "reason": "",
        },
    }
    with patch("app.engine.nodes.generate_reply.read_prompt", return_value="系统层"):
        with patch("app.engine.nodes.evaluate_state.read_prompt", return_value="x"):
            with patch("app.engine.nodes.ending_judge.read_prompt", return_value=""):
                with patch("app.engine.nodes.generate_reply.decide_web_context", return_value=WebContextDecision(False, "", "无需联网")):
                    with patch("app.engine.nodes.generate_reply.build_web_context", return_value=WebContextBuildResult("")):
                        with patch("app.engine.nodes.generate_reply.call_llm", return_value="我有点喜欢你，但我们慢一点"):
                            with patch(
                                "app.engine.nodes.evaluate_state.call_llm",
                                return_value=json.dumps(eval_payload, ensure_ascii=False),
                            ):
                                res = client.post(f"/api/characters/{cid}/chat", json={"content": "我喜欢你，做我女朋友吧"})

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["ending"] == {"result": "NE", "evaluation": "（评价暂缺）", "user_review": None}

    blocked = client.post(f"/api/characters/{cid}/chat", json={"content": "那我们继续聊"})
    assert blocked.status_code == 409

    detail = client.get(f"/api/characters/{cid}")
    assert detail.status_code == 200
    assert detail.json()["status"] == CharacterStatus.ENDING_UNREAD.value

    active_res = client.get("/api/characters")
    assert active_res.status_code == 200
    active_row = next(item for item in active_res.json() if item["id"] == cid)
    assert active_row["status"] == CharacterStatus.ENDING_UNREAD.value
    assert active_row["ending"] == {"result": "NE", "evaluation": "（评价暂缺）", "user_review": None}

    ended_res = client.get("/api/characters/ended")
    assert ended_res.status_code == 200
    ended_ids = [item["id"] for item in ended_res.json()]
    assert cid not in ended_ids

    ack = client.post(f"/api/characters/{cid}/acknowledge-ending")
    assert ack.status_code == 204

    active_res2 = client.get("/api/characters")
    assert active_res2.status_code == 200
    active_ids2 = [item["id"] for item in active_res2.json()]
    assert cid not in active_ids2

    ended_res2 = client.get("/api/characters/ended")
    assert ended_res2.status_code == 200
    ended_row = next(item for item in ended_res2.json() if item["id"] == cid)
    assert ended_row["status"] == CharacterStatus.ENDED.value
    assert ended_row["ending"] == {"result": "NE", "evaluation": "（评价暂缺）", "user_review": None}


def test_post_chat_character_confession_ends_as_he(character_chat_api_client) -> None:
    client, cid = character_chat_api_client

    eval_payload = {
        "intent": "角色表白",
        "confession_response": "accept",
        "state_changes": {
            "comfort_delta": 0,
            "interest_delta": 0,
            "trust_delta": 0,
            "alertness_delta": 0,
            "reason": "",
        },
    }
    with patch("app.engine.nodes.generate_reply.read_prompt", return_value="系统层"):
        with patch("app.engine.nodes.evaluate_state.read_prompt", return_value="x"):
            with patch("app.engine.nodes.ending_judge.read_prompt", return_value=""):
                with patch("app.engine.nodes.generate_reply.decide_web_context", return_value=WebContextDecision(False, "", "无需联网")):
                    with patch("app.engine.nodes.generate_reply.build_web_context", return_value=WebContextBuildResult("")):
                        with patch("app.engine.nodes.generate_reply.call_llm", return_value="我也喜欢你，我们在一起吧"):
                            with patch(
                                "app.engine.nodes.evaluate_state.call_llm",
                                return_value=json.dumps(eval_payload, ensure_ascii=False),
                            ):
                                res = client.post(f"/api/characters/{cid}/chat", json={"content": "今天好开心"})

    assert res.status_code == 200, res.text
    assert res.json()["ending"] == {"result": "HE", "evaluation": "（评价暂缺）", "user_review": None}
    blocked = client.post(f"/api/characters/{cid}/chat", json={"content": "再聊一句"})
    assert blocked.status_code == 409


def test_character_detail_returns_persisted_ending(character_chat_api_client) -> None:
    client, cid = character_chat_api_client
    db = db_session_module.SessionLocal()
    try:
        ch = db.get(Character, cid)
        assert ch is not None
        ch.is_ended = True
        ch.status = CharacterStatus.ENDED.value
        db.add(Ending(character_id=cid, ending_kind="NE", content="detail ending text"))
        db.commit()
    finally:
        db.close()

    res = client.get(f"/api/characters/{cid}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == CharacterStatus.ENDED.value
    assert data["ending"] == {"result": "NE", "evaluation": "detail ending text", "user_review": None}


def test_character_list_excludes_ended_and_ended_endpoint_returns_it(character_chat_api_client) -> None:
    client, cid = character_chat_api_client
    db = db_session_module.SessionLocal()
    try:
        ch = db.get(Character, cid)
        assert ch is not None
        ch.is_ended = True
        ch.status = CharacterStatus.ENDED.value
        ch.is_pinned = True
        db.add(Ending(character_id=cid, ending_kind="HE", content="archive ending text"))
        db.commit()
    finally:
        db.close()

    active_res = client.get("/api/characters")
    assert active_res.status_code == 200
    active_ids = [item["id"] for item in active_res.json()]
    assert cid not in active_ids

    ended_res = client.get("/api/characters/ended")
    assert ended_res.status_code == 200
    ended_items = ended_res.json()
    ended_row = next(item for item in ended_items if item["id"] == cid)
    assert ended_row["status"] == CharacterStatus.ENDED.value
    assert ended_row["is_pinned"] is True
    assert ended_row["ending"] == {"result": "HE", "evaluation": "archive ending text", "user_review": None}


def test_character_with_ending_row_but_old_in_progress_status_still_moves_to_archive(character_chat_api_client) -> None:
    client, cid = character_chat_api_client
    db = db_session_module.SessionLocal()
    try:
        ch = db.get(Character, cid)
        assert ch is not None
        ch.is_ended = False
        ch.status = CharacterStatus.IN_PROGRESS.value
        db.add(Ending(character_id=cid, ending_kind="NE", content="old data ending text"))
        db.commit()
    finally:
        db.close()

    active_res = client.get("/api/characters")
    assert active_res.status_code == 200
    active_ids = [item["id"] for item in active_res.json()]
    assert cid not in active_ids

    ended_res = client.get("/api/characters/ended")
    assert ended_res.status_code == 200
    ended_items = ended_res.json()
    ended_row = next(item for item in ended_items if item["id"] == cid)
    assert ended_row["status"] == CharacterStatus.IN_PROGRESS.value
    assert ended_row["ending"] == {"result": "NE", "evaluation": "old data ending text", "user_review": None}


def test_concurrent_chat_second_request_gets_busy_error(character_chat_api_client) -> None:
    """同一角色两个并发请求：第一个持有锁期间，第二个应立即收到 CharacterChatBusyError。"""
    _, cid = character_chat_api_client

    first_locked = threading.Event()
    first_can_continue = threading.Event()

    def slow_llm(messages, *, temperature=0.8, stream=False, model=None, **kwargs):
        # 告知主线程锁已被持有，然后等待第二个请求完成后再继续。
        first_locked.set()
        first_can_continue.wait(timeout=5)
        return "慢回复"

    results: dict[str, object] = {}

    # 从 DB 读取该角色的 user_id，用于绕过所有权校验
    _tmp_db = db_session_module.SessionLocal()
    _char_user_id = (_tmp_db.get(Character, cid) or Character()).user_id or ""
    _tmp_db.close()

    def send_first() -> None:
        # 必须通过模块属性访问，才能拿到 monkeypatch 替换后的 test_local。
        db = db_session_module.SessionLocal()
        try:
            with patch("app.engine.nodes.generate_reply.read_prompt", return_value="系统层"):
                with patch("app.engine.nodes.evaluate_state.read_prompt", return_value=""):
                    with patch("app.engine.nodes.generate_reply.decide_web_context", return_value=WebContextDecision(False, "", "无需联网")):
                        with patch("app.engine.nodes.generate_reply.build_web_context", return_value=WebContextBuildResult("")):
                            with patch("app.engine.nodes.generate_reply.call_llm", side_effect=slow_llm):
                                req = CharacterChatRequest(content="先来一句")
                                try:
                                    resp = chat_with_character(db, cid, req, user_id=_char_user_id)
                                    results["first"] = 200 if resp is not None else "returned None"
                                except Exception as exc:
                                    results["first"] = str(exc)
        finally:
            db.close()

    def send_second() -> None:
        first_locked.wait(timeout=5)  # 等第一个请求持有锁后再发
        db = db_session_module.SessionLocal()
        try:
            req = CharacterChatRequest(content="抢着发")
            try:
                chat_with_character(db, cid, req, user_id=_char_user_id)
                results["second"] = 200
            except CharacterChatBusyError:
                results["second"] = 409
            except Exception as exc:
                results["second"] = str(exc)
        finally:
            db.close()
            first_can_continue.set()  # 释放第一个请求

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f2 = executor.submit(send_second)
        f1 = executor.submit(send_first)
        concurrent.futures.wait([f1, f2], timeout=30)

    assert results.get("first") == 200, f"第一个请求应成功，实际: {results}"
    assert results.get("second") == 409, f"第二个请求应返回 409，实际: {results}"
