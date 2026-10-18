"""Safe source/authorization failure shared with the topic HTTP transport."""

MIN_CHARACTER_TOPICS = 1
MAX_CHARACTER_TOPICS = 24


class TopicPreparationError(ValueError):
    pass
