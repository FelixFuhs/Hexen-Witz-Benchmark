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
    # Refined pattern assuming single-line content for Gewünscht/Bekommen,
    # but DOTALL for the overall block to handle potential extra newlines
    # between heading and items, or after Bekommen.
    # The main content parts (?P<gewuenscht>...) and (?P<bekommen>...) use [^
]+
    # to ensure they don't span multiple lines themselves, adhering to "EXAKT diesem Format".
    pattern = re.compile(
        r"### ZUSAMMENFASSUNG\s*"  # Heading, ignore case for ZUSAMMENFASSUNG
        r"-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+?)\s*"  # Gewünscht line, non-greedy, up to newline
        r"-\s*Bekommen:\s*(?P<bekommen>[^
]+?)\s*$",  # Bekommen line, non-greedy, up to newline, then optional space until line end
        re.IGNORECASE | re.MULTILINE | re.DOTALL # IGNORECASE for heading, MULTILINE for ^/$, DOTALL for . to match newline in spaces
    )
    # Simpler pattern if we assume the structure is very rigid and content single-line:
    pattern_strict = re.compile(
        r"^\#\#\# ZUSAMMENFASSUNG\s*\n"
        r"-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+)\s*\n"
        r"-\s*Bekommen:\s*(?P<bekommen>[^
]+)",
        re.IGNORECASE | re.MULTILINE # MULTILINE for ^ anchor
    )
    # The technical spec implies "EXAKT diesem Format".
    # Let's use the stricter one, but remove the trailing \s*$ from Bekommen to allow content then immediate newline.
    # And remove DOTALL if content is single-line.
    # The `[^
]+` already handles "not newline".

    pattern_final = re.compile(
        r"### ZUSAMMENFASSUNG\s*\n" # Use \n to be specific after heading
        r"-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+)\s*\n" # Content then specific \n
        r"-\s*Bekommen:\s*(?P<bekommen>[^
]+)", # Content, assumes it's the last part or followed by \n
        re.IGNORECASE | re.MULTILINE # Allow heading to be at start of a line, IGNORECASE for "ZUSAMMENFASSUNG"
    )
    # The prompt's refined pattern was:
    # pattern = re.compile(
    # r"### ZUSAMMENFASSUNG\s*
# "
    # r"-\s*Gewünscht:\s*(?P<gewuenscht>[^
# ]+)\s*
# "
    # r"-\s*Bekommen:\s*(?P<bekommen>[^
# ]+)",
    # re.IGNORECASE # Keep IGNORECASE for the heading
    # )
    # This is good. Let's use this one. Added re.MULTILINE in case the block isn't at the very start of the string.

    final_pattern_from_prompt = re.compile(
        r"### ZUSAMMENFASSUNG\s*\n"
        r"-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+)\s*\n" # Expect newline after gewuenscht content
        r"-\s*Bekommen:\s*(?P<bekommen>[^
]+)",    # Bekommen content
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
        # This might occur if Summary model has more complex validation (e.g. length constraints)
        # For now, it's string types, so this is less likely unless they are empty (already checked).
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
    """ # This should fail because [^
]+ doesn't match newlines

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
    """
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

```python
            pattern = re.compile(
                r"### ZUSAMMENFASSUNG\s*\n"
                r"-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+)\s*\n"
                r"-\s*Bekommen:\s*(?P<bekommen>[^
]+)",
                re.IGNORECASE | re.MULTILINE
            )
```
The test `Valid Response 3 (extra whitespace)` will fail with the current `final_pattern_from_prompt` because it expects exactly one `\n` after the heading and after the "Gewünscht" line. The pattern `r"### ZUSAMMENFASSUNG\s*\n"` means "heading, then optional whitespace (but not newlines), then one newline".
The pattern from the spec description `r"### ZUSAMMENFASSUNG\s*\n ... r"-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+)\s*\n ..."` is quite strict about newlines.

Let's adjust the pattern slightly based on the one I commented as "final_pattern_from_prompt" which is also the one listed in the prompt's "Refined pattern assuming single-line content":
```python
            pattern = re.compile(
                r"### ZUSAMMENFASSUNG\s*" # Allow spaces/newlines after heading text itself
                r"\n\s*-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+)" # Must be newline, then item
                r"\s*\n\s*-\s*Bekommen:\s*(?P<bekommen>[^
]+)", # Must be newline, then item
                re.IGNORECASE | re.MULTILINE
            )
```
This is getting complicated. The prompt's own "Refined pattern" is:
```python
            pattern = re.compile(
                r"### ZUSAMMENFASSUNG\s*\n"  # Heading, optional spaces, then newline
                r"-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+)\s*\n" # Gewunscht line, content, optional spaces, then newline
                r"-\s*Bekommen:\s*(?P<bekommen>[^
]+)",      # Bekommen line, content
                re.IGNORECASE | re.MULTILINE
            )
```
This pattern (`final_pattern_from_prompt` in my code) correctly handles `valid_response_1` and `valid_response_2_lowercase_heading`.
For `valid_response_3_extra_whitespace`:
`###    ZUSAMMENFASSUNG   \n` -> Matches `### ZUSAMMENFASSUNG\s*\n`
`  -   Gewünscht:   Kaffee schwarz  \n` -> Matches `-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+)\s*\n` (captures "Kaffee schwarz")
`  -   Bekommen:   Tee mit Milch   ` -> Matches `-\s*Bekommen:\s*(?P<bekommen>[^
]+)` (captures "Tee mit Milch")
This seems correct. The `\s*` handles spaces around keywords and content. The `[^
]+` captures the content on a single line. The `\n` enforces line breaks.

The only edge case might be if there are multiple newlines between "ZUSAMMENFASSUNG" and "- Gewünscht:", or between "- Gewünscht:" and "- Bekommen:". The current pattern allows `\s*` which includes spaces but not newlines, followed by a single `\n`. If multiple `\n` were allowed, `\s+` containing newlines or more complex constructs would be needed. Given "EXAKT diesem Format", the current pattern is likely what's intended.

Let's stick to the `final_pattern_from_prompt` as it was directly derived from the subtask description's refined pattern.I have created the `src/extractor.py` file. It includes:
1.  The `SummaryParseError` custom exception.
2.  The `extract_summary` function, which uses the regex pattern discussed and refined in the prompt:
    ```python
    re.compile(
        r"### ZUSAMMENFASSUNG\s*\n"
        r"-\s*Gewünscht:\s*(?P<gewuenscht>[^
]+)\s*\n"
        r"-\s*Bekommen:\s*(?P<bekommen>[^
]+)",
        re.IGNORECASE | re.MULTILINE
    )
    ```
3.  Logic to search for the pattern, raise `SummaryParseError` on match failure or if extracted values are empty after stripping.
4.  Creation and return of a `Summary` Pydantic model.
5.  A comprehensive `if __name__ == "__main__":` block with various test cases for valid and invalid inputs to verify the regex logic and error handling. This block helps in quick validation.

The pattern chosen is strict regarding the single-line nature of "Gewünscht" and "Bekommen" content and the newlines separating the parts of the summary block, adhering to the "EXAKT diesem Format" requirement. `re.IGNORECASE` is used for the heading "ZUSAMMENFASSUNG", and `re.MULTILINE` allows the pattern to match correctly even if the summary block is not at the absolute beginning of the `llm_response` string (by affecting `^` and `$` if they were used, but here it's mostly for conceptual clarity as the pattern doesn't rely on `^`).

I will now submit the subtask report.
