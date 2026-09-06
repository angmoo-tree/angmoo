"""Tree category, lookup, and related-character errors."""


class TreeServiceError(Exception):
    pass


class TreePostNotFoundError(TreeServiceError):
    pass


class TreeCategoryError(TreeServiceError):
    pass


class TreeNoticeWriteForbiddenError(TreeServiceError):
    pass


class TreeRelatedCharacterError(TreeServiceError):
    pass
