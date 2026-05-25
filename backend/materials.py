import re


MATERIAL_INVENTORY = [
    # Plastic / containers
    {"label": "Plastic water bottle", "category": "Plastic"},
    {"label": "Soda bottle", "category": "Plastic"},
    {"label": "Milk jug", "category": "Plastic"},
    {"label": "Detergent bottle", "category": "Plastic"},
    {"label": "Shampoo bottle", "category": "Plastic"},
    {"label": "Plastic cup", "category": "Plastic"},
    {"label": "Yogurt container", "category": "Plastic"},
    {"label": "Food takeout container", "category": "Plastic"},
    {"label": "Plastic bag", "category": "Plastic"},
    {"label": "Chip bag", "category": "Mixed Material"},
    {"label": "Candy wrapper", "category": "Mixed Material"},
    {"label": "Toothpaste tube", "category": "Mixed Material"},
    {"label": "Plastic bucket", "category": "Hard Plastic"},
    {"label": "Bottle cap", "category": "Hard Plastic"},
    # Paper / cardboard
    {"label": "Cardboard box", "category": "Cardboard"},
    {"label": "Pizza box", "category": "Cardboard"},
    {"label": "Newspaper", "category": "Paper"},
    {"label": "Magazine", "category": "Paper"},
    {"label": "Notebook paper", "category": "Paper"},
    {"label": "Envelope", "category": "Paper"},
    {"label": "Paper cup", "category": "Mixed Material"},
    {"label": "Drink carton", "category": "Mixed Material"},
    {"label": "Book", "category": "Paper"},
    {"label": "Paper bag", "category": "Paper"},
    # Metal
    {"label": "Soda can", "category": "Metal"},
    {"label": "Food can", "category": "Metal"},
    {"label": "Aluminum foil", "category": "Metal"},
    {"label": "Metal lid", "category": "Metal"},
    {"label": "Aerosol can", "category": "Hazardous"},
    {"label": "Paint can", "category": "Hazardous"},
    # Glass
    {"label": "Glass bottle", "category": "Glass"},
    {"label": "Glass jar", "category": "Glass"},
    {"label": "Beverage bottle", "category": "Glass"},
    # Food / compost
    {"label": "Banana peel", "category": "Organic"},
    {"label": "Apple core", "category": "Organic"},
    {"label": "Orange peel", "category": "Organic"},
    {"label": "Eggshell", "category": "Organic"},
    {"label": "Coffee grounds", "category": "Organic"},
    {"label": "Leftover food", "category": "Organic"},
    {"label": "Bread", "category": "Organic"},
    {"label": "Fruit scraps", "category": "Organic"},
    {"label": "Vegetable scraps", "category": "Organic"},
    # Electronics / batteries / appliances
    {"label": "Smartphone", "category": "Electronics"},
    {"label": "Tablet", "category": "Electronics"},
    {"label": "Laptop", "category": "Electronics"},
    {"label": "Keyboard", "category": "Electronics"},
    {"label": "Mouse", "category": "Electronics"},
    {"label": "Headphones", "category": "Electronics"},
    {"label": "Charger", "category": "Electronics"},
    {"label": "Cable", "category": "Electronics"},
    {"label": "Calculator", "category": "Electronics"},
    {"label": "Remote control", "category": "Electronics"},
    {"label": "TV remote", "category": "Electronics"},
    {"label": "Battery", "category": "Battery"},
    {"label": "Vape pen", "category": "Battery"},
    {"label": "Printer", "category": "Electronics"},
    {"label": "Microwave", "category": "Appliances"},
    {"label": "Toaster", "category": "Appliances"},
    {"label": "Vacuum", "category": "Appliances"},
    # Clothing / household
    {"label": "Shoes", "category": "Textile"},
    {"label": "T-shirt", "category": "Textile"},
    {"label": "Jeans", "category": "Textile"},
    {"label": "Backpack", "category": "Textile"},
    {"label": "Toy", "category": "Hard Plastic"},
    {"label": "Toothbrush", "category": "Mixed Material"},
    {"label": "Hanger", "category": "Hard Plastic"},
    {"label": "Pillow", "category": "Textile"},
    {"label": "Mattress", "category": "Appliances"},
    {"label": "Furniture", "category": "Appliances"},
    # Hazardous items
    {"label": "Light bulb", "category": "Hazardous"},
    {"label": "Motor oil", "category": "Hazardous"},
    {"label": "Cleaning spray bottle", "category": "Hazardous"},
    {"label": "Propane tank", "category": "Hazardous"},
    {"label": "Hand sanitizer", "category": "Hazardous"},
    {"label": "Medication bottle", "category": "Hazardous"},
    # Outdoor / yard
    {"label": "Leaves", "category": "Organic"},
    {"label": "Branches", "category": "Organic"},
    {"label": "Grass clippings", "category": "Organic"},
    {"label": "Wood pieces", "category": "Organic"},
]


MATERIAL_LABELS = [entry["label"] for entry in MATERIAL_INVENTORY]
LABEL_TO_CATEGORY = {entry["label"]: entry["category"] for entry in MATERIAL_INVENTORY}

_ALIAS_MAP = {
    "aerosol spray can": "Aerosol can",
    "aa battery": "Battery",
    "aluminum can": "Soda can",
    "apple cores": "Apple core",
    "back pack": "Backpack",
    "banana peels": "Banana peel",
    "beverage bottles": "Beverage bottle",
    "bottle caps": "Bottle cap",
    "branch": "Branches",
    "branches from tree": "Branches",
    "bread loaf": "Bread",
    "cable charger": "Charger",
    "calculator device": "Calculator",
    "candy wrappers": "Candy wrapper",
    "cap": "Bottle cap",
    "cell phone": "Smartphone",
    "cellphone": "Smartphone",
    "charging cable": "Cable",
    "charging cord": "Cable",
    "chip packet": "Chip bag",
    "chip wrapper": "Chip bag",
    "coffee grounds pile": "Coffee grounds",
    "coffee ground pile": "Coffee grounds",
    "computer mouse": "Mouse",
    "detergent jug": "Detergent bottle",
    "drinks carton": "Drink carton",
    "ear buds": "Headphones",
    "earphones": "Headphones",
    "egg shell": "Eggshell",
    "eggshells": "Eggshell",
    "flip flops": "Shoes",
    "food tin": "Food can",
    "fruit": "Fruit scraps",
    "fruit flesh": "Fruit scraps",
    "fruit scrap": "Fruit scraps",
    "fruit waste": "Fruit scraps",
    "glass bottles": "Glass bottle",
    "glass jars": "Glass jar",
    "grass clipping": "Grass clippings",
    "headset": "Headphones",
    "jean": "Jeans",
    "keyboard device": "Keyboard",
    "leaf": "Leaves",
    "lightbulb": "Light bulb",
    "magazines": "Magazine",
    "medicine bottle": "Medication bottle",
    "metal can": "Food can",
    "milk bottle": "Milk jug",
    "mobile phone": "Smartphone",
    "motor oil bottle": "Motor oil",
    "notebook": "Notebook paper",
    "news paper": "Newspaper",
    "notebook book": "Notebook paper",
    "orange peels": "Orange peel",
    "paint bucket": "Paint can",
    "paper carton": "Drink carton",
    "paper cups": "Paper cup",
    "paper notebook": "Notebook paper",
    "pill bottle": "Medication bottle",
    "pizza boxes": "Pizza box",
    "plastic bottle": "Plastic water bottle",
    "plastic bottles": "Plastic water bottle",
    "plastic bottles water": "Plastic water bottle",
    "plastic container": "Food takeout container",
    "plastic food container": "Food takeout container",
    "plastic shopping bag": "Plastic bag",
    "remote": "Remote control",
    "remote controller": "Remote control",
    "sanitizer bottle": "Hand sanitizer",
    "shoe": "Shoes",
    "sneaker": "Shoes",
    "sneakers": "Shoes",
    "smart phone": "Smartphone",
    "smartphones": "Smartphone",
    "soft drink bottle": "Soda bottle",
    "spray bottle": "Cleaning spray bottle",
    "spray can": "Aerosol can",
    "tablet computer": "Tablet",
    "take out container": "Food takeout container",
    "takeout box": "Food takeout container",
    "tee shirt": "T-shirt",
    "television remote": "TV remote",
    "tin can": "Food can",
    "tooth paste tube": "Toothpaste tube",
    "tv controller": "TV remote",
    "usb cable": "Cable",
    "vacuum cleaner": "Vacuum",
    "vegetable scrap": "Vegetable scraps",
    "vegetable waste": "Vegetable scraps",
    "water bottle": "Plastic water bottle",
    "water melon": "Fruit scraps",
    "watermelon": "Fruit scraps",
    "watermelon rind": "Fruit scraps",
    "wood piece": "Wood pieces",
    "wood scraps": "Wood pieces",
    "yoghurt container": "Yogurt container",
}


def _normalize_key(label: str) -> str:
    normalized = label.strip().lower()
    normalized = normalized.replace("&", " and ")
    normalized = normalized.replace("/", " ")
    normalized = normalized.replace("_", " ")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\b(a|an|the)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


NORMALIZED_LABEL_TO_CANONICAL = {
    _normalize_key(label): label
    for label in MATERIAL_LABELS
}
NORMALIZED_LABEL_TO_CANONICAL.update(
    {
        _normalize_key(alias): canonical
        for alias, canonical in _ALIAS_MAP.items()
    }
)


def resolve_material_label(label: str) -> str | None:
    normalized = _normalize_key(label)
    if not normalized:
        return None

    direct_match = NORMALIZED_LABEL_TO_CANONICAL.get(normalized)
    if direct_match is not None:
        return direct_match

    best_match = None
    best_length = -1
    for candidate_key, canonical_label in NORMALIZED_LABEL_TO_CANONICAL.items():
        if candidate_key and candidate_key in normalized and len(candidate_key) > best_length:
            best_match = canonical_label
            best_length = len(candidate_key)

    if best_match is not None:
        return best_match

    normalized_terms = set(normalized.split())
    best_overlap_match = None
    best_overlap_score = 0.0

    for candidate_key, canonical_label in NORMALIZED_LABEL_TO_CANONICAL.items():
        candidate_terms = set(candidate_key.split())
        if not candidate_terms:
            continue

        overlap = normalized_terms & candidate_terms
        if not overlap:
            continue

        overlap_score = len(overlap) / len(candidate_terms)
        if overlap_score > best_overlap_score or (
            overlap_score == best_overlap_score and len(candidate_key) > best_length
        ):
            best_overlap_match = canonical_label
            best_overlap_score = overlap_score
            best_length = len(candidate_key)

    if best_overlap_score >= 0.6:
        return best_overlap_match

    return None


def build_material_selection_prompt() -> str:
    inventory_lines = "\n".join(f"- {label}" for label in MATERIAL_LABELS)
    return (
        "You are classifying waste-related items from an image.\n"
        "Choose labels only from the allowed inventory below.\n"
        "If the exact object is not listed, generalize to the nearest appropriate inventory label.\n"
        "Examples: watermelon -> Fruit scraps, sneakers -> Shoes, plastic bottle on table -> Plastic water bottle.\n"
        "If two or more distinct visible objects could each map to supported inventory labels, you must return status uncertain.\n"
        "When multiple objects are visible, candidate_labels should name those visible objects or their nearest supported inventory labels.\n"
        "Do not collapse multiple visible objects into one generalized label.\n"
        "Only return status confident when exactly one relevant object is clearly the subject and no other plausible supported object competes with it.\n"
        "If the image is ambiguous or contains multiple plausible items, return the top 3 best inventory labels in ranked order.\n"
        "Return strict JSON only using this exact shape:\n"
        '{"status":"confident|uncertain","primary_label":"<inventory label>","candidate_labels":["<inventory label 1>","<inventory label 2>","<inventory label 3>"]}\n'
        "Use only inventory labels in the JSON. Do not include explanations or markdown.\n"
        "Allowed inventory labels:\n"
        f"{inventory_lines}"
    )


def build_uncertain_fallback_prompt(primary_label: str) -> str:
    inventory_lines = "\n".join(f"- {label}" for label in MATERIAL_LABELS)
    return (
        "Your previous result was uncertain and did not include enough valid candidate labels.\n"
        f"The first-pass primary guess was: {primary_label or 'unknown'}.\n"
        "Return strict JSON only with exactly 3 ranked inventory labels.\n"
        'Use this exact shape: {"status":"uncertain","primary_label":"<inventory label>","candidate_labels":["<inventory label 1>","<inventory label 2>","<inventory label 3>"]}\n'
        "Choose labels only from the allowed inventory below.\n"
        "Keep the alternatives close to the first-pass guess when possible, and do not output scene objects, furniture parts, colors, or descriptions that are not inventory labels.\n"
        "Do not include explanations or markdown.\n"
        "Allowed inventory labels:\n"
        f"{inventory_lines}"
    )


def build_multi_object_verification_prompt(primary_label: str) -> str:
    inventory_lines = "\n".join(f"- {label}" for label in MATERIAL_LABELS)
    return (
        "Verify whether this image should stay confident or become uncertain.\n"
        f"The first-pass primary guess was: {primary_label or 'unknown'}.\n"
        "If two or more distinct visible objects in the image could each map to supported inventory labels, you must return status uncertain.\n"
        "If only one relevant supported object is clearly the subject, return status confident.\n"
        'The status field must be exactly one of these strings: "confident" or "uncertain".\n'
        "Return strict JSON only using this exact shape:\n"
        '{"status":"uncertain","primary_label":"<inventory label>","candidate_labels":["<inventory label 1>","<inventory label 2>","<inventory label 3>"]}\n'
        "or this exact shape:\n"
        '{"status":"confident","primary_label":"<inventory label>","candidate_labels":["<inventory label 1>","<inventory label 2>","<inventory label 3>"]}\n'
        "For uncertain, candidate_labels must contain exactly 3 ranked inventory labels describing the visible supported objects or their nearest supported inventory labels.\n"
        "For confident, candidate_labels may repeat the primary label or include nearby alternatives from the inventory.\n"
        "Use only inventory labels from this list. Do not include explanations or markdown.\n"
        "Allowed inventory labels:\n"
        f"{inventory_lines}"
    )
