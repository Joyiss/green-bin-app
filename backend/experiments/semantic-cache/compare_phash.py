from itertools import combinations
from pathlib import Path

import imagehash
from PIL import Image, ImageOps


IMAGES_FOLDER = Path(__file__).parent / "images" / "phash_test"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_image_hashes():
    image_hashes = []

    for image_path in IMAGES_FOLDER.iterdir():
        if not image_path.is_file():
            continue

        if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        try:
            with Image.open(image_path) as image:
                original_size = image.size
                orientation = image.getexif().get(274)

                # Apply any rotation stored in the image's EXIF metadata.
                image = ImageOps.exif_transpose(image)
                image = image.convert("RGB")

                phash = imagehash.phash(image)

            print(
                f"{image_path.name}: "
                f"size={original_size}, "
                f"orientation={orientation}, "
                f"phash={phash}"
            )

            image_hashes.append(
                {
                    "path": image_path,
                    "phash": phash,
                }
            )

        except OSError as error:
            print(f"Could not read {image_path.name}: {error}")

    return image_hashes


def compare_hashes(image_hashes):
    results = []

    for first, second in combinations(image_hashes, 2):
        # The distance counts how many bits differ between the hashes.
        # A smaller distance means the images are more visually similar.
        distance = first["phash"] - second["phash"]

        results.append(
            {
                "first": first,
                "second": second,
                "distance": distance,
            }
        )

    return sorted(results, key=lambda result: result["distance"])


def print_results(results):
    print("\nClosest pHash matches\n")

    for result in results:
        first = result["first"]
        second = result["second"]

        print(
            f"{first['path'].name} "
            f"↔ {second['path'].name}: "
            f"distance {result['distance']}"
        )


def main():
    print(f"Looking for images in: {IMAGES_FOLDER}")

    if not IMAGES_FOLDER.exists():
        print(f"Images folder not found: {IMAGES_FOLDER}")
        return

    image_hashes = load_image_hashes()

    if len(image_hashes) < 2:
        print(f"Found only {len(image_hashes)} supported image(s).")
        print("Add at least two JPG, JPEG, PNG, or WEBP images.")
        return

    print(f"\nFound {len(image_hashes)} images")

    results = compare_hashes(image_hashes)
    print_results(results)


if __name__ == "__main__":
    main()
