import pytest
from sqlalchemy import select
from app.db.models import APIKey, SearchLog, CrawlerHealth

@pytest.mark.asyncio
async def test_create_api_key_and_search_log(db_session):
    # Test creating API key
    key = APIKey(
        key_hash="abc123hash",
        client_name="Test Client",
        tier="pro",
        rate_limit_per_min=120,
    )
    db_session.add(key)
    await db_session.commit()
    await db_session.refresh(key)

    assert key.id is not None
    assert key.client_name == "Test Client"
    assert key.is_active is True

    # Test creating search log associated with key
    log = SearchLog(
        api_key_id=key.id,
        category="flight",
        search_params='{"origin": "THR", "dest": "MHD"}',
        providers_called="alibaba,flytoday",
        results_count=15,
        duration_ms=1240.5,
        status_code=200,
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)

    assert log.id is not None
    assert log.api_key_id == key.id
    assert log.duration_ms == 1240.5

    # Test querying
    result = await db_session.execute(select(APIKey).where(APIKey.key_hash == "abc123hash"))
    fetched_key = result.scalar_one()
    assert fetched_key.client_name == "Test Client"

@pytest.mark.asyncio
async def test_crawler_health_model(db_session):
    health = CrawlerHealth(
        provider_name="alibaba",
        service_name="flight",
        is_active=True,
        avg_response_time_ms=850.0,
        failure_count=0,
    )
    db_session.add(health)
    await db_session.commit()
    await db_session.refresh(health)

    assert health.id is not None
    assert health.provider_name == "alibaba"
    assert health.is_active is True
