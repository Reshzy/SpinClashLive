from color_rush.observability import configure_logging, redact_event_dict


def test_redact_tokens_and_nested_secrets() -> None:
    event = redact_event_dict(
        None,
        "info",
        {
            "token": "super-secret",
            "password": "hunter2",
            "player_id": "abc",
            "nested": {"api_key": "AIzaShouldNotAppear", "ok": 1},
        },
    )
    assert event["token"] == "[redacted]"
    assert event["password"] == "[redacted]"
    assert event["player_id"] == "abc"
    assert event["nested"]["api_key"] == "[redacted]"
    assert event["nested"]["ok"] == 1


def test_configure_logging_does_not_raise() -> None:
    configure_logging()


def test_create_app_configures_logging() -> None:
    from color_rush.api.app import create_app

    create_app()
