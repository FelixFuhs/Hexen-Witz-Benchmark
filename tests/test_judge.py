import pytest
from src.judge import judge_response, load_judge_prompt_template, format_judge_prompt
from src.router_client import RouterClient # For mocking or actual client
from src.config import Settings
from src.models import GenerationResult, JudgeScore, Summary
from datetime import datetime, timezone
# from pytest_httpx import HTTPXMock # If making actual calls that need mocking

# Tests for judge.py will be implemented here.

# Example test ideas for judge.py:
# - test_load_judge_prompt_template_success: Mock Path.read_text.
# - test_load_judge_prompt_template_not_found: Mock Path.read_text to raise FileNotFoundError.
# - test_format_judge_prompt: Test with a sample template and Summary.
# - test_judge_response_success:
#   - Mock RouterClient.chat to return a valid JSON string for JudgeScore.
#   - Verify JudgeScore is parsed and returned correctly (including clamping if applicable).
# - test_judge_response_summary_missing: Provide GenerationResult with summary=None, check for skip.
# - test_judge_response_json_decode_error: Mock RouterClient.chat to return malformed JSON.
# - test_judge_response_validation_error: Mock RouterClient.chat to return JSON with missing/invalid fields for JudgeScore.
# - test_judge_response_api_error: Mock RouterClient.chat to raise an API error.
# - test_judge_response_json_extraction_from_markdown: Test if JSON is correctly extracted from "```json ... ```".

@pytest.fixture
def mock_router_client_judge(httpx_mock):
    settings = Settings(OPENROUTER_API_KEY="fake_api_key_for_judge_test", MAX_BUDGET_USD=1.0)
    return RouterClient(settings)

@pytest.fixture
def dummy_judge_template_file(tmp_path):
    prompt_dir = tmp_path / "src" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    file_path = prompt_dir / "judge_checklist.md"
    file_path.write_text(
        "WUNSCH: [aus der Antwort extrahiert]\n"
        "ERGEBNIS: [aus der Antwort extrahiert]\n"
        "VOLLSTAENDIGE ANTWORT DES GETESTETEN MODELLS: [hier die komplette Antwort des LLMs einfügen]\n"
        "Return JSON: ..."
    )
    return str(file_path)

@pytest.fixture
def sample_generation_result_with_summary():
    summary = Summary(gewuenscht="Test Wunsch", bekommen="Test Bekommen")
    return GenerationResult(
        model="test/model",
        run=1,
        summary=summary,
        full_response="This is the full response.",
        prompt_tokens=10,
        completion_tokens=20,
        cost_usd=0.001,
        timestamp=datetime.now(timezone.utc)
    )

@pytest.fixture
def sample_generation_result_no_summary():
    return GenerationResult(
        model="test/model",
        run=2,
        summary=None,
        full_response="This response has no summary.",
        prompt_tokens=5,
        completion_tokens=5,
        cost_usd=0.0005,
        timestamp=datetime.now(timezone.utc)
    )
