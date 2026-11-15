"""Versioned support policy; published releases retain their original gates."""
import re


def native_windows(version: str) -> bool:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ValueError("release_version_invalid")
    return tuple(map(int, version.split("."))) < (0, 1, 5)


def platforms(version: str) -> set[str]:
    supported = {"docker-amd64", "docker-arm64", "termux-arm64"}
    return supported | {"windows-x64"} if native_windows(version) else supported
