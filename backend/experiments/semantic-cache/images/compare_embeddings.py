from itertools import combinations
from pathlib import Path

import open_clip
import torch
from PIL import Image


IMAGES_FOLDER = Path(__file__).parent / "images"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_images():
    images = []

    for category_folder in IMAGES_FOLDER.iterdir():
        if not category_folder.is_dir():
            continue

        for image_path in category_folder.iterdir():
            if image_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                images.append(
                    {
                        "path": image_path,
                        "category": category_folder.name,
                    }
                )

    return images


def create_embeddings(images, model, preprocess, device):
    for image_data in images:
        image = Image.open(image_data["path"]).convert("RGB")
        image_tensor = preprocess(image).unsqueeze(0).to(device)

        with torch.no_grad():
            embedding = model.encode_image(image_tensor)

        # Normalize so the dot product becomes cosine similarity.
        embedding = embedding / embedding.norm(dim=-1, keepdim=True)

        image_data["embedding"] = embedding.squeeze(0).cpu()

    return images


def compare_images(images):
    grouped_results = {}

    for first, second in combinations(images, 2):
        similarity = torch.dot(
            first["embedding"],
            second["embedding"],
        ).item()

        categories = sorted([first["category"], second["category"]])
        group_name = f"{categories[0]} to {categories[1]}"

        result = {
            "first_image": first["path"].name,
            "second_image": second["path"].name,
            "similarity": similarity,
        }

        grouped_results.setdefault(group_name, []).append(result)

    return grouped_results


def print_results(grouped_results):
    for group_name, results in sorted(grouped_results.items()):
        print("\n" + "=" * 65)
        print(group_name.upper())
        print("=" * 65)

        results.sort(key=lambda result: result["similarity"], reverse=True)

        for result in results:
            print(
                f"{result['first_image']} ↔ "
                f"{result['second_image']}: "
                f"{result['similarity']:.4f}"
            )

        scores = [result["similarity"] for result in results]

        print("\nSummary")
        print(f"Minimum: {min(scores):.4f}")
        print(f"Maximum: {max(scores):.4f}")
        print(f"Average: {sum(scores) / len(scores):.4f}")


def main():
    if not IMAGES_FOLDER.exists():
        print(f"Images folder not found: {IMAGES_FOLDER}")
        return

    images = load_images()

    if len(images) < 2:
        print("Add at least two images before running the test.")
        return

    device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"Using device: {device}")
    print(f"Found {len(images)} images")

    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32",
        pretrained="laion2b_s34b_b79k",
    )

    model = model.to(device)
    model.eval()

    images = create_embeddings(
        images=images,
        model=model,
        preprocess=preprocess,
        device=device,
    )

    results = compare_images(images)
    print_results(results)


if __name__ == "__main__":
    main()