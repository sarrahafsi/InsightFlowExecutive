"""
Test rapide du pipeline NLP — à lancer avant de démarrer le serveur.
Vérifie : Sentiment + Emotion + Topic + Business (Ollama)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from connectors.schemas import DataItem
from datetime import datetime

# Messages de test couvrant différents cas business
TEST_MESSAGES = [
    {
        "id": "test-1",
        "content": "We successfully deployed the new feature to production. All tests passed and clients are happy.",
        "expected_sentiment": "POSITIVE",
        "expected_business": "Progress",
    },
    {
        "id": "test-2",
        "content": "We are completely blocked on the API integration. Waiting for the backend team for 3 days now. Deadline is tomorrow.",
        "expected_sentiment": "NEGATIVE",
        "expected_business": "Blocked",
    },
    {
        "id": "test-3",
        "content": "The team has been working 14-hour days for two weeks straight. People are exhausted and making mistakes.",
        "expected_sentiment": "NEGATIVE",
        "expected_business": "Overload",
    },
    {
        "id": "test-4",
        "content": "Weekly status update: sprint 12 is 80% complete, minor delays on task #45.",
        "expected_sentiment": "NEUTRAL",
        "expected_business": "Neutral Update",
    },
]


def make_item(test: dict) -> DataItem:
    return DataItem(
        id=test["id"],
        source="gmail",
        type="email",
        title="Test message",
        content=test["content"],
        author="test@company.com",
        timestamp=datetime.utcnow(),
    )


def run():
    print("\n" + "=" * 60)
    print("  InsightFlow Executive — NLP Pipeline Test")
    print("=" * 60)

    # Import pipeline
    print("\n[1/4] Loading NLP pipeline...")
    from nlp.pipeline import NLPPipeline
    from nlp.sentiment import SentimentProcessor
    from nlp.emotion import EmotionProcessor
    from nlp.topics import TopicProcessor
    from nlp.business import BusinessClassifier

    pipeline = NLPPipeline(steps=[
        SentimentProcessor(),
        EmotionProcessor(),
        TopicProcessor(),
        BusinessClassifier(),
    ])
    print("      Pipeline loaded.\n")

    # Run tests
    print("[2/4] Running test messages...\n")
    for test in TEST_MESSAGES:
        item = make_item(test)
        enriched = pipeline.run(item)

        print(f"  Message : {test['content'][:70]}...")
        print(f"  Sentiment  : {enriched.sentiment_label} ({enriched.sentiment_score})")
        print(f"  Emotion    : {enriched.emotion_label} ({enriched.emotion_score})")
        print(f"  Topic      : {enriched.topic}")
        print(f"  Business   : {enriched.business_label} ({enriched.business_confidence})")
        print(f"  Reason     : {enriched.business_reason}")

        sentiment_ok = enriched.sentiment_label == test["expected_sentiment"]
        business_ok  = enriched.business_label  == test["expected_business"]
        status = "OK" if sentiment_ok else "MISMATCH"
        print(f"  Status     : {status} (expected sentiment={test['expected_sentiment']})")
        print()

    print("=" * 60)
    print("  Test complete.")
    print("=" * 60)


if __name__ == "__main__":
    run()
