import pytest
from pytest_httpx import HTTPXMock

from src.config import Settings
from src.router_client import BudgetExceededError, RouterClient


@pytest.mark.asyncio
async def test_chat_success(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://openrouter.ai/api/v1/chat/completions",
        json={
            "choices": [{"message": {"content": "Hallo"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        headers={"x-openrouter-price": "0.01"},
    )
    settings = Settings(OPENROUTER_API_KEY="test-key")
    client = RouterClient(settings)
    response = await client.chat(model="test/model", prompt="hi", temperature=0.5)
    await client.close()
    assert response["text"] == "Hallo"
    assert response["prompt_tokens"] == 10
    assert pytest.approx(response["cost_usd"], rel=1e-5) == 0.00015
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_chat_budget_guard(httpx_mock: HTTPXMock) -> None:
    settings = Settings(OPENROUTER_API_KEY="test-key", budget={"max_budget_usd": 0.0})
    client = RouterClient(settings)
    with pytest.raises(BudgetExceededError):
        await client.chat(model="test/model", prompt="hi", temperature=0.5)
    await client.close()
    assert len(httpx_mock.get_requests()) == 0


@pytest.mark.asyncio
async def test_chat_budget_exceeded_after_request(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://openrouter.ai/api/v1/chat/completions",
        json={
            "choices": [{"message": {"content": "Hallo"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 0},
        },
        headers={"x-openrouter-price": "0.10"},
    )

    settings = Settings(
        OPENROUTER_API_KEY="test-key", budget={"max_budget_usd": 0.05, "warn_at_fraction": 0.5}
    )
    client = RouterClient(settings)

    with pytest.raises(BudgetExceededError):
        await client.chat(model="test/model", prompt="hi", temperature=0.5)

    await client.close()
    assert len(httpx_mock.get_requests()) == 1
    assert client.cumulative_cost_usd > settings.budget.max_budget_usd
