from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENROUTER_API_KEY: str
    MAX_BUDGET_USD: float = 100.0
    JUDGE_MODEL_NAME: str = "openai/gpt-4o" # Default judge model
