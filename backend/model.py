import open_clip
import torch
from PIL import Image

CONFIDENT_THRESHOLD = 0.20
MARGIN_THRESHOLD = 0.05


BASE_ITEMS = [
    # Plastic / Containers
    "plastic bottle",
    "plastic bag",
    "plastic food container",
    "milk jug",
    "shampoo bottle",

    # Paper / Cardboard
    "cardboard box",
    "egg carton",
    "pizza box",
    "newspaper",
    "magazine",
    "paper cup",
    "cereal box",

    # Glass
    "glass bottle",
    "glass jar",

    # Metal
    "aluminum can",

    # Food waste / Compost
    "banana peel",
    "apple core",
    "pile of coffee grounds",

    # Electronics
    "smartphone",
    "laptop",
    "desktop computer tower",
    "printer",
    "pair of earbuds",
    "smartwatch",
    "remote control",
    "calculator",

    # Batteries
    "AA battery",
    "lithium phone battery",

    # Household items
    "light bulb",
    "toothbrush",
    "pair of shoes",
    "pair of flip flops",
    "bicycle",
    "book",
    "toy",

    # Appliances
    "microwave oven",
    "refrigerator",
    "washer and dryer",

    # Hazardous / Chemicals
    "paint can",
    "cleaning spray bottle",
    "motor oil container",

    # Clothing
    "t-shirt",
    "pair of jeans",
]

ENSEMBLE_PROMPTS = {
    item: [
        f"a photo of a {item}.",
        f"a photo of a {item}, a type of waste item.",
    ]
    for item in BASE_ITEMS
}

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODEL = None
PREPROCESS = None
ENSEMBLE_TEXT_FEATURES = None  # averaged embeddings per item


def _get_model_resources():
    global MODEL, PREPROCESS, ENSEMBLE_TEXT_FEATURES

    if MODEL is None or PREPROCESS is None or ENSEMBLE_TEXT_FEATURES is None:
        MODEL, _, PREPROCESS = open_clip.create_model_and_transforms(
            "ViT-B-32",
            pretrained="laion2b_s34b_b79k",
            device=DEVICE,
        )

        # build one averaged embedding per item
        ensemble_embeddings = []
        for item in BASE_ITEMS:
            prompts = ENSEMBLE_PROMPTS[item]
            tokenized = open_clip.get_tokenizer("ViT-B-32")(prompts).to(DEVICE)
            with torch.no_grad():
                embeddings = MODEL.encode_text(tokenized)
                embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
                averaged = embeddings.mean(dim=0)
                averaged = averaged / averaged.norm()
            ensemble_embeddings.append(averaged)

        ENSEMBLE_TEXT_FEATURES = torch.stack(ensemble_embeddings)  # shape: [n_items, embed_dim]

    return MODEL, PREPROCESS, ENSEMBLE_TEXT_FEATURES


def get_top_predictions(image: Image.Image) -> dict[str, object]:
    model, preprocess, text_features = _get_model_resources()
    image_input = preprocess(image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        image_features = model.encode_image(image_input)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        similarities = (image_features @ text_features.T).squeeze(0)
        top_scores, top_indices = similarities.topk(5)

    top_predictions = [
        (BASE_ITEMS[index], float(score))
        for score, index in zip(top_scores.tolist(), top_indices.tolist())
    ]

    top1_score = top_predictions[0][1] if top_predictions else 0.0
    top2_score = top_predictions[1][1] if len(top_predictions) > 1 else 0.0

    return {
        "top_predictions": top_predictions,
        "scores": similarities.tolist(),
        "top1_score": top1_score,
        "top2_score": top2_score,
        "margin": top1_score - top2_score,
    }