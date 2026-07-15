"""大模型配置接口的请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LlmConfigInput(BaseModel):
    """向导提交的配置。"""

    base_url: str = Field(..., description="OpenAI 兼容接口地址，多数供应商需要以 /v1 结尾")
    api_key: str = Field(..., description="供应商 API Key")
    model: str = Field(..., description="角色回复使用的模型名")
    aux_model: str = Field("", description="辅助模型（状态评估/终局/摘要），留空则与主模型相同")


class LlmConfigStatus(BaseModel):
    """回显给前端的配置状态。**永远不含明文 API Key。**"""

    configured: bool
    base_url: str = ""
    model: str = ""
    aux_model: str = ""
    api_key_masked: str = ""
    web_search_supported: bool = False


class LlmProbeResponse(BaseModel):
    """测试连接的结果。"""

    ok: bool
    message: str
    web_search_supported: bool = False
    web_search_message: str = ""
    base_url: str = Field(
        "", description="实测可用的 Base URL，可能是自动补全 /v1 后的结果，前端应据此回填输入框"
    )
