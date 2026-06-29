from datetime import datetime
from typing import Any, Dict, Iterable, List


def local_today() -> str:
    return datetime.now().astimezone().date().isoformat()


def records_to_table(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(record) for record in records]

