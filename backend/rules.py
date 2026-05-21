RULES = {
    "Plastic": {
        "disposal_action": "recycle",
        "impact_level": "High Impact",
        "material_code": "PETE 1",
        "steps": [
            "Check the recycling number before placing it out.",
            "Rinse away any residue.",
            "Place it in your curbside recycling bin.",
        ],
    },
    "Glass": {
        "disposal_action": "recycle",
        "impact_level": "High Impact",
        "material_code": None,
        "steps": [
            "Rinse the container thoroughly.",
            "Remove metal lids and recycle them separately.",
            "Place the glass in your local glass bin.",
        ],
    },
    "Metal": {
        "disposal_action": "recycle",
        "impact_level": "High Impact",
        "material_code": None,
        "steps": [
            "Rinse out cans before disposal.",
            "Do not crush the container.",
            "Place it in your curbside recycling bin.",
        ],
    },
    "Cardboard": {
        "disposal_action": "recycle",
        "impact_level": "Medium Impact",
        "material_code": None,
        "steps": [
            "Flatten boxes to save space.",
            "Remove tape and any styrofoam inserts.",
            "Keep the cardboard dry before recycling.",
        ],
    },
    "Paper": {
        "disposal_action": "recycle",
        "impact_level": "Medium Impact",
        "material_code": None,
        "steps": [
            "Keep paper dry and free of food residue.",
            "Remove plastic envelope windows if possible.",
            "Bundle it loosely for recycling collection.",
        ],
    },
    "Organic": {
        "disposal_action": "compost",
        "impact_level": "High Impact",
        "material_code": None,
        "steps": [
            "Place the item in your compost caddy.",
            "Avoid adding meat or dairy to home compost piles.",
            "Check local food waste collection rules in your area.",
        ],
    },
    "Battery": {
        "disposal_action": "hazardous drop-off",
        "impact_level": "High Impact",
        "material_code": None,
        "steps": [
            "Never place batteries in the bin because they can start fires.",
            "Take them to a supermarket or battery recycling drop-off point.",
            "Tape lithium battery terminals before transport.",
        ],
    },
    "Electronics": {
        "disposal_action": "e-waste recycling",
        "impact_level": "High Impact",
        "material_code": None,
        "steps": [
            "Do not place electronics in household trash.",
            "Wipe any personal data before disposal.",
            "Take the item to an e-waste center or retailer drop-off.",
        ],
    },
    "Hazardous": {
        "disposal_action": "hazardous drop-off",
        "impact_level": "High Impact",
        "material_code": None,
        "steps": [
            "Never pour it down the drain or place it in the bin.",
            "Store it safely until the collection day.",
            "Check your council website for hazardous waste events.",
        ],
    },
    "Textile": {
        "disposal_action": "donate or textile bank",
        "impact_level": "Medium Impact",
        "material_code": None,
        "steps": [
            "Donate the item if it is still wearable.",
            "Use a textile bank if it is too worn out to donate.",
            "Do not place textiles in your general recycling bin.",
        ],
    },
    "Appliances": {
        "disposal_action": "bulky waste collection or drop-off",
        "impact_level": "High Impact",
        "material_code": None,
        "steps": [
            "Do not place large appliances on the curb without a scheduled pickup.",
            "Check if local retailers offer old appliance take-back programs upon delivery.",
            "Ensure refrigerators are properly drained of coolants by certified centers.",
        ],
    },
    "Hard Plastic": {
        "disposal_action": "specialist recycling or donation",
        "impact_level": "Medium Impact",
        "material_code": None,
        "steps": [
            "Do not put rigid, non-bottle plastics in your curbside recycling bin.",
            "Donate toys and durable items to charity if they are still in good, usable condition.",
            "Take broken items to a dedicated hard-plastic recycling skip at your local waste center.",
        ],
    },
    "Mixed Material": {
        "disposal_action": "landfill bin",
        "impact_level": "Low Impact",
        "material_code": None,
        "steps": [
            "Place items made of fused plastic, metal, and rubber directly into the general waste bin.",
            "Try to separate clean cardboard or paper backings from plastic packaging where possible.",
            "Look for specialized mail-in or retail drop-off boxes (like TerraCycle) for oral care or wrapper waste.",
        ],
    },
}

def get_rules(category: str) -> dict:
    return RULES.get(
        category,
        {
            "disposal_action": "general waste",
            "impact_level": "Low Impact",
            "material_code": None,
            "steps": ["Place in your general waste bin."],
        },
    )
