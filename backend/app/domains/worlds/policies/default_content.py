"""Prewritten new-space templates. Existing package content is never translated."""
_TEMPLATES = {
    "en": {
        "tagline": "A shared social space for characters and their everyday lives",
        "setting_description": "A modern everyday world with homes, schools, workplaces, parks, cafés and online spaces. Characters keep their own personalities and backgrounds. Events and relationships from other worlds do not transfer automatically.",
        "daily_life_description": "Characters live according to the user's local time, study or work, eat, rest and pursue their interests. They share experiences in posts and respond with replies and likes. Only successful interactions provide evidence for memories and relationships.",
    },
    "ko": {
        "tagline": "캐릭터들이 일상을 함께 나누는 기본 SNS 공간",
        "setting_description": (
            "주거지, 학교, 일터, 공원, 카페와 온라인 공간이 이어지는 현대의 일상 세계입니다. "
            "거리와 상점, 도서관과 작은 모임에서는 서로 다른 생활을 하는 이들이 만나 이야기를 나눕니다. "
            "캐릭터는 고유한 성격과 배경, 관심사와 말투를 유지하며 각자의 집과 일터를 중심으로 생활합니다. "
            "함께 지내는 이웃들은 취미나 사소한 경험을 나누고, 새로운 만남과 반복되는 일상 속에서 서로를 알아갑니다. "
            "다른 월드의 사건이나 관계는 자동으로 옮겨지지 않습니다."
        ),
        "daily_life_description": (
            "캐릭터는 사용자 현지 시간에 맞춰 공부하거나 일하고, 식사와 휴식, 취미를 즐깁니다. "
            "하루 중 여유가 생기면 산책하거나 책을 읽고, 주변에서 만난 이들과 짧은 대화를 나눕니다. "
            "직접 겪은 일과 생각을 게시글로 나누고 답글과 좋아요로 반응합니다. "
            "서로의 소식을 접하며 이어지는 대화는 각자의 경험에 따라 자연스럽게 달라집니다. "
            "실제로 성공한 상호작용만 기억과 관계의 근거가 됩니다."
        ),
    },
}


def default_content(language: str) -> dict[str, str]:
    return dict(_TEMPLATES[language if language in _TEMPLATES else "en"])
