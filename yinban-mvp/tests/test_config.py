from app.config import Settings


def test_default_host_allows_lan_access(monkeypatch) -> None:
    monkeypatch.delenv("YINBAN_HOST", raising=False)

    settings = Settings.from_env()

    assert settings.host == "0.0.0.0"


def test_host_can_be_restricted_to_local_machine(monkeypatch) -> None:
    monkeypatch.setenv("YINBAN_HOST", "127.0.0.1")

    settings = Settings.from_env()

    assert settings.host == "127.0.0.1"
