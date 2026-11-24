"""Testes unitários das regras de autenticação."""

import pytest
from flask import Flask

from app.errors import ConflictError, UnauthorizedError
from app.services import auth_service


def test_password_is_hashed_with_argon2() -> None:
    hashed = auth_service.hash_password("senha-segura-123")
    assert hashed != "senha-segura-123"
    assert hashed.startswith("$argon2")
    assert auth_service.verify_password(hashed, "senha-segura-123")
    assert not auth_service.verify_password(hashed, "outra-senha")


def test_verify_password_with_garbage_hash_is_false() -> None:
    assert auth_service.verify_password("not-a-hash", "x") is False


def test_register_normalizes_email_and_never_stores_plain_password(app: Flask) -> None:
    with app.app_context():
        user = auth_service.register_user("  Ana  ", "  ANA@Salao.com ", "senha-segura-123")
        assert user.email == "ana@salao.com"
        assert user.name == "Ana"
        assert "senha-segura-123" not in user.password_hash


def test_register_duplicate_email_is_case_insensitive(app: Flask) -> None:
    with app.app_context():
        auth_service.register_user("Ana", "ana@salao.com", "senha-segura-123")
        with pytest.raises(ConflictError) as exc:
            auth_service.register_user("Outra", "ANA@salao.com", "senha-segura-123")
        assert exc.value.code == "EMAIL_ALREADY_REGISTERED"


def test_authenticate_success(app: Flask) -> None:
    with app.app_context():
        created = auth_service.register_user("Ana", "ana@salao.com", "senha-segura-123")
        assert auth_service.authenticate("ANA@salao.com", "senha-segura-123").id == created.id


@pytest.mark.parametrize(
    ("email", "password"),
    [("ana@salao.com", "errada-errada"), ("naoexiste@salao.com", "senha-segura-123")],
)
def test_authenticate_failure_is_identical_for_wrong_password_and_unknown_email(
    app: Flask, email: str, password: str
) -> None:
    with app.app_context():
        auth_service.register_user("Ana", "ana@salao.com", "senha-segura-123")
        with pytest.raises(UnauthorizedError) as exc:
            auth_service.authenticate(email, password)
        assert exc.value.code == "INVALID_CREDENTIALS"
        assert exc.value.message == "Invalid email or password."
