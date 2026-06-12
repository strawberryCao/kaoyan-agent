import argparse
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a YOLO focus-state model.")
    parser.add_argument("--data", required=True, help="Path to YOLO dataset yaml.")
    parser.add_argument("--model", default="yolov8n.pt", help="Base YOLO checkpoint.")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--project", default="runs/focus_yolo")
    parser.add_argument("--name", default="focus_state")
    parser.add_argument(
        "--fraction",
        type=float,
        default=1.0,
        help="Fraction of training data to use. Lower this for smoke tests.",
    )
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--device", default=None, help="Training device, for example cpu or 0.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"Dataset yaml not found: {data_path}")

    if os.name == "nt":
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    yolo_config_dir = PROJECT_ROOT / "data" / "ultralytics"
    yolo_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(yolo_config_dir.resolve()))

    try:
        from ultralytics import YOLO
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install ultralytics first: pip install ultralytics") from exc

    project_path = Path(args.project)
    if not project_path.is_absolute():
        project_path = PROJECT_ROOT / project_path

    model = YOLO(args.model)
    model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=str(project_path),
        name=args.name,
        fraction=args.fraction,
        workers=args.workers,
        device=args.device,
    )


if __name__ == "__main__":
    main()
