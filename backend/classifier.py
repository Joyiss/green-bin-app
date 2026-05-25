from .materials import LABEL_TO_CATEGORY, resolve_material_label
from .model import CONFIDENT_THRESHOLD, MARGIN_THRESHOLD


UNKNOWN_CATEGORY = "Unknown"
UNCERTAIN_CANDIDATE_LIMIT = 3


def _normalize_label(label: str) -> str:
    canonical_label = resolve_material_label(label)
    if canonical_label is not None:
        return canonical_label

    return label.strip()


def get_category_for_label(label: str) -> str:
    normalized_label = _normalize_label(label)
    return LABEL_TO_CATEGORY.get(normalized_label, UNKNOWN_CATEGORY)


def build_selected_item_prediction(label: str) -> dict:
    normalized_label = _normalize_label(label)
    category = get_category_for_label(normalized_label)

    if category == UNKNOWN_CATEGORY:
        return {
            "item": "",
            "category": UNKNOWN_CATEGORY,
            "status": "unknown",
            "candidates": [],
        }

    return {
        "item": normalized_label,
        "category": category,
        "status": "confident",
        "candidates": [],
    }


def _unknown_prediction() -> dict:
    return {
        "item": "",
        "category": UNKNOWN_CATEGORY,
        "status": "unknown",
        "candidates": [],
    }


def classify(prediction_result: dict) -> dict:
    top_predictions = prediction_result.get("top_predictions", [])

    print("top labels:")
    for rank, (label, score) in enumerate(top_predictions, start=1):
        print(f"  {rank}. {label}: {score:.4f}")

    if not top_predictions:
        return _unknown_prediction()

    top1_label, top1_score = top_predictions[0]
    margin = float(prediction_result.get("margin", 0.0))
    top1_category = get_category_for_label(top1_label)

    if top1_category == UNKNOWN_CATEGORY or float(top1_score) < CONFIDENT_THRESHOLD:
        return _unknown_prediction()

    if margin < MARGIN_THRESHOLD:
        candidates = []
        seen_labels = set()

        for label, score in top_predictions:
            normalized_label = _normalize_label(label)
            if normalized_label in seen_labels:
                continue
            if get_category_for_label(normalized_label) == UNKNOWN_CATEGORY:
                continue

            seen_labels.add(normalized_label)
            candidates.append((normalized_label, float(score)))

            if len(candidates) == UNCERTAIN_CANDIDATE_LIMIT:
                break

        if len(candidates) < 2:
            return _unknown_prediction()

        return {
            "item": "",
            "category": UNKNOWN_CATEGORY,
            "status": "uncertain",
            "candidates": candidates,
        }

    return {
        "item": _normalize_label(top1_label),
        "category": top1_category,
        "status": "confident",
        "candidates": [],
    }
