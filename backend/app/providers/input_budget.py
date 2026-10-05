"""Opt-in model limits and full-request counting, independent of runtime/DB."""
from dataclasses import asdict, dataclass
from typing import Protocol

from app.providers.contracts import ProviderRequest


class InputBudgetError(ValueError):
    def __init__(self, code):
        self.validation_code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ModelTokenProfile:
    provider: str
    model: str
    version: str
    input_limit: int
    output_limit: int
    revision: str
    source: str
    checked_at: str
    # Official Gemini input/output limits are independent. No output subtraction.
    context_limit: int | None = None

    def __post_init__(self):
        if (any(type(v) is not int or v <= 0 for v in (self.input_limit, self.output_limit))
                or any(not isinstance(v, str) or not v.strip() for v in
                       (self.provider, self.model, self.version, self.revision, self.source, self.checked_at))
                or (self.context_limit is not None and
                    (type(self.context_limit) is not int or self.context_limit <= 0))):
            raise InputBudgetError("model_budget_unsupported")

    def to_dict(self):
        return asdict(self)

    def permits(self, input_tokens, output_tokens):
        if type(input_tokens) is not int or input_tokens < 0:
            raise InputBudgetError("activity_input_budget_unavailable")
        if type(output_tokens) is not int or output_tokens <= 0 or output_tokens > self.output_limit:
            raise InputBudgetError("model_budget_unsupported")
        return input_tokens <= self.input_limit and (self.context_limit is None or input_tokens + output_tokens <= self.context_limit)


class ModelTokenCounter(Protocol):
    async def profile(self, request: ProviderRequest) -> ModelTokenProfile: ...
    async def count(self, request: ProviderRequest, profile: ModelTokenProfile) -> tuple[int, str]: ...
