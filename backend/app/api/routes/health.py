"""健康检查路由：阶段 1 用于验证服务启动与跨域。"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """健康检查响应模型，便于 OpenAPI 文档与前后端对齐。"""

    status: str = Field(..., description="服务状态，阶段 1 固定为 ok")
    service: str = Field(..., description="服务标识，便于多服务环境区分")


@router.get("/health", summary="健康检查", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """返回固定结构；不包含业务逻辑。"""
    return HealthResponse(status="ok", service="heartbeat-lab-api")
