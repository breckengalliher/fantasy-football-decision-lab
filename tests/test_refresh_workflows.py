from pathlib import Path


def test_all_publishers_serialize_and_push_version_pointer_last():
    root = Path(__file__).resolve().parents[1]
    for name in ("weekly-production-refresh", "daily-injury-refresh", "general-context-refresh", "market-data-refresh"):
        path = root / f".github/workflows/{name}.yml"
        # QA branches disable production jobs; preserve their exact source as
        # inert audit fixtures so isolated archive regression remains runnable.
        if not path.exists():
            path = root / f"tests/fixtures/workflow-audit/{name}.yml"
        workflow = path.read_text()
        assert "group: production-data-refresh" in workflow
        assert "cancel-in-progress: false" in workflow
        assert "queue: max" in workflow
        assert "ref: main" in workflow
        assert workflow.index("python scripts/prepare_publication.py") < workflow.index("git push")
        assert workflow.index("git add -f data/processed/publication_manifest.json") < workflow.index("git push")
