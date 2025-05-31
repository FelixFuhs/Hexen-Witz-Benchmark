import pytest
from src.extractor import extract_summary, SummaryParseError
from src.models import Summary

# Tests for summary extraction will be implemented here.
# The if __name__ == "__main__": block in extractor.py already provides a good base.
# These tests should be more formal pytest-style tests.

# Example test cases from extractor.py to be ported:
# - Valid responses with different formatting (whitespace, casing).
# - Invalid responses (missing heading, wrong heading, missing keywords, empty values).
# - Responses that should trigger SummaryParseError.
# - Ensure correct Summary object is returned for valid inputs.

# Test function structure:
# def test_extract_summary_valid_simple():
#     response = "### ZUSAMMENFASSUNG\n- Gewünscht: A\n- Bekommen: B"
#     expected = Summary(gewuenscht="A", bekommen="B")
#     assert extract_summary(response) == expected

# def test_extract_summary_invalid_no_heading():
#     response = "- Gewünscht: A\n- Bekommen: B"
#     with pytest.raises(SummaryParseError, match="heading not found"):
#         extract_summary(response)

# def test_extract_summary_empty_value():
#     response = "### ZUSAMMENFASSUNG\n- Gewünscht:\n- Bekommen: B"
#     with pytest.raises(SummaryParseError, match="Gewünscht value is empty"):
#         extract_summary(response)
