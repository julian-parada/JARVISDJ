"""Cifrado de credenciales por usuario."""

from cryptography.fernet import Fernet, InvalidToken

from jarvis.config import get_settings


class SecurityError(RuntimeError):
    pass


def generate_key() -> str:
    return Fernet.generate_key().decode()


def _fernet() -> Fernet:
    key = get_settings().jarvis_master_key
    if not key:
        raise SecurityError("Falta JARVIS_MASTER_KEY en el .env (genérala con: jarvis gen-key)")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise SecurityError("JARVIS_MASTER_KEY no es una clave Fernet válida") from exc


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecurityError("No se pudo descifrar la credencial (¿cambió la clave maestra?)") from exc
