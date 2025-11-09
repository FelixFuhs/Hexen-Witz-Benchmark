from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz
import structlog

from .models import Summary


logger = structlog.get_logger(__name__)


class SummaryParseError(ValueError):
    """Raised when the summary block could not be extracted."""


SUMMARY_HEADER_PATTERN = re.compile(r"^\s*###\s*ZUSAMMENFASSUNG\s*$", re.IGNORECASE | re.MULTILINE)
LINE_PATTERN = re.compile(r"^-\s*(?P<label>[A-Za-zÄÖÜäöüß]+):\s*(?P<value>.+)$")
REQUIRED_LABELS = {"gewuenscht", "bekommen"}


@dataclass
class _ParsedLine:
    label: str
    value: str


def _normalise_label(label: str) -> str:
    label_lower = label.strip().lower()
    for required in REQUIRED_LABELS:
        if fuzz.ratio(label_lower, required) >= 80:
            return required
    return label_lower


def extract_summary(llm_response: str) -> Summary:
    match = SUMMARY_HEADER_PATTERN.search(llm_response)
    if not match:
        raise SummaryParseError("summary header missing")

    after_header = llm_response[match.end() :]
    lines = [line.strip() for line in after_header.splitlines() if line.strip()]
    parsed: dict[str, _ParsedLine] = {}

    for line in lines:
        line_match = LINE_PATTERN.match(line)
        if not line_match:
            if parsed:
                break
            continue
        label = _normalise_label(line_match.group("label"))
        value = line_match.group("value").strip()
        if label in REQUIRED_LABELS:
            if not value:
                raise SummaryParseError(f"value for {label} missing")
            parsed[label] = _ParsedLine(label=label, value=value)
        if len(parsed) == len(REQUIRED_LABELS):
            break

    missing = REQUIRED_LABELS - parsed.keys()
    if missing:
        raise SummaryParseError(f"summary labels missing: {', '.join(sorted(missing))}")

    logger.debug("summary_extracted", parsed_labels=list(parsed.keys()))
    return Summary(gewuenscht=parsed["gewuenscht"].value, bekommen=parsed["bekommen"].value)


__all__ = ["SummaryParseError", "extract_summary"]
