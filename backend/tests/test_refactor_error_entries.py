"""An explicit shared error entry grants no HTTP, storage or descendant access."""

from tests.test_refactor_backend_partial_scopes import b, errors, policy


ERRORS = "app.domains.social.exceptions"
CALLER = "app.domains.local_bot.router.bot"


def test_explicit_error_entry_allows_same_class_http_catches_without_domain_completion():
    result = errors(
        b._module(CALLER, imports=(ERRORS,)),
        b._module(ERRORS),
        scope=policy(modules=(ERRORS,), entries=(ERRORS,)),
    )
    assert result == []


def test_error_entry_does_not_open_unlisted_siblings_storage_http_or_deep_modules():
    for target in (
        ERRORS + ".internal",
        "app.domains.social.router",
        "app.domains.social.models.posts",
        "app.domains.social.repository.posts",
        "app.domains.social.service.private_helper",
    ):
        result = errors(
            b._module(CALLER, imports=(target,)),
            b._module(ERRORS),
            b._module(target),
            scope=policy(modules=(ERRORS,), entries=(ERRORS,)),
        )
        assert any("cross_domain_deep_import" in error for error in result)
    result = errors(
        b._module(CALLER, imports=(ERRORS,)),
        b._module(ERRORS),
        scope=policy(modules=(ERRORS,), entries=()),
    )
    assert any("cross_domain_deep_import" in error for error in result)


def test_explicit_error_entry_keeps_framework_and_storage_imports_forbidden():
    for module, expected in (
        (b._module(ERRORS, external=("fastapi",)), "refactor_pure_imports_framework"),
        (b._module(ERRORS, imports=("app.core.db",)), "refactor_pure_imports_io"),
    ):
        result = errors(
            b._module(CALLER, imports=(ERRORS,)),
            module,
            b._module("app.core.db"),
            scope=policy(modules=(ERRORS,), entries=(ERRORS,)),
        )
        assert any(expected in error for error in result)
