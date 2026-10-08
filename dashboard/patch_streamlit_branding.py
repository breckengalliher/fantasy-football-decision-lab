"""Apply The Sunday Decision Lab metadata to Streamlit's static HTML shell.

Social crawlers do not run the Streamlit websocket application, so page_config
alone cannot provide link-preview metadata. This build step keeps the runtime
application untouched while branding the initial HTML response.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TITLE = "The Sunday Decision Lab"
DESCRIPTION = "Compare fantasy football players with projections, trends, injuries, matchups, and live decision context."
SITE_URL = "https://thesundaydecisionlab.com/"
SOCIAL_IMAGE_URL = f"{SITE_URL}static/sdl-social-preview.png"


def streamlit_static_directory() -> Path:
    import streamlit

    return Path(streamlit.__file__).resolve().parent / "static"


def patch_branding(static_directory: Path, asset_directory: Path) -> Path:
    index_path = static_directory / "index.html"
    if not index_path.exists():
        raise FileNotFoundError(f"Streamlit index was not found at {index_path}")

    html = index_path.read_text(encoding="utf-8")
    title_tag = "<title>Streamlit</title>"
    if title_tag not in html and f"<title>{TITLE}</title>" not in html:
        raise RuntimeError("The Streamlit HTML title marker changed; branding was not applied.")

    metadata = f"""<title>{TITLE}</title>
    <meta name="description" content="{DESCRIPTION}" />
    <meta name="theme-color" content="#002244" />
    <link rel="canonical" href="{SITE_URL}" />
    <link rel="apple-touch-icon" href="./sdl-app-icon.png" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="{TITLE}" />
    <meta property="og:title" content="{TITLE}" />
    <meta property="og:description" content="{DESCRIPTION}" />
    <meta property="og:url" content="{SITE_URL}" />
    <meta property="og:image" content="{SOCIAL_IMAGE_URL}" />
    <meta property="og:image:secure_url" content="{SOCIAL_IMAGE_URL}" />
    <meta property="og:image:type" content="image/png" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta property="og:image:alt" content="The Sunday Decision Lab logo" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{TITLE}" />
    <meta name="twitter:description" content="{DESCRIPTION}" />
    <meta name="twitter:image" content="{SOCIAL_IMAGE_URL}" />"""

    if title_tag in html:
        html = html.replace(title_tag, metadata, 1)
        index_path.write_text(html, encoding="utf-8")

    shutil.copyfile(asset_directory / "sunday-decision-lab-icon-clean.png", static_directory / "favicon.png")
    shutil.copyfile(asset_directory / "sunday-decision-lab-icon-clean.png", static_directory / "sdl-app-icon.png")
    shutil.copyfile(asset_directory / "sunday-decision-lab-social-preview.png", static_directory / "sdl-social-preview.png")
    return index_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-dir", type=Path, default=None)
    parser.add_argument("--asset-dir", type=Path, default=Path(__file__).resolve().parent / "assets")
    arguments = parser.parse_args()
    target = arguments.static_dir or streamlit_static_directory()
    patch_branding(target, arguments.asset_dir)
    print(f"Applied Sunday Decision Lab metadata to {target}")


if __name__ == "__main__":
    main()
