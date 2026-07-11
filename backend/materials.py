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
    {"label": "Plastic film", "category": "Plastic"},
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
    {"label": "Monitor", "category": "Electronics"},
    {"label": "Television", "category": "Electronics"},
    {"label": "Computer tower", "category": "Electronics"},
    {"label": "Keyboard", "category": "Electronics"},
    {"label": "Mouse", "category": "Electronics"},
    {"label": "Headphones", "category": "Electronics"},
    {"label": "Earbuds", "category": "Electronics"},
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
    {"label": "Refrigerator", "category": "Appliances"},

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
    {"label": "Sofa", "category": "Appliances"},

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
    {"label": "Garden hose", "category": "Hard Plastic"},
    {"label": "String lights", "category": "Electronics"},
    {"label": "Tire", "category": "Hard Plastic"},
]


MATERIAL_LABELS = [entry["label"] for entry in MATERIAL_INVENTORY]
LABEL_TO_CATEGORY = {entry["label"]: entry["category"] for entry in MATERIAL_INVENTORY}

GENERIC_UNSAFE_TERMS = {
    "paper",
    "plastic",
    "glass",
    "metal",
    "organic",
    "electronics",
    "clothing",
    "textile",
    "container",
    "bottle",
    "bag",
    "food",
}

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
    "composition book": "Book",
    "computer mouse": "Mouse",
    "computer monitor": "Monitor",
    "display monitor": "Monitor",
    "pc monitor": "Monitor",
    "screen": "Monitor",
    "tv": "Television",
    "television set": "Television",
    "flat screen tv": "Television",
    "smart tv": "Television",
    "desktop tower": "Computer tower",
    "pc tower": "Computer tower",
    "computer tower case": "Computer tower",
    "desktop tower computer": "Computer tower",
    "detergent jug": "Detergent bottle",
    "drinking bottle": "Plastic water bottle",
    "drinks carton": "Drink carton",
    "ear buds": "Earbuds",
    "earbud": "Earbuds",
    "wireless earbuds": "Earbuds",
    "bluetooth earbuds": "Earbuds",
    "earphones": "Headphones",
    "egg shell": "Eggshell",
    "eggshells": "Eggshell",
    "flip flops": "Shoes",
    "food tin": "Food can",
    "fruit scrap": "Fruit scraps",
    "fruit waste": "Fruit scraps",
    "glass bottles": "Glass bottle",
    "glass jars": "Glass jar",
    "grass clipping": "Grass clippings",
    "garden hose pipe": "Garden hose",
    "water hose": "Garden hose",
    "hose pipe": "Garden hose",
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
    "news paper": "Newspaper",
    "notebook": "Book",
    "orange peels": "Orange peel",
    "paint bucket": "Paint can",
    "paper carton": "Drink carton",
    "paper cups": "Paper cup",
    "paper notebook": "Book",
    "pill bottle": "Medication bottle",
    "pizza boxes": "Pizza box",
    "plastic shopping bag": "Plastic bag",
    "plastic wrap": "Plastic film",
    "cling wrap": "Plastic film",
    "cling film": "Plastic film",
    "saran wrap": "Plastic film",
    "shrink wrap": "Plastic film",
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
    "string light": "String lights",
    "fairy lights": "String lights",
    "christmas lights": "String lights",
    "holiday lights": "String lights",
    "tablet computer": "Tablet",
    "take out container": "Food takeout container",
    "takeout box": "Food takeout container",
    "tee shirt": "T-shirt",
    "television remote": "TV remote",
    "tin can": "Food can",
    "tooth paste tube": "Toothpaste tube",
    "tv controller": "TV remote",
    "tv screen": "Television",
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
    "fridge": "Refrigerator",
    "mini fridge": "Refrigerator",
    "refrigerator fridge": "Refrigerator",
    "sofa couch": "Sofa",
    "couch": "Sofa",
    "loveseat": "Sofa",
    "car tire": "Tire",
    "vehicle tire": "Tire",
    "rubber tire": "Tire",
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

    if normalized in GENERIC_UNSAFE_TERMS:
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

    if best_match is not None and best_length >= len(normalized) * 0.75:
        return best_match

    normalized_terms = set(normalized.split())
    best_overlap_match = None
    best_overlap_score = 0.0
    best_overlap_length = -1

    for candidate_key, canonical_label in NORMALIZED_LABEL_TO_CANONICAL.items():
        candidate_terms = set(candidate_key.split())
        if not candidate_terms:
            continue

        overlap = normalized_terms & candidate_terms
        if not overlap:
            continue

        overlap_score = len(overlap) / len(candidate_terms)
        if overlap_score > best_overlap_score or (
            overlap_score == best_overlap_score and len(candidate_key) > best_overlap_length
        ):
            best_overlap_match = canonical_label
            best_overlap_score = overlap_score
            best_overlap_length = len(candidate_key)

    if best_overlap_score >= 0.75:
        return best_overlap_match

    return None


def build_material_selection_prompt() -> str:
    inventory_lines = "\n".join(f"- {label}" for label in MATERIAL_LABELS)
    return (
        "You are an image classifier for a disposal app.\n"
        "Return exactly one JSON object and nothing else.\n"
        "Do not include any explanation, description, markdown, or extra text.\n"
        "Do not output more than one JSON object.\n"
        "\n"
        "Classify the single main item the user is most likely focusing on.\n"
        "Ignore background objects unless they are equally prominent and equally likely to be the intended item.\n"
        "Do not mark the result uncertain just because other background objects are visible.\n"
        "Identify the actual physical object the user would dispose of, not only the product, brand, logo, printed text, or contents shown on it.\n"
        "Use visible packaging form and material when choosing a label: bottle, jar, can, carton, box, bag, wrapper, tube, cup, lid, container, cable, device, or loose contents.\n"
        "Consider whether the item appears opened, used, empty, food-soiled, wet, broken, reusable, or single-use when deciding the closest disposal label.\n"
        "If a food or household product is visible inside packaging, classify the package or container unless the loose contents are clearly the disposal item.\n"
        "Examples: chips in a crinkly pouch -> Chip bag; yogurt in a plastic tub -> Yogurt container; greasy pizza delivery box -> Pizza box; empty beverage can -> Soda can.\n"
        "\n"
        "Use only labels from the allowed inventory below.\n"
        "If the exact object is not listed, map it to the nearest allowed inventory label.\n"
        "If no allowed inventory label is a reasonable match, return unknown with an empty primary_label and an empty candidate_labels list.\n"
        "\n"
        "Rules:\n"
        '- status must be exactly one of: "confident", "uncertain", "unknown"\n'
        "- Return confident when one main supported item is clearly the subject.\n"
        "- Return uncertain only when two or more supported inventory labels are genuinely plausible for the same main item.\n"
        "- Return unknown when no supported inventory label is a good match.\n"
        "- candidate_labels must contain 0 to 3 labels only.\n"
        "- Never include more than 3 candidate labels.\n"
        "- candidate_labels must contain only allowed inventory labels.\n"
        "- When status is confident, candidate_labels should contain only close alternatives, not random inventory items.\n"
        "- When status is unknown, primary_label must be \"\" and candidate_labels must be [].\n"
        "\n"
        "Return JSON in exactly this shape:\n"
        '{"status":"confident","primary_label":"<inventory label>","candidate_labels":["<inventory label>","<inventory label>","<inventory label>"]}\n'
        "\n"
        "Allowed inventory labels:\n"
        f"{inventory_lines}"
    )


def build_uncertain_fallback_prompt(primary_label: str) -> str:
    inventory_lines = "\n".join(f"- {label}" for label in MATERIAL_LABELS)
    return (
        "Your previous result was uncertain or incomplete.\n"
        "Return exactly one JSON object and nothing else.\n"
        "Do not include any explanation, description, markdown, or extra text.\n"
        "Do not output more than one JSON object.\n"
        f'The previous primary guess was: "{primary_label or "unknown"}".\n'
        "\n"
        "Choose the 2 or 3 closest allowed inventory labels for the same main item.\n"
        "Do not include unrelated background objects.\n"
        "Do not include random labels from the inventory.\n"
        "\n"
        "Rules:\n"
        '- status must be exactly "uncertain"\n'
        "- primary_label must be the best single allowed inventory label, or \"\" if no good match exists.\n"
        "- candidate_labels must contain 2 to 3 allowed inventory labels only.\n"
        "- candidate_labels must be ranked from best to worst.\n"
        "- Never include more than 3 candidate labels.\n"
        "\n"
        "Return JSON in exactly this shape:\n"
        '{"status":"uncertain","primary_label":"<inventory label>","candidate_labels":["<inventory label>","<inventory label>","<inventory label>"]}\n'
        "\n"
        "Allowed inventory labels:\n"
        f"{inventory_lines}"
    )


def build_multi_object_verification_prompt(primary_label: str) -> str:
    inventory_lines = "\n".join(f"- {label}" for label in MATERIAL_LABELS)
    return (
        "Re-evaluate the same main item from the image.\n"
        "Return exactly one JSON object and nothing else.\n"
        "Do not include any explanation, description, markdown, or extra text.\n"
        "Do not output more than one JSON object.\n"
        f'The first-pass primary guess was: "{primary_label or "unknown"}".\n'
        "\n"
        "Focus only on the single main item.\n"
        "Ignore background objects unless they make the main item genuinely ambiguous.\n"
        "Do not mark the result uncertain just because a bed, table, wall, floor, or other background object is visible.\n"
        "\n"
        "Rules:\n"
        '- status must be exactly one of: "confident", "uncertain", "unknown"\n'
        "- Return confident when the first-pass label still looks like the best supported label.\n"
        "- Return uncertain only when 2 or 3 supported labels are genuinely plausible for the same main item.\n"
        "- Return unknown when no supported label is a good match.\n"
        "- candidate_labels must contain 0 to 3 allowed inventory labels only.\n"
        "- Never include more than 3 candidate labels.\n"
        "\n"
        "Return JSON in exactly this shape:\n"
        '{"status":"confident","primary_label":"<inventory label>","candidate_labels":["<inventory label>","<inventory label>","<inventory label>"]}\n'
        "\n"
        "Allowed inventory labels:\n"
        f"{inventory_lines}"
    )
