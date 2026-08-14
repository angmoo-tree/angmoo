"""Audit locked dependency licenses and render a deterministic notice."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = Path("security/license_policy.json")
PLATFORM_NODE_PREFIXES = (
    "@img/sharp-",
    "@next/swc-",
)
PLATFORM_PYTHON_LICENSE_FALLBACKS = {
    "colorama": "OSI Approved :: BSD License",
    "tzdata": "Apache-2.0",
}
TOKEN = re.compile(r"\s*(\(|\)|AND|OR|WITH|[A-Za-z0-9][A-Za-z0-9.+:-]*)")


class LicenseAuditError(RuntimeError):
    pass


def _normalized_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _metadata_license(metadata: importlib.metadata.PackageMetadata) -> str:
    expression = (metadata.get("License-Expression") or metadata.get("License") or "").strip()
    if expression and expression.lower() not in {"unknown", "none"}:
        return " ".join(expression.split())
    classifiers = sorted(
        {
            value.removeprefix("License :: ").strip()
            for value in metadata.get_all("Classifier", [])
            if value.startswith("License :: ")
        }
    )
    return " OR ".join(classifiers)


def python_inventory(repo_root: Path) -> list[tuple[str, str, str]]:
    lock_path = repo_root / "backend" / "uv.lock"
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    locked = {
        _normalized_name(item["name"]): str(item["version"])
        for item in lock["package"]
        if _normalized_name(item["name"]) != "backend"
    }
    installed: dict[str, tuple[str, str, str]] = {}
    for distribution in importlib.metadata.distributions():
        name = _normalized_name(distribution.metadata.get("Name") or "")
        if name not in locked:
            continue
        installed[name] = (
            name,
            distribution.version,
            _metadata_license(distribution.metadata),
        )
    missing = sorted(set(locked) - set(installed))
    unsupported_missing = [
        name for name in missing if name not in PLATFORM_PYTHON_LICENSE_FALLBACKS
    ]
    if unsupported_missing:
        raise LicenseAuditError(
            "locked Python packages are not installed: "
            + ", ".join(unsupported_missing)
        )
    for name in missing:
        installed[name] = (
            name,
            locked[name],
            PLATFORM_PYTHON_LICENSE_FALLBACKS[name],
        )
    return sorted(installed.values())


def node_inventory(repo_root: Path) -> list[tuple[str, str, str]]:
    result = subprocess.run(
        ["pnpm.cmd" if os.name == "nt" else "pnpm", "licenses", "list", "--prod", "--json"],
        cwd=repo_root / "frontend",
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise LicenseAuditError(result.stderr.strip() or "pnpm license inventory failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LicenseAuditError("pnpm returned invalid license JSON") from exc

    packages: set[tuple[str, str, str]] = set()
    for license_name, entries in payload.items():
        normalized_license = " ".join(str(license_name).split())
        for entry in entries:
            name = str(entry["name"])
            if name.startswith(PLATFORM_NODE_PREFIXES):
                continue
            for version in entry.get("versions", []):
                packages.add((name, str(version), normalized_license))
    return sorted(packages, key=lambda row: (row[0].lower(), row[1], row[2]))


def load_policy(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LicenseAuditError(f"license policy could not be read: {path}") from exc
    if payload.get("schema_version") != 1:
        raise LicenseAuditError("unsupported license policy schema")
    required_lists = (
        "allowed_license_ids",
        "review_required_license_ids",
        "forbidden_license_ids",
        "allowed_exceptions",
        "dependency_reviews",
    )
    if any(not isinstance(payload.get(key), list) for key in required_lists):
        raise LicenseAuditError("license policy lists are invalid")
    if not isinstance(payload.get("license_aliases"), dict):
        raise LicenseAuditError("license aliases are invalid")
    if not isinstance(payload.get("metadata_overrides"), list):
        raise LicenseAuditError("metadata overrides are invalid")
    return payload


def normalize_expression(
    ecosystem: str,
    name: str,
    expression: str,
    policy: dict[str, Any],
) -> str:
    reported = " ".join(expression.split())
    for override in policy["metadata_overrides"]:
        if not isinstance(override, dict):
            raise LicenseAuditError("metadata override must be an object")
        if (
            override.get("ecosystem") == ecosystem
            and _normalized_name(str(override.get("name", ""))) == _normalized_name(name)
            and override.get("reported_expression") == reported
        ):
            normalized = override.get("normalized_expression")
            if not isinstance(normalized, str) or not normalized:
                raise LicenseAuditError("metadata override has no normalized expression")
            return normalized

    aliases = {
        str(key).casefold(): str(value)
        for key, value in policy["license_aliases"].items()
    }
    normalized = aliases.get(reported.casefold(), reported)
    normalized = re.sub(
        r"(?<![A-Za-z0-9.+:-])(and|or|with)(?![A-Za-z0-9.+:-])",
        lambda match: match.group(1).upper(),
        normalized,
        flags=re.IGNORECASE,
    )
    return " ".join(normalized.split())


class _ExpressionParser:
    def __init__(self, expression: str) -> None:
        self.expression = expression
        self.tokens = self._tokenize(expression)
        self.index = 0

    @staticmethod
    def _tokenize(expression: str) -> list[str]:
        if not expression:
            raise LicenseAuditError("empty license expression")
        tokens: list[str] = []
        position = 0
        while position < len(expression):
            match = TOKEN.match(expression, position)
            if match is None:
                raise LicenseAuditError(
                    f"unsupported license expression syntax near {expression[position:]!r}"
                )
            tokens.append(match.group(1))
            position = match.end()
        return tokens

    def parse(self) -> tuple[set[str], set[str]]:
        licenses, exceptions = self._parse_or()
        if self.index != len(self.tokens):
            raise LicenseAuditError(
                f"unexpected license expression token {self.tokens[self.index]!r}"
            )
        return licenses, exceptions

    def _parse_or(self) -> tuple[set[str], set[str]]:
        licenses, exceptions = self._parse_and()
        while self._peek() == "OR":
            self.index += 1
            right_licenses, right_exceptions = self._parse_and()
            licenses |= right_licenses
            exceptions |= right_exceptions
        return licenses, exceptions

    def _parse_and(self) -> tuple[set[str], set[str]]:
        licenses, exceptions = self._parse_with()
        while self._peek() == "AND":
            self.index += 1
            right_licenses, right_exceptions = self._parse_with()
            licenses |= right_licenses
            exceptions |= right_exceptions
        return licenses, exceptions

    def _parse_with(self) -> tuple[set[str], set[str]]:
        licenses, exceptions = self._parse_primary()
        if self._peek() == "WITH":
            self.index += 1
            exception = self._take_identifier("license exception")
            exceptions.add(exception)
        return licenses, exceptions

    def _parse_primary(self) -> tuple[set[str], set[str]]:
        if self._peek() == "(":
            self.index += 1
            licenses, exceptions = self._parse_or()
            if self._peek() != ")":
                raise LicenseAuditError("unbalanced license expression parentheses")
            self.index += 1
            return licenses, exceptions
        return {self._take_identifier("license id")}, set()

    def _take_identifier(self, label: str) -> str:
        token = self._peek()
        if token is None or token in {"(", ")", "AND", "OR", "WITH"}:
            raise LicenseAuditError(f"expected {label}")
        self.index += 1
        return token

    def _peek(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]


def parse_expression(expression: str) -> tuple[set[str], set[str]]:
    return _ExpressionParser(expression).parse()


def _review_lookup(policy: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    reviews: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in policy["dependency_reviews"]:
        if not isinstance(record, dict):
            raise LicenseAuditError("dependency review must be an object")
        key = (
            str(record.get("ecosystem", "")),
            _normalized_name(str(record.get("name", ""))),
            str(record.get("version", "")),
        )
        if not all(key) or key in reviews:
            raise LicenseAuditError(f"invalid or duplicate dependency review: {key}")
        reviews[key] = record
    return reviews


def validate_inventory(
    ecosystem: str,
    packages: list[tuple[str, str, str]],
    policy: dict[str, Any],
    policy_label: str,
) -> set[tuple[str, str, str]]:
    if not packages:
        raise LicenseAuditError(f"{ecosystem} dependency inventory is empty")
    allowed = set(policy["allowed_license_ids"])
    review_required = set(policy["review_required_license_ids"])
    forbidden = set(policy["forbidden_license_ids"])
    allowed_exceptions = set(policy["allowed_exceptions"])
    reviews = _review_lookup(policy)
    used_reviews: set[tuple[str, str, str]] = set()
    failures: list[str] = []

    ecosystem_key = ecosystem.lower()
    for name, version, reported in packages:
        normalized = normalize_expression(ecosystem_key, name, reported, policy)
        reason = ""
        try:
            license_ids, exceptions = parse_expression(normalized)
        except LicenseAuditError as exc:
            reason = str(exc)
            license_ids, exceptions = set(), set()

        blocked = sorted(license_ids & forbidden)
        unknown = sorted(license_ids - allowed - forbidden)
        unsupported_exceptions = sorted(exceptions - allowed_exceptions)
        if blocked:
            reason = "forbidden license ids: " + ", ".join(blocked)
        elif unknown:
            reason = "unknown license ids: " + ", ".join(unknown)
        elif unsupported_exceptions:
            reason = "unapproved license exceptions: " + ", ".join(unsupported_exceptions)
        elif not license_ids and not reason:
            reason = "license expression has no ids"
        elif license_ids & review_required:
            review_key = (ecosystem_key, _normalized_name(name), version)
            review = reviews.get(review_key)
            if review is None:
                reason = "conditional license requires an exact package/version review"
            elif review.get("reported_expression") != reported:
                reason = "conditional review reported expression drift"
            elif review.get("normalized_expression") != normalized:
                reason = "conditional review normalized expression drift"
            else:
                obligations = review.get("obligations")
                if not isinstance(obligations, list) or not obligations:
                    reason = "conditional review has no obligations"
                else:
                    used_reviews.add(review_key)

        if reason:
            failures.append(
                f"ecosystem={ecosystem_key} package={name}@{version} "
                f"reported={reported or 'unknown'} normalized={normalized or 'unknown'} "
                f"result=blocked reason={reason} policy={policy_label}"
            )

    if failures:
        raise LicenseAuditError("; ".join(failures))
    return used_reviews


def _render_review(record: dict[str, Any]) -> list[str]:
    lines = [
        f"### `{record['ecosystem']}/{record['name']} {record['version']}`",
        "",
        f"- Reported license: `{record['reported_expression']}`",
        f"- Normalized license: `{record['normalized_expression']}`",
        f"- Distribution boundary: {record['distribution_boundary']}",
        f"- Upstream license source: <{record['source']}>",
        "- Recorded obligations:",
    ]
    lines.extend(f"  - {value}" for value in record["obligations"])
    lines.append("")
    return lines


def render_notice(
    python_packages: list[tuple[str, str, str]],
    node_packages: list[tuple[str, str, str]],
    policy: dict[str, Any],
) -> str:
    lines = [
        "# Third-party notices",
        "",
        "This inventory is generated from the locked Angmoo dependencies.",
        "Package authors retain all rights granted by their respective licenses.",
        "",
        f"## Python packages ({len(python_packages)})",
        "",
    ]
    lines.extend(
        f"- `{name} {version}` — {license_name}"
        for name, version, license_name in python_packages
    )
    lines.extend(
        [
            "",
            f"## JavaScript production packages ({len(node_packages)})",
            "",
        ]
    )
    lines.extend(
        f"- `{name} {version}` — {license_name}"
        for name, version, license_name in node_packages
    )
    lines.extend(["", "## Reviewed conditional dependencies", ""])
    for record in sorted(
        policy["dependency_reviews"],
        key=lambda item: (item["ecosystem"], item["name"], item["version"]),
    ):
        lines.extend(_render_review(record))

    lines.extend(
        [
            "## Infrastructure and build tooling",
            "",
            "These services and CI tools are separate components and retain their own licenses.",
            "",
        ]
    )
    for record in [*policy["infrastructure"], *policy["actions"]]:
        lines.append(
            f"- **{record['name']}** — `{record['license_expression']}`; "
            f"reference `{record['reference']}`; source <{record['source']}>"
        )

    lines.extend(
        [
            "",
            "## Bundled assets and content",
            "",
        ]
    )
    for record in policy["assets"]:
        detail = record.get("note") or f"source <{record.get('source')}>"
        lines.append(
            f"- **{record['name']}** — `{record['license_expression']}`; {detail}"
        )
    for record in policy["bundled_content"]:
        lines.append(
            f"- `{record['path']}` — {record['classification']}; "
            f"`{record['license_expression']}`"
        )

    lines.extend(["", "## License scope boundary", ""])
    for key in ("application", "world_packages", "runtime_data", "third_party"):
        lines.append(f"- **{key.replace('_', ' ').title()}**: {policy['scope'][key]}")
    lines.extend(
        [
            "",
            "This notice does not replace license text distributed by an individual dependency.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--write-notice", type=Path)
    parser.add_argument("--check-notice", type=Path)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    policy_path = (args.policy or (repo_root / DEFAULT_POLICY_PATH)).resolve()
    try:
        policy = load_policy(policy_path)
        python_packages = python_inventory(repo_root)
        node_packages = node_inventory(repo_root)
        used_reviews = validate_inventory(
            "Python", python_packages, policy, policy_path.as_posix()
        )
        used_reviews |= validate_inventory(
            "Node", node_packages, policy, policy_path.as_posix()
        )
        declared_reviews = set(_review_lookup(policy))
        if used_reviews != declared_reviews:
            unused = sorted(declared_reviews - used_reviews)
            raise LicenseAuditError(
                "stale conditional dependency reviews: "
                + ", ".join("/".join(value) for value in unused)
            )
        notice = render_notice(python_packages, node_packages, policy)
        if args.write_notice is not None:
            args.write_notice.resolve().write_text(
                notice, encoding="utf-8", newline="\n"
            )
        if args.check_notice is not None:
            current = args.check_notice.resolve().read_text(encoding="utf-8")
            if current != notice:
                raise LicenseAuditError("third-party notice does not match locked dependencies and policy")
    except (OSError, LicenseAuditError) as exc:
        print(f"Dependency license audit failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Dependency license audit passed: "
        f"python={len(python_packages)} node={len(node_packages)} "
        f"conditional_reviews={len(used_reviews)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
