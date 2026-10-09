"""Runtime identity data must survive the production Docker packaging boundary."""
from pathlib import Path
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


def test_console_entrypoint_has_application_package_path():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    assert "PYTHONPATH=/app" in dockerfile
    assert 'streamlit run dashboard/app.py' in dockerfile

