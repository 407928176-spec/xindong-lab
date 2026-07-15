"""大模型配置接口：支撑前端的首次启动向导与设置页。

三个端点：查当前状态、只测不存、测通后保存。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import llm_config
from app.engine import llm_client
from app.schemas.config import LlmConfigInput, LlmConfigStatus, LlmProbeResponse
from app.services.llm_probe_service import probe

router = APIRouter(prefix="/config", tags=["config"])


def _to_status(cfg: llm_config.LlmConfig) -> LlmConfigStatus:
    return LlmConfigStatus(
        configured=cfg.is_complete,
        base_url=cfg.base_url,
        model=cfg.model,
        aux_model=cfg.aux_model,
        api_key_masked=llm_config.masked_api_key(cfg.api_key),
        web_search_supported=cfg.web_search_supported,
    )


def _to_config(payload: LlmConfigInput) -> llm_config.LlmConfig:
    return llm_config.LlmConfig(
        base_url=payload.base_url.strip(),
        api_key=payload.api_key.strip(),
        model=payload.model.strip(),
        aux_model=payload.aux_model.strip(),
    )


@router.get("/llm", response_model=LlmConfigStatus)
def get_llm_config() -> LlmConfigStatus:
    """当前大模型配置状态。前端用它决定是否跳转向导、以及聊天页的联网标识。"""
    return _to_status(llm_config.load())


@router.post("/llm/test", response_model=LlmProbeResponse)
def test_llm_config(payload: LlmConfigInput) -> LlmProbeResponse:
    """实测一份配置但不保存，供向导的「测试连接」按钮使用。"""
    result = probe(_to_config(payload))
    return LlmProbeResponse(
        ok=result.ok,
        message=result.message,
        web_search_supported=result.web_search_supported,
        web_search_message=result.web_search_message,
        base_url=result.base_url,
    )


@router.put("/llm", response_model=LlmConfigStatus)
def save_llm_config(payload: LlmConfigInput) -> LlmConfigStatus:
    """保存配置。先实测再落盘——不让用户存下一份根本用不了的配置。

    顺带把探测出的联网搜索能力一起存下来，避免每次聊天都去试探一次。
    """
    cfg = _to_config(payload)
    result = probe(cfg)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.message)

    saved = llm_config.save(
        llm_config.LlmConfig(
            # 存实测通过的那个地址：probe 可能给缺 /v1 的地址补全过，
            # 存用户原样填的会把刚验证好的配置又变回不可用的。
            base_url=result.base_url or cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
            aux_model=cfg.aux_model,
            web_search_supported=result.web_search_supported,
        )
    )
    # 换了 Key/Base URL 后，之前缓存的客户端指向旧配置，必须丢弃。
    llm_client.reset_clients()
    return _to_status(saved)
