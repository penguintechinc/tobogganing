"""Non-generative TF-IDF + linear classifier for Tier-2 AI categorizer (Slice E Task 3).

Loads a pre-trained sklearn model (joblib artifact) and classifies text.
Outputs are from a fixed, finite category set (non-generative).
Gracefully fails to ("uncategorized", 0.0) if model is missing/unloadable.
"""
from __future__ import annotations

import os
from typing import Optional

import joblib
import structlog

logger = structlog.get_logger()

__all__ = ["DomainClassifier"]


class DomainClassifier:
    """TF-IDF + linear SVM/LogisticRegression classifier.

    Loads a pre-trained joblib model artifact and classifies text.
    Outputs are from a fixed category set; below confidence threshold → uncategorized.
    Fail-safe: missing/unloadable model → ("uncategorized", 0.0) without crash.
    """

    CONFIDENCE_THRESHOLD: float = 0.5  # Output uncategorized if confidence below this

    def __init__(self, model_path: Optional[str] = None) -> None:
        """Initialize classifier.

        Args:
            model_path: Path to joblib model artifact. If None or missing, classifier
                        will return ("uncategorized", 0.0) for all classifications.
        """
        self.model_path = model_path
        self._model = None
        self._vectorizer = None

        if model_path:
            self._load_model(model_path)

    def _load_model(self, model_path: str) -> None:
        """Load model and vectorizer from joblib artifact.

        NOTE: joblib.load uses pickle, but this is safe because:
        - Model is self-trained locally by train.py
        - Never loaded from user input or untrusted sources
        - Artifact is stored in trusted location (codebase/deployment)
        - joblib is pinned to specific version in requirements

        Args:
            model_path: Path to joblib artifact (dict with 'model' and 'vectorizer').
        """
        try:
            if not os.path.exists(model_path):
                logger.debug("classifier_model_missing", model_path=model_path)
                return

            artifact = joblib.load(model_path)
            if isinstance(artifact, dict) and "model" in artifact and "vectorizer" in artifact:
                self._model = artifact["model"]
                self._vectorizer = artifact["vectorizer"]
                logger.info("classifier_model_loaded", model_path=model_path)
            else:
                logger.warning("classifier_artifact_invalid_format", model_path=model_path)
        except Exception as e:
            logger.warning("classifier_load_error", model_path=model_path, error=str(e))

    def classify(self, text: str) -> tuple[str, float]:
        """Classify text to a category.

        Args:
            text: Text to classify.

        Returns:
            Tuple of (category, confidence). If model not loaded or confidence
            below threshold, returns ("uncategorized", 0.0).
        """
        if not self._model or not self._vectorizer:
            return ("uncategorized", 0.0)

        try:
            # Vectorize text
            X = self._vectorizer.transform([text])

            # Predict
            prediction = self._model.predict(X)[0]

            # Get confidence (decision function or probability)
            if hasattr(self._model, "decision_function"):
                # LinearSVC uses decision_function
                decision = self._model.decision_function(X)[0]
                # Normalize decision score to [0, 1] (simplified)
                confidence = min(1.0, max(0.0, (decision + 2) / 4))
            elif hasattr(self._model, "predict_proba"):
                # LogisticRegression uses predict_proba
                proba = self._model.predict_proba(X)[0]
                confidence = max(proba)
            else:
                confidence = 0.5  # Default

            # Check threshold
            if confidence < self.CONFIDENCE_THRESHOLD:
                return ("uncategorized", confidence)

            return (str(prediction), float(confidence))

        except Exception as e:
            logger.warning("classifier_error", error=str(e))
            return ("uncategorized", 0.0)
