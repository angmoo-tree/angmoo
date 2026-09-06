"""Shared HTTP Authorization syntax; account and Bot admission remain separate."""

from typing import Annotated

from fastapi import Header, HTTPException, status

AuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization required"
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required"
        )
    return token.strip()
