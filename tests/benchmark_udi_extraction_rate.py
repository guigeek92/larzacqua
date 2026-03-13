from __future__ import annotations

import json
from pathlib import Path

from src.ai_extraction import _extract_udi_fields_from_text

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "udi_real_cases.json"

# Critical fields requested by product requirements.
CRITICAL_FIELDS = [
    "nom_udi",
    "debit_m3_j",
    "volume_reservoir_m3",
    "denivele_source_reservoir_m",
    "presence_reducteurs_pression",
]


def is_present(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


def main() -> None:
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    total_slots = len(cases) * len(CRITICAL_FIELDS)
    found_slots = 0

    print(f"cases={len(cases)}")
    for case in cases:
        extracted = _extract_udi_fields_from_text(case["text"])
        present_fields = [field for field in CRITICAL_FIELDS if is_present(extracted.get(field))]
        found_slots += len(present_fields)
        print(
            f"{case['id']}: present={len(present_fields)}/{len(CRITICAL_FIELDS)} "
            f"-> {', '.join(present_fields) if present_fields else '-'}"
        )

    rate = (found_slots / total_slots) * 100 if total_slots else 0.0
    print(f"coverage={found_slots}/{total_slots} ({rate:.1f}%)")


if __name__ == "__main__":
    main()
