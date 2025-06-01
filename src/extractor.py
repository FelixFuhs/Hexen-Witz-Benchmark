import re
from typing import Optional
from src.models import Summary
from pydantic import ValidationError

class SummaryParseError(ValueError):
    """Custom exception for errors during summary parsing."""
    pass

def extract_summary(llm_response: str) -> Summary:
    """
    Extracts the 'Gewünscht' and 'Bekommen' items from the LLM response
    under the '### ZUSAMMENFASSUNG' heading.

    Args:
        llm_response: The text response from the language model.

    Returns:
        A Summary object with the extracted information.

    Raises:
        SummaryParseError: If the summary block is not found, is malformed,
                           or if 'Gewünscht' or 'Bekommen' values are empty.
    """
    # This is the final pattern decided upon in previous discussions
    final_pattern_from_prompt = re.compile(
        r"### ZUSAMMENFASSUNG\s*\n"
        r"-\s*Gewünscht:\s*(?P<gewuenscht>[^\n]+)\s*\n" # Expect newline after gewuenscht content
        r"-\s*Bekommen:\s*(?P<bekommen>[^\n]+)",    # Bekommen content
        re.IGNORECASE | re.MULTILINE # Search per line for the header, IGNORECASE for header text
    )

    match = final_pattern_from_prompt.search(llm_response)

    if not match:
        raise SummaryParseError(
            "Summary block with '### ZUSAMMENFASSUNG' heading not found or format is incorrect. "
            "Expected format:\n### ZUSAMMENFASSUNG\n- Gewünscht: <text>\n- Bekommen: <text>"
        )

    gewuenscht_text = match.group("gewuenscht").strip()
    bekommen_text = match.group("bekommen").strip()

    if not gewuenscht_text:
        raise SummaryParseError("Gewünscht value is empty or contains only whitespace.")
    if not bekommen_text:
        raise SummaryParseError("Bekommen value is empty or contains only whitespace.")

    try:
        summary = Summary(gewuenscht=gewuenscht_text, bekommen=bekommen_text)
        return summary
    except ValidationError as e:
        raise SummaryParseError(f"Validation error when creating Summary object: {e}")


if __name__ == "__main__":
    print("--- Extractor Test ---")

    valid_response_1 = """
Some text before.
### ZUSAMMENFASSUNG
- Gewünscht: Ein Haus am See
- Bekommen: Eine Wohnung in der Stadt
Some text after.
    """

    valid_response_2_lowercase_heading = """
### zusammenfassung
- Gewünscht: Schnelles Auto
- Bekommen: Fahrrad
    """

    valid_response_3_extra_whitespace = """
###    ZUSAMMENFASSUNG
  -   Gewünscht:   Kaffee schwarz
  -   Bekommen:   Tee mit Milch
    """

    invalid_response_no_heading = """
- Gewünscht: Urlaub
- Bekommen: Arbeit
    """

    invalid_response_wrong_heading = """
### SUMMARY
- Gewünscht: Katze
- Bekommen: Hund
    """

    invalid_response_missing_gewuenscht_keyword = """
### ZUSAMMENFASSUNG
- Gwnscht: Etwas
- Bekommen: Nichts
    """

    invalid_response_missing_bekommen_keyword = """
### ZUSAMMENFASSUNG
- Gewünscht: Alles
- Bkommen: Wenig
    """

    invalid_response_empty_gewuenscht_value = """
### ZUSAMMENFASSUNG
- Gewünscht:
- Bekommen: Ein voller Wert
    """

    invalid_response_empty_bekommen_value = """
### ZUSAMMENFASSUNG
- Gewünscht: Ein voller Wert
- Bekommen:
    """

    invalid_response_multiline_value = """
### ZUSAMMENFASSUNG
- Gewünscht: Ein Haus
am See
- Bekommen: Eine Wohnung in der Stadt
    """ # This should fail because [^\n]+ doesn't match newlines

    tests = {
        "Valid Response 1": (valid_response_1, True),
        "Valid Response 2 (lowercase heading)": (valid_response_2_lowercase_heading, True),
        "Valid Response 3 (extra whitespace)": (valid_response_3_extra_whitespace, True),
        "Invalid - No Heading": (invalid_response_no_heading, False),
        "Invalid - Wrong Heading": (invalid_response_wrong_heading, False),
        "Invalid - Missing 'Gewünscht' Keyword": (invalid_response_missing_gewuenscht_keyword, False),
        "Invalid - Missing 'Bekommen' Keyword": (invalid_response_missing_bekommen_keyword, False),
        "Invalid - Empty 'Gewünscht' Value": (invalid_response_empty_gewuenscht_value, False),
        "Invalid - Empty 'Bekommen' Value": (invalid_response_empty_bekommen_value, False),
        "Invalid - Multiline Value (should fail)": (invalid_response_multiline_value, False),
    }

    for name, (response_text, should_succeed) in tests.items():
        print(f"\nTesting: {name}")
        try:
            summary = extract_summary(response_text)
            if should_succeed:
                print(f"  Success (as expected): {summary}")
            else:
                print(f"  !!! UNEXPECTED Success: {summary} (but should have failed)")
        except SummaryParseError as e:
            if not should_succeed:
                print(f"  Success (error as expected): {e}")
            else:
                print(f"  !!! UNEXPECTED Error: {e} (but should have succeeded)")
        except Exception as e:
            print(f"  !!! UNEXPECTED Exception type: {e}")

    print("\n--- Test with only spaces for a value (should fail on strip check) ---")
    invalid_response_spaces_value = """
### ZUSAMMENFASSUNG
- Gewünscht: Ein voller Wert
- Bekommen:      
    """ # Note: added spaces to 'Bekommen' to make the test more explicit for empty after strip
    try:
        summary = extract_summary(invalid_response_spaces_value)
        print(f"  !!! UNEXPECTED Success: {summary} (but should have failed due to empty 'Bekommen')")
    except SummaryParseError as e:
        print(f"  Success (error as expected for spaces value): {e}")

    print("\n--- Test with content on same line as heading (should fail due to \\n in pattern) ---")
    invalid_response_content_same_line_as_heading = "### ZUSAMMENFASSUNG - Gewünscht: X - Bekommen: Y"
    try:
        summary = extract_summary(invalid_response_content_same_line_as_heading)
        print(f"  !!! UNEXPECTED Success: {summary} (but should have failed)")
    except SummaryParseError as e:
        print(f"  Success (error as expected for content on same line as heading): {e}")

    print("\n--- Test with content directly after Bekommen: (no trailing space, should pass) ---")
    valid_response_no_trailing_space_bekommen = """
### ZUSAMMENFASSUNG
- Gewünscht: Test1
- Bekommen:Test2
"""
    try:
        summary = extract_summary(valid_response_no_trailing_space_bekommen)
        print(f"  Success (as expected): {summary}")
    except SummaryParseError as e:
        print(f"  !!! UNEXPECTED Error: {e} (but should have succeeded)")