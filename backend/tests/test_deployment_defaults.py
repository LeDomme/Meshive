from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_docker_image_supplies_container_runtime_defaults() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text()

    for default in (
        "MESHIVE_ENVIRONMENT=production",
        "MESHIVE_DATA_DIR=/app/data",
        "MESHIVE_CACHE_DIR=/app/cache",
        "MESHIVE_BACKUP_DIR=/backups",
        "MESHIVE_FRONTEND_DIST=/app/frontend",
    ):
        assert default in dockerfile


def test_standalone_compose_overrides_image_environment_for_trusted_http() -> None:
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text()

    assert "MESHIVE_ENVIRONMENT: ${MESHIVE_ENVIRONMENT:-development}" in compose
    assert "MESHIVE_FIX_PERMISSIONS: ${MESHIVE_FIX_PERMISSIONS:-auto}" in compose


def test_traefik_compose_uses_production_and_forwards_permission_mode() -> None:
    compose = (REPOSITORY_ROOT / "compose.traefik.yaml").read_text()

    assert "MESHIVE_ENVIRONMENT: production" in compose
    assert "MESHIVE_FIX_PERMISSIONS: ${MESHIVE_FIX_PERMISSIONS:-auto}" in compose
