import os

from cryptography.fernet import Fernet

os.environ.setdefault("JARVIS_MASTER_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import pytest  # noqa: E402

from jarvis.config import Settings, get_settings  # noqa: E402
from jarvis.db import create_all, init_engine, session_scope  # noqa: E402

HUB_URL = "http://hub.test"


@pytest.fixture
def settings(tmp_path) -> Settings:
    get_settings.cache_clear()
    url = f"sqlite:///{tmp_path / 'test.db'}"
    init_engine(url)
    create_all()
    return Settings(database_url=url, claude_model="test-model")


@pytest.fixture
def local_user_id(settings) -> int:
    """Usuario sin Personal Hub: usa el almacén local."""
    from jarvis import accounts

    with session_scope() as s:
        return accounts.create_user(s, name="Julian", email="local@test.co").id


@pytest.fixture
def user_id(settings) -> int:
    """Usuario con Personal Hub conectado."""
    from jarvis import accounts

    with session_scope() as s:
        user = accounts.create_user(s, name="Julian", email="j@test.co")
        accounts.set_credential(s, user.id, "personal_hub", "secret-token", base_url=HUB_URL)
        return user.id
