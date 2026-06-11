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
python scripts/train_focus_yolo.py --data path\to\data.yaml --epochs 50 --imgsz 640 --batch 8
```

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
