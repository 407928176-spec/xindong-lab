from __future__ import annotations

from app.engine.no_reply import (
    NO_REPLY_TOKEN,
    NoReplyStreamSplitter,
    is_exact_no_reply,
    normalize_character_reply,
)


def test_is_exact_no_reply() -> None:
    assert is_exact_no_reply(f"  {NO_REPLY_TOKEN}  ")
    assert not is_exact_no_reply(f"{NO_REPLY_TOKEN}。")
    assert not is_exact_no_reply(f"你好 {NO_REPLY_TOKEN}")
    assert not is_exact_no_reply("")
    assert not is_exact_no_reply("   ")


def test_normalize_character_reply() -> None:
    assert normalize_character_reply(f"  {NO_REPLY_TOKEN}  ") == ("", True)
    assert normalize_character_reply("  hi  ") == ("hi", False)
    assert normalize_character_reply("") == ("", False)


def test_stream_exact_no_reply_no_public() -> None:
    sp = NoReplyStreamSplitter()
    out: list[str] = []
    for part in ["  ", NO_REPLY_TOKEN, "  "]:
        out.extend(sp.feed(part))
    out.extend(sp.finish())
    assert out == []
    assert sp.public_acc == ""
    assert sp.normalized_reply() == ("", True)


def test_stream_plain_text_passthrough() -> None:
    sp = NoReplyStreamSplitter()
    out: list[str] = []
    for ch in "你好":
        out.extend(sp.feed(ch))
    out.extend(sp.finish())
    assert "".join(out) == "你好"
    assert sp.raw_acc == "你好"
    assert sp.normalized_reply() == ("你好", False)


def test_stream_no_reply_with_trailing_ws_chunks() -> None:
    sp = NoReplyStreamSplitter()
    out: list[str] = []
    out.extend(sp.feed("  "))
    out.extend(sp.feed(NO_REPLY_TOKEN))
    out.extend(sp.feed("  "))
    out.extend(sp.finish())
    assert out == []
    assert sp.normalized_reply() == ("", True)


def test_stream_not_exact_flushes_prefix() -> None:
    sp = NoReplyStreamSplitter()
    out: list[str] = []
    out.extend(sp.feed(NO_REPLY_TOKEN))
    out.extend(sp.feed("。"))
    out.extend(sp.finish())
    assert "".join(out) == f"{NO_REPLY_TOKEN}。"
    assert sp.normalized_reply() == (f"{NO_REPLY_TOKEN}。", False)


def test_stream_chunked_token_then_extra() -> None:
    sp = NoReplyStreamSplitter()
    out: list[str] = []
    for part in ["<", "NO_REPLY", ">x"]:
        out.extend(sp.feed(part))
    out.extend(sp.finish())
    assert "".join(out) == "<NO_REPLY>x"
    assert sp.normalized_reply() == ("<NO_REPLY>x", False)
