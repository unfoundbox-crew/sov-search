"""Compose spec tests — no docker needed, yaml-parse only."""
from pathlib import Path

import yaml

HERE = Path(__file__).parent


def load_compose():
    with open(HERE / "docker-compose.yml") as f:
        return yaml.safe_load(f)


def load_settings():
    with open(HERE / "settings.yml") as f:
        return yaml.safe_load(f)


def test_compose_has_three_replicas():
    compose = load_compose()
    searxng = compose["services"]["searxng"]
    assert searxng["deploy"]["replicas"] == 3


def test_compose_cap_drop_and_caps():
    compose = load_compose()
    searxng = compose["services"]["searxng"]
    assert "ALL" in searxng["cap_drop"]
    for cap in ("CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID"):
        assert cap in searxng["cap_add"]


def test_compose_images_pinned():
    compose = load_compose()
    svcs = compose["services"]
    assert svcs["valkey"]["image"] == "valkey/valkey:8-alpine"
    assert svcs["searxng"]["image"] == "searxng/searxng:latest"
    assert svcs["caddy"]["image"] == "caddy:2-alpine"


def test_settings_limiter_and_private_defaults():
    s = load_settings()
    assert s.get("use_default_settings") is True
    server = s["server"]
    assert server["limiter"] is True
    assert server["image_proxy"] is True
    assert server["public_instance"] is False
    assert server["method"] == "POST"
    assert s["search"]["safe_search"] == 2


def test_settings_google_bing_removed():
    s = load_settings()
    removed = s["engines"]["remove"]
    assert "google" in removed
    assert "bing" in removed


def test_caddyfile_has_x_real_ip():
    text = (HERE / "Caddyfile").read_text()
    assert "X-Real-IP" in text
    assert "X-Forwarded-For" in text
    assert "searxng:8080" in text
    assert "round_robin" in text
