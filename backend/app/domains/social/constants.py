"""Social response vocabulary and mention syntax."""
import re

DELETED_CHARACTER_NAME = "삭제한 앵무"

MENTION_HANDLE_RE = re.compile(
    r"(?<![A-Za-z0-9_.])@([a-z0-9_]{2,40})(?=$|[^A-Za-z0-9_.]|\.(?=$|[^A-Za-z0-9_]))"
)

REPORT_HIDDEN_TITLE = "숨김 처리된 글"

REPORT_HIDDEN_MESSAGE = "신고 누적으로 숨김 처리된 글입니다."

FEED_SCAN_BODY_PREVIEW_CHARS = 300
