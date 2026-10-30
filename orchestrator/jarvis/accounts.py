"""Gestión de usuarios, credenciales y vinculación de canales."""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.models import ChannelLink, Credential, LinkCode, User, UserSettings
from jarvis.security import encrypt
from jarvis.timeutil import as_utc, utcnow

LINK_CODE_MINUTES = 15
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O/1/I para evitar confusiones


def create_user(session: Session, name: str, email: str | None = None, timezone: str = "America/Bogota",
                assistant_name: str = "Jarvis") -> User:
    user = User(name=name, email=email, timezone=timezone)
    session.add(user)
    session.flush()
    session.add(UserSettings(user_id=user.id, assistant_name=assistant_name))
    session.flush()
    return user


def set_credential(session: Session, user_id: int, provider: str, secret: str, base_url: str | None = None) -> Credential:
    cred = session.scalar(select(Credential).where(Credential.user_id == user_id, Credential.provider == provider))
    if cred is None:
        cred = Credential(user_id=user_id, provider=provider, secret_encrypted="")
        session.add(cred)
    cred.base_url = base_url
    cred.secret_encrypted = encrypt(secret)
    session.flush()
    return cred


def remove_credential(session: Session, user_id: int, provider: str) -> bool:
    cred = session.scalar(select(Credential).where(Credential.user_id == user_id, Credential.provider == provider))
    if cred is None:
        return False
    session.delete(cred)
    return True


def new_link_code(session: Session, user_id: int, channel: str = "telegram") -> str:
    code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    session.add(LinkCode(code=code, user_id=user_id, channel=channel,
                         expires_at=utcnow() + timedelta(minutes=LINK_CODE_MINUTES)))
    session.flush()
    return code


def redeem_link_code(session: Session, code: str, channel: str, external_id: str) -> User | None:
    """Vincula una identidad externa al usuario dueño del código. Devuelve el usuario o None."""
    row = session.get(LinkCode, code.strip().upper())
    if row is None or row.used_at is not None or row.channel != channel or as_utc(row.expires_at) < utcnow():
        return None

    existing = session.scalar(
        select(ChannelLink).where(ChannelLink.channel == channel, ChannelLink.external_id == external_id)
    )
    if existing:
        existing.user_id = row.user_id
    else:
        session.add(ChannelLink(user_id=row.user_id, channel=channel, external_id=external_id))
    row.used_at = utcnow()
    session.flush()
    return session.get(User, row.user_id)


def user_for_channel(session: Session, channel: str, external_id: str) -> User | None:
    link = session.scalar(
        select(ChannelLink).where(ChannelLink.channel == channel, ChannelLink.external_id == external_id)
    )
    return session.get(User, link.user_id) if link else None


def unlink_channel(session: Session, channel: str, external_id: str) -> bool:
    link = session.scalar(
        select(ChannelLink).where(ChannelLink.channel == channel, ChannelLink.external_id == external_id)
    )
    if link is None:
        return False
    session.delete(link)
    return True
