import json
import logging
import re
from typing import Optional, Dict, Any
from pathlib import Path

from pydantic import ValidationError

from src.router_client import RouterClient # Assuming OpenRouterResponse is implicitly handled if not directly imported
from src.models import GenerationResult, JudgeScore, Summary # OpenRouterResponse is defined in models.py
from src.config import Settings 
from datetime import datetime, timezone 
import asyncio 

logger = logging.getLogger(__name__)

def load_judge_prompt_template(file_path: str = "src/prompts/judge_checklist.md") -> str:
    """
    Loads the content of the judge checklist file.
    """
    try:
        template_path = Path(file_path)
        content = template_path.read_text(encoding="utf-8")
        logger.info(f"Successfully loaded judge prompt template from {file_path}")
        return content
    except FileNotFoundError:
        logger.error(f"Judge prompt template file not found at {file_path}")
        raise
    except Exception as e:
        logger.error(f"Error loading judge prompt template from {file_path}: {e}")
        raise

def format_judge_prompt(template: str, summary: Summary, full_response: str) -> str:
    """
    Formats the judge prompt template with the summary's 'gewuenscht' and 'bekommen'
    values, and the full LLM response.
    """
    # Ensure these placeholder strings EXACTLY match those in your judge_checklist.md
    prompt = template.replace("[Was sich der Gast von der Hexe wünscht – wird hier automatisch eingefügt]", f"WUNSCH: {summary.gewuenscht}")
    prompt = prompt.replace("[Was er stattdessen bekommt – wird hier automatisch eingefügt]", f"ERGEBNIS: {summary.bekommen}")
    prompt = prompt.replace("[VOLLSTAENDIGE ANTWORT DES GETESTETEN MODELLS: hier die komplette Antwort des LLMs einfügen]",
                            f"VOLLSTAENDIGE ANTWORT DES GETESTETEN MODELLS:\n```text\n{full_response}\n```")
    return prompt

async def judge_response(
    router_client: RouterClient,
    generation_result: GenerationResult,
    judge_model_name: str,
    judge_prompt_template: str,
    temperature: float = 0.1,
) -> Optional[JudgeScore]:
    """
    Judges a generation result using an LLM.
    """
    if generation_result.summary is None:
        logger.info(
            f"Skipping judging for model {generation_result.model}, run {generation_result.run} "
            "as its summary is missing."
        )
        return None

    current_summary = generation_result.summary
    formatted_prompt = format_judge_prompt(judge_prompt_template, current_summary, generation_result.full_response)

    logger.info(
        f"Judging response for model {generation_result.model}, run {generation_result.run} "
        f"using judge LLM {judge_model_name} with temp {temperature}."
    )

    try:
        # judge_llm_response will be an OpenRouterResponse TypedDict
        judge_llm_response = await router_client.chat(
            model=judge_model_name, prompt=formatted_prompt, temperature=temperature
        )
    except Exception as e:
        logger.error(
            f"Call to judge LLM {judge_model_name} failed for "
            f"{generation_result.model} run {generation_result.run}: {e}",
            exc_info=True
        )
        return None

    # Use dictionary key access for TypedDict
    raw_judge_text = judge_llm_response['text'] # MODIFIED LINE
    logger.debug(f"Raw response from judge LLM {judge_model_name} for "
                 f"{generation_result.model} run {generation_result.run}: {raw_judge_text}")

    judge_data: Optional[Dict[str, Any]] = None
    try:
        json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw_judge_text, re.IGNORECASE)
        json_str: str
        if json_match:
            json_str = json_match.group(1)
            logger.debug(f"Extracted JSON block from judge response: {json_str}")
        else:
            json_str = raw_judge_text
            logger.debug("No JSON block found, attempting to parse entire judge response as JSON.")

        judge_data = json.loads(json_str)
        
        if 'flags' not in judge_data:
            judge_data['flags'] = []

        score = JudgeScore(**judge_data)
        logger.info(
            f"Successfully parsed and validated JudgeScore for {generation_result.model} "
            f"run {generation_result.run}. Flags: {score.flags}"
        )
        return score

    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to decode JSON from judge LLM for {generation_result.model} "
            f"run {generation_result.run}: {e}. Response text: '{raw_judge_text}'"
        )
        return None
    except ValidationError as e:
        error_details = e.errors()
        logger.error(
            f"Validation error for JudgeScore from judge LLM for {generation_result.model} "
            f"run {generation_result.run}: {error_details}. "
            f"Attempted data: {json.dumps(judge_data) if judge_data else 'N/A'}"
        )
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error processing judge response for {generation_result.model} "
            f"run {generation_result.run}: {e}",
            exc_info=True
        )
        return None


async def main_test_judge():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Starting judge test run...")

    dummy_judge_file = Path("src/prompts/judge_checklist.md")
    dummy_judge_file.parent.mkdir(parents=True, exist_ok=True)
    if not dummy_judge_file.exists() or dummy_judge_file.read_text(encoding="utf-8").strip() == "":
        dummy_judge_file.write_text(
            """Bewerte die phonetische Ähnlichkeit und den Witz der folgenden Antwort.
WUNSCH: [aus der Antwort extrahiert]
ERGEBNIS: [aus der Antwort extrahiert]
VOLLSTAENDIGE ANTWORT DES GETESTETEN MODELLS: [hier die komplette Antwort des LLMs einfügen]
Gib deine Bewertung als JSON-Objekt mit den folgenden Feldern zurück:
- phonetische_aehnlichkeit (0-35)
- anzueglichkeit (0-25)
- logik (0-20)
- kreativitaet (0-20)
- gesamt (0-100)
- begruendung (ein Dictionary mit Schlüsseln für jede Kategorie und Text als Wert)
Beispiel-JSON:
```json
{
  "phonetische_aehnlichkeit": 30,
  "anzueglichkeit": 5,
  "logik": 15,
  "kreativitaet": 18,
  "gesamt": 68,
  "begruendung": {
    "phonetische_aehnlichkeit": "Sehr gute phonetische Ähnlichkeit.",
    "anzueglichkeit": "Nicht besonders anzüglich.",
    "logik": "Die Logik ist nachvollziehbar.",
    "kreativitaet": "Kreative Wendung.",
    "gesamt": "Solide Leistung."
  }
}
```""",
            encoding="utf-8"
        )
        logger.info(f"Created/updated dummy judge checklist at {dummy_judge_file}")

    try:
        settings = Settings()
        import os
        if not settings.OPENROUTER_API_KEY or settings.OPENROUTER_API_KEY == "dummy_key_not_real":
            env_api_key = os.getenv("OPENROUTER_API_KEY")
            if env_api_key:
                settings.OPENROUTER_API_KEY = env_api_key
                logger.info("Loaded OPENROUTER_API_KEY from environment variable for judge test.")
            else:
                logger.error("OPENROUTER_API_KEY is not set. Cannot run main_test_judge with API calls.")
                return
    except Exception as e:
        logger.error(f"Failed to initialize Settings for judge test (OPENROUTER_API_KEY missing?): {e}")
        return

    client = RouterClient(settings)
    judge_template_content = ""
    try:
        judge_template_content = load_judge_prompt_template(str(dummy_judge_file))
    except Exception:
        logger.error("Failed to load judge prompt template. Aborting test.")
        await client.close()
        return

    sample_summary = Summary(gewuenscht="Eine Million in kleinen Scheinen", bekommen="Zwei Melonen mit kleinen Schweinen")
    sample_gen_result = GenerationResult(
        model="test_model_for_judge",
        run=1,
        summary=sample_summary,
        full_response="Die Bank sagte, sie hätten nur noch zwei Melonen, aber immerhin mit kleinen Schweinen drauf!",
        prompt_tokens=10,
        completion_tokens=20, 
        cost_usd=0.0001, # Added cost_usd for GenerationResult initialization
        timestamp=datetime.now(timezone.utc)
    )

    judge_model_under_test = "mistralai/mistral-small-latest"

    logger.info(f"Attempting to judge with model: {judge_model_under_test}")

    try:
        score = await judge_response(
            router_client=client,
            generation_result=sample_gen_result,
            judge_model_name=judge_model_under_test,
            judge_prompt_template=judge_template_content,
            temperature=0.0 
        )
        if score:
            print("\n--- Judge Score ---")
            print(score.model_dump_json(indent=2))
            if score.flags:
                print(f"Flags set during validation: {score.flags}")
        else:
            print("Judging failed, was skipped, or returned no valid score.")

        print("\n--- Testing Clamping Logic (manual data) ---")
        manual_score_data_extreme = {
            "phonetische_aehnlichkeit": 50, 
            "anzueglichkeit": -10, 
            "logik": 20,
            "kreativitaet": 25, 
            "gesamt": 120, 
            "begruendung": {"test": "extreme values"},
            "flags": [] 
        }
        try:
            clamped_score = JudgeScore(**manual_score_data_extreme)
            print("Clamped Score (manual data):")
            print(clamped_score.model_dump_json(indent=2))
        except ValidationError as ve:
             print(f"ValidationError during manual clamping test: {ve}")

    except Exception as e:
        logger.error(f"An error occurred during the main_test_judge: {e}", exc_info=True)
    finally:
        logger.info("Closing router client (judge test)...")
        await client.close()
        logger.info("Router client closed (judge test).")

if __name__ == "__main__":
    asyncio.run(main_test_judge())