from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


FOCUSED_LABELS = {
    "book",
    "laptop",
    "read",
    "reading",
    "study",
    "studying",
    "write",
    "writing",
}
DISTRACTED_LABELS = {
    "cell phone",
    "drinking",
    "eating",
    "look at phone",
    "mobile phone",
    "phone",
    "talk",
    "talking",
    "turn head",
    "turning around",
    "using mobile phone",
    "using phone",
}
AWAY_LABELS = {"leaving", "stand", "standing", "walk", "walking"}
BLOCKED_LABELS = {"blocked", "covered", "dark", "occluded"}
SLEEPY_LABELS = {
    "bowing head",
    "head down",
    "lying",
    "lying on desk",
    "sleep",
    "sleeping",
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
    """Map detector labels to the product focus-state vocabulary."""

    def classify(self, detections: Iterable[Dict[str, Any]]) -> FocusRuleResult:
        items = list(detections)
        labels = [self.normalize_label(item.get("label", "")) for item in items]
        person_present = any(label in {"person", "sitting", "student"} for label in labels)
        metrics = {
            "detections": items,
            "labels": labels,
            "person_present": person_present,
            "phone_count": sum(1 for label in labels if label in DISTRACTED_LABELS),
            "away_action_count": sum(1 for label in labels if label in AWAY_LABELS),
            "sleepy_action_count": sum(1 for label in labels if label in SLEEPY_LABELS),
        }

        blocked = self.max_confidence(items, BLOCKED_LABELS)
        away = self.max_confidence(items, AWAY_LABELS)
        distracted = max(
            self.max_confidence(items, DISTRACTED_LABELS),
            self.max_confidence(items, SLEEPY_LABELS),
        )
        focused = self.max_confidence(items, FOCUSED_LABELS)

        if blocked > 0:
            return self.result("blocked", blocked, labels, metrics)
        if away > 0:
            return self.result("away", away, labels, metrics)
        if not person_present and not labels:
            return FocusRuleResult(
                state_type="unknown",
                confidence=0.0,
                explanation="No behavior detection is not proof that the person left.",
                metrics=metrics,
            )
        if distracted > 0:
            return self.result("distracted", distracted, labels, metrics)
        if focused > 0:
            return self.result("focused", focused, labels, metrics)
        if person_present:
            return FocusRuleResult(
                state_type="unknown",
                confidence=0.0,
                explanation="Person is visible but study behavior is not determined.",
                metrics=metrics,
            )
        return FocusRuleResult(
            state_type="unknown",
            confidence=0.2,
            explanation="Detector labels do not map to a focus state.",
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
            explanation=f"Local rule classified state as {state_type}; labels={visible}.",
            metrics=metrics,
        )

    def max_confidence(
        self,
        detections: Iterable[Dict[str, Any]],
        target_labels: set[str],
    ) -> float:
        best = 0.0
        for item in detections:
            if self.normalize_label(item.get("label", "")) not in target_labels:
                continue
            try:
                best = max(best, float(item.get("confidence", 0.0)))
            except (TypeError, ValueError):
                continue
        return best

    def normalize_label(self, label: Any) -> str:
        return str(label or "").strip().lower().replace("-", " ").replace("_", " ")
