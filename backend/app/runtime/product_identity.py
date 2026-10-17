"""Product identity, independent of image tags and persistent data versions."""

import os
import re

PRODUCT_VERSION = "0.1.0"


def validate_product_version() -> str:
    version = os.environ.get("ANGMOO_VERSION", PRODUCT_VERSION)
    if not re.fullmatch(r"0\.1\.0(?:-dev(?:-[0-9a-f]{7,40})?)?", version):
        raise ValueError(
            "product_version_mismatch: Set ANGMOO_VERSION=0.1.0 and select images "
            "with ANGMOO_IMAGE_TAG=release-v0.1.0 before starting. / 시작 전에 "
            "ANGMOO_VERSION=0.1.0으로 설정하고 이미지 선택에는 "
            "ANGMOO_IMAGE_TAG=release-v0.1.0을 사용하세요."
        )
    return version


def runtime_identity() -> dict[str, str]:
    source = os.environ.get("ANGMOO_SOURCE_SHA", "unknown")
    launch = os.environ.get("ANGMOO_LAUNCH_ID", "")
    return {
        "version": PRODUCT_VERSION,
        "source_sha": source if re.fullmatch(r"[0-9a-f]{40}", source) else "unknown",
        "launch_id": launch if re.fullmatch(r"[0-9a-f]{32}", launch) else "",
    }


if __name__ == "__main__":
    validate_product_version()
