"""Coverage tests for train.py's exception branches and __main__ entry point."""

from __future__ import annotations

import runpy
from unittest.mock import patch

import pytest

from hub_api.modules.sase.security.swg.tier2 import train
from hub_api.modules.sase.security.swg.tier2.train import build_model

TRAIN_MOD = "hub_api.modules.sase.security.swg.tier2.train"


class TestBuildModelExceptions:
    """Covers build_model's training and save exception-propagation branches."""

    def test_training_exception_is_logged_and_reraised(self) -> None:
        """A failure inside model.fit() is logged and re-raised (not swallowed)."""
        with patch(f"{TRAIN_MOD}.LinearSVC") as MockSVC:
            MockSVC.return_value.fit.side_effect = RuntimeError("training blew up")

            with pytest.raises(RuntimeError, match="training blew up"):
                build_model([("text one", "a"), ("text two", "b")], "/tmp/unused.joblib")

    def test_save_exception_is_logged_and_reraised(self) -> None:
        """A failure inside joblib.dump() is logged and re-raised (not swallowed)."""
        with patch(f"{TRAIN_MOD}.joblib.dump", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                build_model(
                    [("text one", "a"), ("text two", "b"), ("text three", "a")],
                    "/tmp/unused.joblib",
                )


class TestMainEntryPoint:
    """Covers the `if __name__ == "__main__":` script block via runpy."""

    def test_main_block_trains_and_saves_dummy_model(self) -> None:
        """Running train.py as a script trains on the dummy samples and saves.

        joblib.dump is patched to avoid writing a real artifact into the
        source tree during tests.
        """
        with patch(f"{TRAIN_MOD}.joblib.dump") as mock_dump:
            runpy.run_path(train.__file__, run_name="__main__")

        mock_dump.assert_called_once()
        artifact = mock_dump.call_args[0][0]
        assert "model" in artifact
        assert "vectorizer" in artifact
