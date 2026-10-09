"""Runtime identity data must survive the production Docker packaging boundary."""
from pathlib import Path
import shutil
import pytest
from dashboard.check_release_assets import check_assets, REQUIRED


def test_identity_crosswalk_is_packaged():
    root = Path(__file__).resolve().parents[1]
    asset = "data/external/player_identity_crosswalk.csv"
    assert (root / asset).is_file()
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert f"COPY {asset} ./{asset}" in dockerfile


def test_build_executes_asset_check_after_data_copy():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    assert dockerfile.index("COPY .streamlit/config.toml") < dockerfile.index("RUN python dashboard/check_release_assets.py")
    assert check_assets(root)["required_assets"] == len(REQUIRED)


def test_missing_identity_asset_blocks_build(tmp_path):
    with pytest.raises(ValueError, match="Required release asset missing"):
        check_assets(tmp_path)


@pytest.mark.parametrize("missing", REQUIRED[:5])
def test_each_required_identity_or_publication_asset_blocks_build(tmp_path, missing):
    root = Path(__file__).resolve().parents[1]
    for name in REQUIRED:
        if name != missing:
            destination = tmp_path / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, destination)
    with pytest.raises(ValueError, match="Required release asset missing"):
        check_assets(tmp_path)


def test_console_entrypoint_has_application_package_path():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    assert "PYTHONPATH=/app" in dockerfile
    assert 'streamlit run dashboard/app.py' in dockerfile


def test_container_uses_pinned_base_and_locked_runtime():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    assert "python:3.12-slim@sha256:" in dockerfile
    assert "-c /tmp/dashboard-requirements.lock" in dockerfile
    pins = (root / "dashboard/requirements.lock").read_text().splitlines()
    assert all("==" in pin for pin in pins if pin.strip())

