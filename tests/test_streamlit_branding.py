from pathlib import Path

from dashboard.patch_streamlit_branding import DESCRIPTION, SITE_URL, TITLE, patch_branding


def test_patch_branding_adds_social_metadata_and_assets(tmp_path: Path) -> None:
    static_directory = tmp_path / "static"
    asset_directory = tmp_path / "assets"
    static_directory.mkdir()
    asset_directory.mkdir()
    (static_directory / "index.html").write_text(
        "<html><head><link rel=\"shortcut icon\" href=\"./favicon.png\" /><title>Streamlit</title></head></html>",
        encoding="utf-8",
    )
    (asset_directory / "sunday-decision-lab-icon-clean.png").write_bytes(b"icon")
    (asset_directory / "sunday-decision-lab-social-preview.png").write_bytes(b"preview")

    patch_branding(static_directory, asset_directory)

    html = (static_directory / "index.html").read_text(encoding="utf-8")
    assert f"<title>{TITLE}</title>" in html
    assert f'content="{DESCRIPTION}"' in html
    assert f'property="og:url" content="{SITE_URL}"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert (static_directory / "favicon.png").read_bytes() == b"icon"
    assert (static_directory / "sdl-app-icon.png").read_bytes() == b"icon"
    assert (static_directory / "sdl-social-preview.png").read_bytes() == b"preview"
