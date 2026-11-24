"""Regras de negócio de autenticação (sem dependência de HTTP)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask_jwt_extended import create_access_token, create_refresh_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.errors import ConflictError, UnauthorizedError
from app.extensions import db
from app.models import User

_hasher = PasswordHasher()
# Hash descartável: permite gastar o mesmo tempo de verificação quando o e-mail não existe,
# evitando que o tempo de resposta revele quais e-mails estão cadastrados.
_DUMMY_HASH = _hasher.hash("timing-attack-mitigation")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def get_user_by_email(email: str) -> User | None:
    return db.session.scalar(select(User).where(User.email == normalize_email(email)))


def register_user(name: str, email: str, password: str) -> User:
    if get_user_by_email(email):
        raise ConflictError("Email already registered.", code="EMAIL_ALREADY_REGISTERED")

    user = User(
        name=name.strip(),
        email=normalize_email(email),
        password_hash=hash_password(password),
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Dois cadastros simultâneos com o mesmo e-mail: a constraint única decide.
        db.session.rollback()
        raise ConflictError("Email already registered.", code="EMAIL_ALREADY_REGISTERED") from None
    return user


def authenticate(email: str, password: str) -> User:
    user = get_user_by_email(email)
    password_hash = user.password_hash if user else _DUMMY_HASH
    valid = verify_password(password_hash, password)
    if user is None or not valid:
        # Mesma mensagem nos dois casos para não revelar se o e-mail existe.
        raise UnauthorizedError("Invalid email or password.", code="INVALID_CREDENTIALS")
    return user


def issue_tokens(user: User) -> dict[str, str]:
    identity = str(user.id)  # o "sub" do JWT precisa ser string
    return {
        "access_token": create_access_token(identity=identity),
        "refresh_token": create_refresh_token(identity=identity),
        "token_type": "Bearer",
    }


def issue_access_token(user_id: int) -> dict[str, str]:
    return {"access_token": create_access_token(identity=str(user_id)), "token_type": "Bearer"}
