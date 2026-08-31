"""Chat v1 policy constants frozen for the P8-L-B structure-only move."""

MAX_ACTIVE_THREADS = 5
CONTEXT_MESSAGE_LIMIT = 20
CONTEXT_CHAR_LIMIT = 12_000
USER_MESSAGE_LIMIT = 2_000
MODEL_OUTPUT_TOKENS = 1024
DEFAULT_MESSAGE_MODEL = "gemini-2.5-flash-lite"
MESSAGE_RESPONSE_LEASE_SECONDS = 150

THREAD_LIMIT_MESSAGE = (
    "쪽지는 최대 5개까지 보관할 수 있습니다. 쪽지함에서 기존 쪽지 내역을 삭제한 뒤 다시 시작해주세요."
)
MODEL_BUSY_MESSAGE = (
    "현재 선택한 모델이 바쁘거나 응답하지 않습니다. 잠시 뒤 다시 시도하거나 다른 모델로 바꿔서 시도해주세요."
)
API_KEY_INVALID_MESSAGE = "API key를 확인해주세요."
API_KEY_MISSING_MESSAGE = "쪽지를 시작하려면 API key를 등록해주세요."
CHARACTER_DISABLED_MESSAGE = "이 앵무는 아직 쪽지를 받을 수 없습니다."
LOCAL_CHARACTER_MESSAGES_DISABLED_MESSAGE = "외부 연결 앵무는 쪽지를 받을 수 없습니다."
PROMPT_INJECTION_BLOCKED_MESSAGE = (
    "그건 말해줄 수 없지만, 다른 이야기는 편하게 해도 돼."
)

MESSAGE_MODELS = {
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
}
