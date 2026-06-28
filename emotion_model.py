from __future__ import annotations

import base64
import csv
import json
import zipfile
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

from platform_db import DATA_DIR, record_training_run


MODEL_DIR = DATA_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

FER_DATASET_DIR = DATA_DIR / "fer2013"
FER_MODEL_PATH = MODEL_DIR / "fer2013_emotion_mlp.npz"
FER_HISTORY_PATH = MODEL_DIR / "fer2013_training_history.json"
FER_CONFUSION_MATRIX_PATH = MODEL_DIR / "fer2013_confusion_matrix.csv"

EMOTION_LABELS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
IMAGE_SIZE = (48, 48)
INPUT_DIM = IMAGE_SIZE[0] * IMAGE_SIZE[1]
HIDDEN_UNITS = 128

_MODEL_CACHE: dict[str, object] = {"path": None, "weights": None}


def _image_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for extension in ("*.jpg", "*.jpeg", "*.png"):
        paths.extend(root.rglob(extension))
    return sorted(paths)


def _one_hot(indices: np.ndarray, class_count: int) -> np.ndarray:
    encoded = np.zeros((indices.shape[0], class_count), dtype=np.float32)
    encoded[np.arange(indices.shape[0]), indices] = 1.0
    return encoded


def _softmax(logits: np.ndarray) -> np.ndarray:
    stabilized = logits - np.max(logits, axis=1, keepdims=True)
    exp_values = np.exp(stabilized)
    return exp_values / np.sum(exp_values, axis=1, keepdims=True)


def _load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    resized = cv2.resize(image, IMAGE_SIZE)
    normalized = resized.astype(np.float32) / 255.0
    return normalized.reshape(-1)


def ensure_dataset_extracted(zip_path: str | Path, destination: Path = FER_DATASET_DIR) -> Path:
    archive_path = Path(zip_path)
    train_dir = destination / "train"
    test_dir = destination / "test"
    if train_dir.exists() and test_dir.exists():
        return destination

    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as archive:
        archive.extractall(destination)
    return destination


def _load_split(split_root: Path, class_names: list[str]) -> tuple[np.ndarray, np.ndarray]:
    vectors: list[np.ndarray] = []
    labels: list[int] = []
    for label_index, class_name in enumerate(class_names):
        class_dir = split_root / class_name
        if not class_dir.exists():
            continue
        for path in _image_paths(class_dir):
            vectors.append(_load_image(path))
            labels.append(label_index)
    if not vectors:
        raise ValueError(f"No images found under {split_root}")
    return np.stack(vectors).astype(np.float32), np.array(labels, dtype=np.int32)


def _train_validation_split(
    features: np.ndarray,
    labels: np.ndarray,
    validation_ratio: float = 0.1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    indices = np.arange(features.shape[0])
    rng.shuffle(indices)
    split_index = int(features.shape[0] * (1.0 - validation_ratio))
    train_indices = indices[:split_index]
    val_indices = indices[split_index:]
    return (
        features[train_indices],
        labels[train_indices],
        features[val_indices],
        labels[val_indices],
    )


def _forward(
    features: np.ndarray,
    w1: np.ndarray,
    b1: np.ndarray,
    w2: np.ndarray,
    b2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    hidden_linear = features @ w1 + b1
    hidden = np.maximum(hidden_linear, 0.0)
    logits = hidden @ w2 + b2
    return hidden, _softmax(logits)


def _loss_and_accuracy(probabilities: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    eps = 1e-8
    chosen = probabilities[np.arange(labels.shape[0]), labels]
    loss = float(-np.mean(np.log(chosen + eps)))
    accuracy = float(np.mean(np.argmax(probabilities, axis=1) == labels))
    return loss, accuracy


def _iter_batches(
    features: np.ndarray,
    labels: np.ndarray,
    batch_size: int,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng()
    indices = np.arange(features.shape[0])
    rng.shuffle(indices)
    for start in range(0, features.shape[0], batch_size):
        batch_indices = indices[start : start + batch_size]
        yield features[batch_indices], labels[batch_indices]


def _write_confusion_matrix(confusion_matrix: np.ndarray, class_names: list[str]) -> None:
    with FER_CONFUSION_MATRIX_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["label", *class_names])
        for index, label in enumerate(class_names):
            writer.writerow([label, *confusion_matrix[index].tolist()])


def train_emotion_model(
    *,
    zip_path: str | Path,
    epochs: int = 5,
    batch_size: int = 128,
    learning_rate: float = 0.05,
) -> dict[str, object]:
    dataset_root = ensure_dataset_extracted(zip_path)
    train_root = dataset_root / "train"
    test_root = dataset_root / "test"

    class_names = [label for label in EMOTION_LABELS if (train_root / label).exists()]
    if not class_names:
        raise ValueError("FER2013 training folders were not found after extraction.")

    train_features_all, train_labels_all = _load_split(train_root, class_names)
    test_features, test_labels = _load_split(test_root, class_names)
    train_features, train_labels, val_features, val_labels = _train_validation_split(
        train_features_all,
        train_labels_all,
        validation_ratio=0.1,
    )

    rng = np.random.default_rng(42)
    class_count = len(class_names)
    w1 = rng.normal(0.0, np.sqrt(2.0 / INPUT_DIM), size=(INPUT_DIM, HIDDEN_UNITS)).astype(np.float32)
    b1 = np.zeros((1, HIDDEN_UNITS), dtype=np.float32)
    w2 = rng.normal(0.0, np.sqrt(2.0 / HIDDEN_UNITS), size=(HIDDEN_UNITS, class_count)).astype(np.float32)
    b2 = np.zeros((1, class_count), dtype=np.float32)

    history = {"loss": [], "accuracy": [], "val_loss": [], "val_accuracy": []}

    for _ in range(epochs):
        for batch_features, batch_labels in _iter_batches(train_features, train_labels, batch_size):
            hidden, probabilities = _forward(batch_features, w1, b1, w2, b2)
            targets = _one_hot(batch_labels, class_count)
            batch_size_current = batch_features.shape[0]

            grad_logits = (probabilities - targets) / batch_size_current
            grad_w2 = hidden.T @ grad_logits
            grad_b2 = np.sum(grad_logits, axis=0, keepdims=True)

            grad_hidden = grad_logits @ w2.T
            grad_hidden[hidden <= 0.0] = 0.0
            grad_w1 = batch_features.T @ grad_hidden
            grad_b1 = np.sum(grad_hidden, axis=0, keepdims=True)

            w2 -= learning_rate * grad_w2
            b2 -= learning_rate * grad_b2
            w1 -= learning_rate * grad_w1
            b1 -= learning_rate * grad_b1

        _, train_probabilities = _forward(train_features, w1, b1, w2, b2)
        _, val_probabilities = _forward(val_features, w1, b1, w2, b2)
        train_loss, train_accuracy = _loss_and_accuracy(train_probabilities, train_labels)
        val_loss, val_accuracy = _loss_and_accuracy(val_probabilities, val_labels)

        history["loss"].append(train_loss)
        history["accuracy"].append(train_accuracy)
        history["val_loss"].append(val_loss)
        history["val_accuracy"].append(val_accuracy)

    _, test_probabilities = _forward(test_features, w1, b1, w2, b2)
    test_loss, test_accuracy = _loss_and_accuracy(test_probabilities, test_labels)
    predicted_labels = np.argmax(test_probabilities, axis=1)
    confusion_matrix = np.zeros((class_count, class_count), dtype=np.int32)
    for actual, predicted in zip(test_labels, predicted_labels, strict=False):
        confusion_matrix[actual, predicted] += 1

    np.savez_compressed(
        FER_MODEL_PATH,
        w1=w1,
        b1=b1,
        w2=w2,
        b2=b2,
        class_names=np.array(class_names),
    )
    FER_HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")
    _write_confusion_matrix(confusion_matrix, class_names)

    metadata = {
        "model_name": "fer2013-mlp",
        "dataset_name": "FER2013",
        "dataset_path": str(dataset_root),
        "train_samples": int(train_features.shape[0]),
        "validation_samples": int(val_features.shape[0]),
        "test_samples": int(test_features.shape[0]),
        "image_size": "48x48",
        "epochs": epochs,
        "batch_size": batch_size,
        "train_accuracy": float(history["accuracy"][-1] if history["accuracy"] else 0.0),
        "val_accuracy": float(history["val_accuracy"][-1] if history["val_accuracy"] else 0.0),
        "test_accuracy": float(test_accuracy),
        "test_loss": float(test_loss),
        "label_map": {index: label for index, label in enumerate(class_names)},
        "model_path": str(FER_MODEL_PATH),
        "history_path": str(FER_HISTORY_PATH),
        "confusion_matrix_path": str(FER_CONFUSION_MATRIX_PATH),
        "notes": "NumPy MLP trained from FER2013 train/test folders.",
    }
    run_id = record_training_run(metadata)
    metadata["run_id"] = run_id
    _MODEL_CACHE["path"] = str(FER_MODEL_PATH)
    _MODEL_CACHE["weights"] = {
        "w1": w1,
        "b1": b1,
        "w2": w2,
        "b2": b2,
        "class_names": class_names,
    }
    return metadata


def _load_weights() -> dict[str, object] | None:
    if not FER_MODEL_PATH.exists():
        return None
    if _MODEL_CACHE.get("path") == str(FER_MODEL_PATH) and _MODEL_CACHE.get("weights") is not None:
        return _MODEL_CACHE["weights"]  # type: ignore[return-value]

    payload = np.load(FER_MODEL_PATH, allow_pickle=True)
    weights = {
        "w1": payload["w1"],
        "b1": payload["b1"],
        "w2": payload["w2"],
        "b2": payload["b2"],
        "class_names": payload["class_names"].tolist(),
    }
    _MODEL_CACHE["path"] = str(FER_MODEL_PATH)
    _MODEL_CACHE["weights"] = weights
    return weights


def _prepare_face(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    faces = cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)
    if len(faces) > 0:
        x, y, width, height = max(faces, key=lambda face: face[2] * face[3])
        gray = gray[y : y + height, x : x + width]
    resized = cv2.resize(gray, IMAGE_SIZE)
    normalized = resized.astype(np.float32).reshape(1, -1) / 255.0
    return normalized


def _extract_face_roi(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    faces = cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)
    if len(faces) == 0:
        return gray
    x, y, width, height = max(faces, key=lambda face: face[2] * face[3])
    return gray[y : y + height, x : x + width]


def _face_variant_to_vector(gray_face: np.ndarray) -> np.ndarray:
    resized = cv2.resize(gray_face, IMAGE_SIZE)
    normalized = resized.astype(np.float32).reshape(1, -1) / 255.0
    return normalized


def _prepare_face_variants(frame: np.ndarray) -> list[np.ndarray]:
    face = _extract_face_roi(frame)
    if face.size == 0:
        return [_prepare_face(frame)]

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    face_eq = clahe.apply(face)
    h, w = face_eq.shape[:2]

    variants: list[np.ndarray] = []
    variants.append(_face_variant_to_vector(face_eq))

    # Center crop variant.
    cy0, cy1 = int(h * 0.1), int(h * 0.9)
    cx0, cx1 = int(w * 0.1), int(w * 0.9)
    center = face_eq[cy0:cy1, cx0:cx1]
    if center.size > 0:
        variants.append(_face_variant_to_vector(center))

    # Fine-grained upper and lower region variants.
    upper = face_eq[0 : max(1, int(h * 0.65)), :]
    lower = face_eq[max(0, int(h * 0.35)) : h, :]
    if upper.size > 0:
        variants.append(_face_variant_to_vector(upper))
    if lower.size > 0:
        variants.append(_face_variant_to_vector(lower))

    return variants


def predict_emotion_from_data_url(data_url: str) -> tuple[str, float, str] | None:
    if not data_url or "," not in data_url:
        return None

    weights = _load_weights()
    if weights is None:
        return None

    try:
        encoded = data_url.split(",", 1)[1]
        image_bytes = base64.b64decode(encoded)
    except Exception:
        return None

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if frame is None:
        return None

    feature_variants = _prepare_face_variants(frame)
    prob_vectors: list[np.ndarray] = []
    for features in feature_variants:
        hidden, probabilities = _forward(
            features,
            weights["w1"],  # type: ignore[arg-type]
            weights["b1"],  # type: ignore[arg-type]
            weights["w2"],  # type: ignore[arg-type]
            weights["b2"],  # type: ignore[arg-type]
        )
        _ = hidden
        prob_vectors.append(probabilities[0])
    probability_vector = np.mean(np.stack(prob_vectors), axis=0)
    label_index = int(np.argmax(probability_vector))
    class_names = weights["class_names"]  # type: ignore[assignment]
    label = class_names[label_index]
    confidence = float(probability_vector[label_index] * 100.0)
    return label, confidence, "fer2013-mlp-multiscale"
