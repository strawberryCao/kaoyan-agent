# Task E Local YOLO Training

This file records the local-model path for Task E. The current production
fallback is saved in git as:

```text
commit: 049ad41
tag: task-e-multimodal-fallback
```

## Goal

Keep the existing supervision pipeline:

```text
Streamlit WebRTC camera stream
-> periodic latest-frame sampling
-> local YOLO focus detector first
-> multimodal model fallback if local model is unavailable
-> focus_state_events
-> focus_reports
```

## Candidate Dataset

The closest public starting point found so far is the SCB student classroom
behavior dataset family. Its GitHub README lists classroom behavior labels such
as reading, writing, using mobile phones, sleeping, standing, turning around,
and related student behaviors. It also points to HuggingFace/Baidu dataset and
model links, but the dataset can be large and has non-commercial restrictions.

Candidate links:

```text
GitHub: https://github.com/Whiffe/SCB-dataset
HuggingFace: https://huggingface.co/datasets/Whiffe/SCB-Dataset
```

Do not download the full dataset until the team confirms license, size, and
network/storage budget.

The first local-model iteration should use the already-downloaded
SCB-Dataset3 YOLO archive. It is smaller, already available locally, and covers
the first useful product states: reading/writing as focused, phone usage as
distracted, and head-down/leaning behavior as fatigue or distraction. Larger
SCB releases can be evaluated after the camera-to-report loop works end to end.

## Preparing SCB-Dataset3

Extract these zip files from the local `.rar` archive first:

```text
SCB-Dataset3 yolo dataset\5k_HRW_yolo_Dataset_jpg.zip
SCB-Dataset3 yolo dataset\0.671k_university_yolo_Dataset.zip
```

Then combine them into a standard YOLO folder:

```powershell
python scripts/prepare_scb_dataset.py `
  --zip "d:\摄像头状态数据\inspect_scb\SCB-Dataset3 yolo dataset\5k_HRW_yolo_Dataset_jpg.zip" `
  --zip "d:\摄像头状态数据\inspect_scb\SCB-Dataset3 yolo dataset\0.671k_university_yolo_Dataset.zip" `
  --output "d:\kaoyan_datasets\SCB-Dataset3-prepared" `
  --reset
```

The script writes:

```text
d:\kaoyan_datasets\SCB-Dataset3-prepared\data.yaml
d:\kaoyan_datasets\SCB-Dataset3-prepared\images\train
d:\kaoyan_datasets\SCB-Dataset3-prepared\images\val
d:\kaoyan_datasets\SCB-Dataset3-prepared\labels\train
d:\kaoyan_datasets\SCB-Dataset3-prepared\labels\val
```

Use an ASCII-only prepared dataset path for Ultralytics on Windows. Chinese
paths may display or resolve incorrectly in some Anaconda/Ultralytics calls.
The preparation script also drops invalid YOLO label rows, such as out-of-range
coordinates, so one bad box does not make an entire image unusable.

## Label Mapping

Recommended first mapping from YOLO labels to product states:

```text
focused:
- reading
- writing
- studying
- book
- laptop

away:
- no person
- standing
- walking
- leaving

distracted:
- using phone
- mobile phone
- turning around
- talking
- eating/drinking
- sleeping
- yawning
- head down / lying on desk

blocked:
- blocked
- occluded
- covered
- dark
```

Frame-level YOLO labels are not the same as product states. The mapping lives in:

```text
src/kaoyan_agent/vision/focus_state_rules.py
```

## Training

Prepare a YOLO dataset yaml, then run:

```powershell
python scripts/train_focus_yolo.py --data d:\kaoyan_datasets\SCB-Dataset3-prepared\data.yaml --epochs 50 --imgsz 640 --batch 8
```

For a quick smoke test before a full run:

```powershell
python scripts/train_focus_yolo.py `
  --data d:\kaoyan_datasets\SCB-Dataset3-prepared\data.yaml `
  --epochs 1 `
  --imgsz 320 `
  --batch 2 `
  --fraction 0.02 `
  --device cpu `
  --workers 0 `
  --name focus_state_smoke_clean
```

On Windows Anaconda environments, PyTorch/Ultralytics may load duplicate
OpenMP runtimes. The training script sets `KMP_DUPLICATE_LIB_OK=TRUE` by
default on Windows so local training can proceed.

The expected model output is usually:

```text
runs/focus_yolo/focus_state/weights/best.pt
```

Configure the app:

```text
FOCUS_LOCAL_MODEL_PATH=runs/focus_yolo/focus_state/weights/best.pt
FOCUS_LOCAL_MODEL_CONFIDENCE=0.35
```

If the local model path is empty or inference fails, the app uses the saved
multimodal fallback path.
