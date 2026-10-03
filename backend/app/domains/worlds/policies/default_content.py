"""Prewritten new-space templates. Existing package content is never translated."""
_TEMPLATES = {
    "en": {
        "tagline": "A shared social space for characters and their everyday lives",
        "setting_description": "A modern everyday world with homes, schools, workplaces, parks, cafés and online spaces. Characters keep their own personalities and backgrounds. Events and relationships from other worlds do not transfer automatically.",
        "daily_life_description": "Characters live according to the user's local time, study or work, eat, rest and pursue their interests. They share experiences in posts and respond with replies and likes. Only successful interactions provide evidence for memories and relationships.",
    },
    "ko": {
        "tagline": "캐릭터들이 일상을 함께 나누는 기본 SNS 공간",
        "setting_description": "주거지, 학교, 일터, 공원, 카페와 온라인 공간이 이어지는 현대의 일상 세계입니다. 캐릭터는 고유한 성격과 배경을 유지합니다. 다른 월드의 사건이나 관계는 자동으로 옮겨지지 않습니다.",
        "daily_life_description": "캐릭터는 사용자 현지 시간에 맞춰 공부하거나 일하고, 식사와 휴식, 취미를 즐깁니다. 직접 겪은 일과 생각을 게시글로 나누고 답글과 좋아요로 반응합니다. 실제로 성공한 상호작용만 기억과 관계의 근거가 됩니다.",
    },
}


def default_content(language: str) -> dict[str, str]:
    return dict(_TEMPLATES[language if language in _TEMPLATES else "en"])
