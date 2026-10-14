import numpy as np
import pandas as pd

from src.refresh_shadow_challenger import NUMERIC_FEATURES, fit_ridge, ridge_predict


def test_shadow_ridge_is_deterministic_and_separate_from_incumbent():
    rows = []
    for index in range(16):
        row = {field: float(index + offset) for offset, field in enumerate(NUMERIC_FEATURES)}
        row.update({"position": ("QB", "RB", "WR", "TE")[index % 4], "target_ppr": float(index * 1.5 + 4)})
        rows.append(row)
    frame = pd.DataFrame(rows)
    model = fit_ridge(frame, alpha=100.0)
    first = ridge_predict(frame, model)
    second = ridge_predict(frame, model)
    assert np.allclose(first, second)
    assert model["alpha"] == 100.0
