import argparse
import math
import shutil
import zipfile
from pathlib import Path


CLASS_NAMES = {
    0: "hand_raising",
    1: "reading",
    2: "writing",
    3: "using_phone",
    4: "bowing_head",
    5: "leaning_over_table",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare SCB-Dataset3 zip files as a YOLO training dataset."
    )
    parser.add_argument(
        "--zip",
        action="append",
        dest="zips",
        required=True,
        help="Path to an SCB YOLO zip. Pass this option more than once to combine zips.",
    )
    parser.add_argument("--output", required=True, help="Prepared dataset directory.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove the output directory before preparing the dataset.",
    )
    return parser.parse_args()


def split_from_name(name: str) -> str | None:
    lower = name.replace("\\", "/").lower()
    parts = [part for part in lower.split("/") if part]
    if "train" in parts or "train1" in parts or "train2" in parts:
        return "train"
    if "val" in parts or "valid" in parts or "validation" in parts:
        return "val"
    return None


def make_output_dirs(output: Path) -> None:
    for folder in ("images/train", "images/val", "labels/train", "labels/val"):
        (output / folder).mkdir(parents=True, exist_ok=True)


def matching_label_names(image_name: str) -> list[str]:
    path = Path(image_name.replace("\\", "/"))
    stem = path.with_suffix(".txt")
    candidates = {str(stem).replace("\\", "/")}
    normalized = str(stem).replace("\\", "/")
    if "/images/" in normalized:
        candidates.add(normalized.replace("/images/", "/labels/", 1))
    return sorted(candidates)


def copy_entry(zip_file: zipfile.ZipFile, source_name: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zip_file.open(source_name) as source, target.open("wb") as destination:
        shutil.copyfileobj(source, destination)


def sanitize_label_text(text: str) -> tuple[str, int]:
    kept_lines = []
    dropped = 0
    for raw_line in text.splitlines():
        parts = raw_line.strip().split()
        if not parts:
            continue
        if len(parts) < 5:
            dropped += 1
            continue

        try:
            class_id = int(parts[0])
            x_center, y_center, width, height = [float(value) for value in parts[1:5]]
        except ValueError:
            dropped += 1
            continue

        coordinates = (x_center, y_center, width, height)
        if class_id not in CLASS_NAMES:
            dropped += 1
            continue
        if not all(math.isfinite(value) for value in coordinates):
            dropped += 1
            continue
        if width <= 0 or height <= 0:
            dropped += 1
            continue
        if not all(0 <= value <= 1 for value in coordinates):
            dropped += 1
            continue

        kept_lines.append(
            f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
        )

    return ("\n".join(kept_lines) + ("\n" if kept_lines else "")), dropped


def copy_label_entry(
    zip_file: zipfile.ZipFile,
    source_name: str,
    target: Path,
) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zip_file.open(source_name) as source:
        text = source.read().decode("utf-8", errors="replace")
    sanitized_text, dropped = sanitize_label_text(text)
    target.write_text(sanitized_text, encoding="utf-8")
    return dropped


def prepare_zip(zip_path: Path, output: Path) -> tuple[int, int, int, int]:
    dataset_prefix = zip_path.stem.replace(" ", "_")
    copied_images = 0
    copied_labels = 0
    missing_labels = 0
    dropped_boxes = 0

    with zipfile.ZipFile(zip_path) as archive:
        names = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
        name_lookup = {name.replace("\\", "/").lower(): name for name in names}
        images = [
            name
            for name in names
            if Path(name).suffix.lower() in IMAGE_EXTENSIONS and split_from_name(name)
        ]

        for image_name in images:
            split = split_from_name(image_name)
            if split is None:
                continue

            source_path = Path(image_name.replace("\\", "/"))
            safe_name = f"{dataset_prefix}__{source_path.name}"
            copy_entry(archive, image_name, output / "images" / split / safe_name)
            copied_images += 1

            label_name = None
            for candidate in matching_label_names(image_name):
                found = name_lookup.get(candidate.lower())
                if found is not None:
                    label_name = found
                    break

            label_target = output / "labels" / split / f"{Path(safe_name).stem}.txt"
            if label_name is None:
                label_target.write_text("", encoding="utf-8")
                missing_labels += 1
            else:
                dropped_boxes += copy_label_entry(archive, label_name, label_target)
                copied_labels += 1

    return copied_images, copied_labels, missing_labels, dropped_boxes


def write_data_yaml(output: Path) -> None:
    names = "\n".join(f"  {index}: {name}" for index, name in CLASS_NAMES.items())
    content = (
        f"path: {output.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        f"{names}\n"
    )
    (output / "data.yaml").write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    output = Path(args.output).resolve()
    zip_paths = [Path(zip_path).resolve() for zip_path in args.zips]

    missing = [zip_path for zip_path in zip_paths if not zip_path.exists()]
    if missing:
        raise FileNotFoundError(f"Zip not found: {missing[0]}")

    if args.reset and output.exists():
        shutil.rmtree(output)

    make_output_dirs(output)

    total_images = 0
    total_labels = 0
    total_missing_labels = 0
    total_dropped_boxes = 0
    for zip_path in zip_paths:
        images, labels, missing_labels, dropped_boxes = prepare_zip(zip_path, output)
        total_images += images
        total_labels += labels
        total_missing_labels += missing_labels
        total_dropped_boxes += dropped_boxes
        print(
            f"{zip_path.name}: images={images}, labels={labels}, "
            f"missing_labels={missing_labels}, dropped_boxes={dropped_boxes}"
        )

    write_data_yaml(output)
    print(
        f"prepared={output} images={total_images} labels={total_labels} "
        f"missing_labels={total_missing_labels} dropped_boxes={total_dropped_boxes}"
    )
    print(f"data_yaml={output / 'data.yaml'}")


if __name__ == "__main__":
    main()
