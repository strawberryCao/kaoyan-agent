from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


FOCUSED_LABELS = {
    "read",
    "reading",
    "write",
    "writing",
    "study",
    "studying",
    "book",
    "laptop",
}

DISTRACTED_LABELS = {
    "phone",
    "cell phone",
    "mobile phone",
    "using phone",
    "using mobile phone",
    "look at phone",
    "turning around",
    "turn head",
    "talk",
    "talking",
    "discuss",
    "discussing",
    "eating",
    "drinking",
}

AWAY_LABELS = {
    "stand",
    "standing",
    "walking",
    "walk",
    "leaving",
}

BLOCKED_LABELS = {
    "blocked",
    "occluded",
    "covered",
    "dark",
}

SLEEPY_LABELS = {
    "sleep",
    "sleeping",
    "head down",
    "bowing head",
    "lying",
    "lying on desk",
    "yawn",
    "yawning",
}


@dataclass(frozen=True)
class FocusRuleResult:
    state_type: str
    confidence: float
    explanation: str
    metrics: Dict[str, Any]


class FocusStateRuleEngine:
    """Map YOLO detections to the project focus-state vocabulary.

    YOLO detects visible objects/actions. The product state is a higher-level
    interpretation, so this class keeps the mapping explicit and easy to tune.
    """

    def classify(self, detections: Iterable[Dict[str, Any]]) -> FocusRuleResult:
        items = list(detections)
        labels = [self.normalize_label(item.get("label", "")) for item in items]
        confidence_by_group = {
            "focused": self.max_confidence(items, FOCUSED_LABELS),
            "distracted": max(
                self.max_confidence(items, DISTRACTED_LABELS),
                self.max_confidence(items, SLEEPY_LABELS),
            ),
            "away": self.max_confidence(items, AWAY_LABELS),
            "blocked": self.max_confidence(items, BLOCKED_LABELS),
        }

        person_present = any(label in {"person", "student", "sitting"} for label in labels)
        metrics = {
            "detections": items,
            "labels": labels,
            "person_present": person_present,
            "phone_count": sum(1 for label in labels if label in DISTRACTED_LABELS),
            "away_action_count": sum(1 for label in labels if label in AWAY_LABELS),
            "sleepy_action_count": sum(1 for label in labels if label in SLEEPY_LABELS),
        }

        if confidence_by_group["blocked"] > 0:
            return self.result("blocked", confidence_by_group["blocked"], labels, metrics)
        if confidence_by_group["away"] > 0:
            return self.result("away", confidence_by_group["away"], labels, metrics)
        if not person_present and not labels:
            return FocusRuleResult(
                state_type="away",
                confidence=0.65,
                explanation="Local model found no visible person or study behavior.",
                metrics=metrics,
            )
        if confidence_by_group["distracted"] > 0:
            return self.result("distracted", confidence_by_group["distracted"], labels, metrics)
        if confidence_by_group["focused"] > 0 or person_present:
            confidence = max(confidence_by_group["focused"], 0.55 if person_present else 0.0)
            return self.result("focused", confidence, labels, metrics)

        return FocusRuleResult(
            state_type="unknown",
            confidence=0.2,
            explanation="Local model produced detections that do not map to a focus state.",
            metrics=metrics,
        )

    def result(
        self,
        state_type: str,
        confidence: float,
        labels: List[str],
        metrics: Dict[str, Any],
    ) -> FocusRuleResult:
        visible = ", ".join(labels[:8]) if labels else "none"
        return FocusRuleResult(
            state_type=state_type,
            confidence=max(0.0, min(1.0, float(confidence))),
            explanation=f"Local YOLO rule classified state as {state_type}; labels={visible}.",
            metrics=metrics,
        )

    def max_confidence(
        self,
        detections: Iterable[Dict[str, Any]],
        target_labels: set[str],
    ) -> float:
        best = 0.0
        for item in detections:
            if self.normalize_label(item.get("label", "")) in target_labels:
                try:
                    best = max(best, float(item.get("confidence", 0.0)))
                except (TypeError, ValueError):
                    continue
        return best

    def normalize_label(self, label: Any) -> str:
        return str(label or "").strip().lower().replace("-", " ").replace("_", " ")
