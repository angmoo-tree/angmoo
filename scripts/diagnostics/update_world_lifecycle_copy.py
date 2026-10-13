"""Apply the scoped ko/en lifecycle copy contract; no generated AI text changes."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLACEMENTS = {
    "저장한 내용은 공개할 준비가 되었어요.": "저장한 내용은 사용할 준비가 되었어요.",
    "공개 전에 아래 항목을 확인해주세요.": "사용 시작 전에 아래 항목을 확인해주세요.",
    "World를 공개했어요.": "World를 사용할 수 있어요.", "공개됨": "사용 가능", "초안": "작성 중",
    "공개 준비 확인": "사용 준비 확인", "World 공개": "World 사용 시작", "공개 준비": "사용 준비",
    "저장한 내용은 공개 준비 완료": "저장한 내용은 사용 준비 완료",
    "아직 저장하지 않은 변경이 있어요. 공개 준비는 마지막으로 저장한 내용을 기준으로 확인해요.": "아직 저장하지 않은 변경이 있어요. 사용 준비는 마지막으로 저장한 내용을 기준으로 확인해요.",
}
COPY = {
    "패키지 내보내기는 World 구성을 보관하는 기능이며, 전체 활동 기록 백업은 아니에요.": "Package export preserves the World configuration; it is not a complete backup of activity history.",
    "사용 가능한 World": "Ready Worlds", "사용 가능": "Ready to use", "작성 중": "Drafts",
    "필수 항목을 채우고 사용을 준비해요.": "Complete the required details to prepare this World for use.",
    "World를 만들고, 초안을 저장하고, 사용을 시작해요.": "Create Worlds, save drafts, and start using them.",
    "첫 World의 사용을 시작하면 기기 홈에서 열 수 있어요.": "Start using your first World to open it from the device home.",
    "사용 준비 완료": "Setup complete", "사용 준비 확인 필요": "Check setup readiness",
    "저장한 내용은 사용할 준비가 되었어요.": "The saved details are ready to use.",
    "사용 시작 전에 아래 항목을 확인해주세요.": "Check the following details before starting to use this World.",
    "World를 사용할 수 있어요.": "This World is ready to use.", "사용 준비 확인": "Check setup readiness",
    "World 사용 시작": "Start using this World", "사용 준비": "Setup readiness",
    "저장한 내용은 사용 준비 완료": "The saved details are ready to use",
    "아직 저장하지 않은 변경이 있어요. 사용 준비는 마지막으로 저장한 내용을 기준으로 확인해요.": "There are unsaved changes. Readiness is checked against the last saved details.",
    "World 삭제": "Delete World", "기본 SNS World는 삭제할 수 없어요.": "The default SNS World cannot be deleted.",
    "이 World를 영구 삭제할까요?": "Permanently delete this World?", "영구 삭제": "Permanently delete",
    "확인을 위해 World 이름을 입력해주세요.": "Enter the World name to confirm.",
    "영구 삭제를 확인했어요.": "I confirm permanent deletion.",
    "삭제가 시작되면 되돌릴 수 없어요.": "Once deletion starts, it cannot be undone.",
    "이 World의 설정, 캐릭터 등록과 활동, 게시글, 채팅, 관계, 기억과 첨부 자료를 삭제해요. 캐릭터의 첫 등록 원본과 재사용에 필요한 초기 이미지·연결, 다른 World의 자료와 공용 설정은 유지돼요.": "Deletes this World's settings, character registrations and activity, posts, chats, relationships, memories, and attachments. Characters' original registration settings, initial images and links needed for reuse, data in other Worlds, and shared settings are kept.",
    "삭제 상태를 확인하지 못했어요.": "Could not check deletion status.",
    "World 내용이 바뀌었어요. 현재 내용을 확인한 뒤 다시 삭제해주세요.": "The World has changed. Review its current details before deleting it.",
    "World를 삭제했어요.": "World deleted.", "World 삭제 중…": "Deleting World…",
    "삭제를 마치지 못했어요. 정리를 다시 시도해주세요.": "Deletion could not finish. Retry the cleanup.",
    "삭제 다시 시도": "Retry deletion",
}
target = ROOT / "frontend/src/features/worlds/components/world-creator-client.tsx"
source = target.read_text(encoding="utf-8")
for old, new in REPLACEMENTS.items():
    source = source.replace('"' + old + '"', '"' + new + '"')
target.write_text(source, encoding="utf-8")
for feature in ("worlds", "creator-studio"):
    for locale in ("ko", "en"):
        path = ROOT / f"frontend/src/features/{feature}/locales/{locale}.json"
        values = json.loads(path.read_text(encoding="utf-8"))
        for key, english in COPY.items():
            values[key] = key if locale == "ko" else english
        path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
