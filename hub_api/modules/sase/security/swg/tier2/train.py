"""Training script for Tier-2 AI categorizer (Slice E Task 3).

NOT run at request time. Used to build the model artifact offline:
1. Collect labeled domain samples from domain_categories
2. Train TF-IDF + linear classifier
3. Save joblib artifact

Run manually or via a scheduled job to update the model.
"""
from __future__ import annotations

import joblib
import structlog
from typing import Iterable

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline

logger = structlog.get_logger()

__all__ = ["build_model"]


def build_model(samples: Iterable[tuple[str, str]], output_path: str) -> None:
    """Train and save a TF-IDF + LinearSVC model.

    Args:
        samples: Iterable of (text, category) tuples.
        output_path: Path to save joblib artifact.

    Raises:
        ValueError: If samples list is empty.
    """
    samples_list = list(samples)

    if not samples_list:
        raise ValueError("Cannot train model with zero samples")

    # Extract texts and labels
    texts = [s[0] for s in samples_list]
    labels = [s[1] for s in samples_list]

    # Build TF-IDF vectorizer + LinearSVC
    vectorizer = TfidfVectorizer(
        max_features=1000,
        stop_words="english",
        lowercase=True,
        strip_accents="unicode",
    )

    model = LinearSVC(
        loss="squared_hinge",
        dual=False,
        max_iter=1000,
        random_state=42,
        verbose=0,
    )

    # Train
    try:
        X = vectorizer.fit_transform(texts)
        model.fit(X, labels)

        logger.info(
            "model_trained",
            samples=len(samples_list),
            features=X.shape[1],
            classes=len(set(labels)),
        )
    except Exception as e:
        logger.error("model_training_failed", error=str(e))
        raise

    # Save as joblib artifact
    artifact = {
        "model": model,
        "vectorizer": vectorizer,
    }

    try:
        joblib.dump(artifact, output_path)
        logger.info("model_saved", output_path=output_path)
    except Exception as e:
        logger.error("model_save_failed", output_path=output_path, error=str(e))
        raise


if __name__ == "__main__":
    # Example: train on dummy data
    dummy_samples = [
        ("malware phishing scam virus", "malware"),
        ("ransomware trojan botnet", "malware"),
        ("facebook twitter social media", "social"),
        ("instagram tiktok sharing", "social"),
        ("news article blog journalism", "news"),
        ("reporting opinion editorial", "news"),
    ]

    import os

    output_path = os.path.join(os.path.dirname(__file__), "domain_classifier.joblib")
    build_model(dummy_samples, output_path)
    print(f"Model saved to {output_path}")
