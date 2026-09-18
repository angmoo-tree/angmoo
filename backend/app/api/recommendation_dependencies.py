"""Request-bound topic workflow access; runtime supplies the implementation."""
from fastapi import Request


def recommendation_workflows(request: Request):
    return request.app.state.recommendation_topics
