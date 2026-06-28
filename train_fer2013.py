from __future__ import annotations

import argparse
import json
from pathlib import Path

from emotion_model import train_emotion_model


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train and test the FER-2013 emotion model used by the adaptive learning project."
    )

    # Default path added → no need to pass argument every time
    parser.add_argument(
        "--zip-path",
        default=r"data\fer2013.zip",
        help="Path to the FER-2013 dataset zip that contains train/ and test/ folders.",
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=0.03)

    args = parser.parse_args()

    metadata = train_emotion_model(
        zip_path=Path(args.zip_path),
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
    )

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
