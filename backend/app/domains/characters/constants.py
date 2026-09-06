"""Character settings and their accepted transport values."""

from typing import Literal

from app.providers.registry import AGENT_GOOGLE_MODELS


AgentGoogleModel = Literal[*AGENT_GOOGLE_MODELS]
GoogleGeminiModel = AgentGoogleModel
ImageKeyMode = Literal["service", "user", "disabled"]
AgentExecutionMode = Literal["llm", "local"]


TENDENCY_ANALYSIS_RETRY_DETAIL = (
    "성향 분석 결과를 정리하지 못했습니다. 잠시 후 다시 시도해주세요."
)
