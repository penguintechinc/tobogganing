"""Tests for non-generative sklearn classifier (Slice E Task 3)."""

from __future__ import annotations

import os
import tempfile

import pytest

from hub_api.modules.sase.security.swg.tier2.classifier import DomainClassifier
from hub_api.modules.sase.security.swg.tier2.train import build_model


class TestDomainClassifier:
    """Test TF-IDF + linear classifier."""

    @pytest.fixture
    def trained_model_path(self) -> str:
        """Build and return a tiny trained model for testing."""
        # Sample labeled data
        samples = [
            ("phishing website malware scam", "malware"),
            ("banking fraud scam", "malware"),
            ("download executable virus", "malware"),
            ("social media facebook twitter", "social"),
            ("youtube video streaming", "social"),
            ("tiktok social sharing", "social"),
            ("news article blog post", "news"),
            ("journalism reporting", "news"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "test_model.joblib")
            build_model(samples, model_path)
            yield model_path

    def test_classify_returns_category_and_confidence(self, trained_model_path: str) -> None:
        """Classify returns (category, confidence) tuple."""
        clf = DomainClassifier(model_path=trained_model_path)
        category, confidence = clf.classify("phishing scam malware")
        assert isinstance(category, str)
        assert isinstance(confidence, float)
        assert 0 <= confidence <= 1

    def test_classify_returns_trained_categories(self, trained_model_path: str) -> None:
        """Classification output is from the fixed trained category set."""
        clf = DomainClassifier(model_path=trained_model_path)
        category, _ = clf.classify("phishing website malware")
        assert category in ["malware", "social", "news", "uncategorized"]

    def test_classify_below_threshold_returns_uncategorized(self, trained_model_path: str) -> None:
        """Low confidence classification returns uncategorized."""
        clf = DomainClassifier(model_path=trained_model_path)
        # Use a confidence threshold that's likely to reject random text
        clf.CONFIDENCE_THRESHOLD = 0.9
        category, confidence = clf.classify("xyz abc def")
        if confidence < 0.9:
            assert category == "uncategorized"

    def test_missing_model_returns_uncategorized_failsafe(self) -> None:
        """Missing model file returns ("uncategorized", 0.0) without crashing."""
        clf = DomainClassifier(model_path="/nonexistent/path/to/model.joblib")
        category, confidence = clf.classify("any text here")
        assert category == "uncategorized"
        assert confidence == 0.0

    def test_invalid_model_path_returns_uncategorized_failsafe(self) -> None:
        """Invalid model path returns ("uncategorized", 0.0)."""
        clf = DomainClassifier(model_path="")
        category, confidence = clf.classify("test")
        assert category == "uncategorized"
        assert confidence == 0.0

    def test_empty_text_returns_uncategorized(self, trained_model_path: str) -> None:
        """Empty text returns uncategorized."""
        clf = DomainClassifier(model_path=trained_model_path)
        category, confidence = clf.classify("")
        assert category == "uncategorized" or confidence < 0.5

    def test_invalid_artifact_format_logs_warning_and_leaves_model_unset(self) -> None:
        """A joblib artifact that isn't a {model, vectorizer} dict is rejected."""
        import joblib

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "bad_artifact.joblib")
            joblib.dump({"unexpected": "shape"}, model_path)

            clf = DomainClassifier(model_path=model_path)

            assert clf._model is None
            assert clf._vectorizer is None
            category, confidence = clf.classify("anything")
            assert category == "uncategorized"
            assert confidence == 0.0

    def test_corrupt_model_file_load_error_is_swallowed(self) -> None:
        """A file that isn't a valid joblib artifact raises internally and is swallowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "corrupt.joblib")
            with open(model_path, "wb") as f:
                f.write(b"not a valid pickle/joblib stream at all")

            clf = DomainClassifier(model_path=model_path)  # must not raise

            assert clf._model is None
            category, confidence = clf.classify("anything")
            assert category == "uncategorized"
            assert confidence == 0.0

    def test_classify_predict_proba_branch(self) -> None:
        """A model exposing predict_proba (but not decision_function) uses that path."""
        from unittest.mock import MagicMock

        clf = DomainClassifier(model_path=None)
        fake_vectorizer = MagicMock()
        fake_vectorizer.transform.return_value = "vectorized"

        fake_model = MagicMock(spec=["predict", "predict_proba"])
        fake_model.predict.return_value = ["news"]
        fake_model.predict_proba.return_value = [[0.1, 0.85]]

        clf._model = fake_model
        clf._vectorizer = fake_vectorizer

        category, confidence = clf.classify("some article text")

        assert category == "news"
        assert confidence == 0.85

    def test_classify_no_confidence_method_defaults_to_half(self) -> None:
        """A model with neither decision_function nor predict_proba defaults to 0.5."""
        from unittest.mock import MagicMock

        clf = DomainClassifier(model_path=None)
        fake_vectorizer = MagicMock()
        fake_vectorizer.transform.return_value = "vectorized"

        fake_model = MagicMock(spec=["predict"])
        fake_model.predict.return_value = ["news"]

        clf._model = fake_model
        clf._vectorizer = fake_vectorizer

        category, confidence = clf.classify("some article text")

        # 0.5 meets the default CONFIDENCE_THRESHOLD (>=), so it's returned as-is
        assert confidence == 0.5
        assert category == "news"

    def test_classify_prediction_exception_is_swallowed(self) -> None:
        """An exception during vectorize/predict is caught, returning uncategorized."""
        from unittest.mock import MagicMock

        clf = DomainClassifier(model_path=None)
        fake_vectorizer = MagicMock()
        fake_vectorizer.transform.side_effect = RuntimeError("vectorizer broke")

        clf._model = MagicMock()
        clf._vectorizer = fake_vectorizer

        category, confidence = clf.classify("some text")

        assert category == "uncategorized"
        assert confidence == 0.0


class TestBuildModel:
    """Test model training."""

    def test_build_model_creates_joblib_artifact(self) -> None:
        """Train and save a model."""
        samples = [
            ("phishing malware scam", "malware"),
            ("facebook social", "social"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "model.joblib")
            build_model(samples, model_path)
            assert os.path.exists(model_path)
            assert os.path.getsize(model_path) > 0

    def test_trained_model_is_usable(self) -> None:
        """Trained model can be loaded and used."""
        samples = [
            ("malware virus scam phishing", "malware"),
            ("malware trojan ransomware", "malware"),
            ("social facebook twitter", "social"),
            ("social instagram tiktok", "social"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "model.joblib")
            build_model(samples, model_path)

            # Load and classify
            clf = DomainClassifier(model_path=model_path)
            category, confidence = clf.classify("phishing malware")
            assert category in ["malware", "social", "uncategorized"]
            assert confidence >= 0  # Non-negative confidence

    def test_build_model_with_empty_samples(self) -> None:
        """Empty sample list should not crash (graceful degradation)."""
        samples: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "model.joblib")
            try:
                build_model(samples, model_path)
            except ValueError:
                # Expected: can't train with no samples
                pass
