import pytest

from src.extractor import SummaryParseError, extract_summary
from src.models import Summary


def test_extract_summary_standard_block() -> None:
    text = """
    Irrelevant
    ### ZUSAMMENFASSUNG
    - Gewünscht: Ein Schloss
    - Bekommen: Ein Floh
    """
    summary = extract_summary(text)
    assert summary == Summary(gewuenscht="Ein Schloss", bekommen="Ein Floh")


def test_extract_summary_accepts_fuzzy_labels() -> None:
    text = """
    ### ZUSAMMENFASSUNG
    - Gewuenscht: Kaffee
    - Bekomnen: Tee
    """
    summary = extract_summary(text)
    assert summary == Summary(gewuenscht="Kaffee", bekommen="Tee")


def test_extract_summary_missing_header_raises() -> None:
    text = "- Gewünscht: A\n- Bekommen: B"
    with pytest.raises(SummaryParseError):
        extract_summary(text)


def test_extract_summary_missing_value_raises() -> None:
    text = """
    ### ZUSAMMENFASSUNG
    - Gewünscht:
    - Bekommen: B
    """
    with pytest.raises(SummaryParseError):
        extract_summary(text)
