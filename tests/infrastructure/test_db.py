"""The session dependency and declarative base.

Nothing here opens a connection: `async_sessionmaker` builds a session lazily
and the engine only dials out on first execute.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import QueuePool

from app.infrastructure.db import Base, async_session_maker, engine, get_db_session
from app.infrastructure.models import ClimateReading, Device, Location


async def test_get_db_session_yields_a_session():
    agen = get_db_session()
    session = await anext(agen)

    assert isinstance(session, AsyncSession)

    await agen.aclose()


async def test_get_db_session_closes_the_session_afterwards():
    agen = get_db_session()
    session = await anext(agen)

    await agen.aclose()

    assert not session.is_active or not session.in_transaction()


async def test_each_request_gets_its_own_session():
    first_gen, second_gen = get_db_session(), get_db_session()
    first, second = await anext(first_gen), await anext(second_gen)

    assert first is not second

    await first_gen.aclose()
    await second_gen.aclose()


def test_sessions_survive_commit_for_response_serialisation():
    """`expire_on_commit=False` is what lets a router serialise a committed ORM
    object without triggering lazy IO on an async session."""
    assert async_session_maker.kw["expire_on_commit"] is False


def test_the_engine_is_configured_for_asyncpg():
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "asyncpg"


def test_the_pool_does_not_overflow():
    """max_overflow=0 keeps the Pi from opening unbounded connections under load."""
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.size() == 20
    assert pool._max_overflow == 0


def test_every_model_is_registered_on_the_declarative_base():
    tables = set(Base.metadata.tables)

    assert {"devices", "locations", "climate_readings"} <= tables


def test_the_continuous_aggregates_are_excluded_from_autogenerate():
    """They are materialized views created by raw SQL in migrations, so Alembic
    must never propose CREATE/DROP TABLE for them."""
    for name in ("climate_5m", "climate_1h"):
        assert Base.metadata.tables[name].info["skip_autogenerate"] is True


def test_climate_readings_has_the_hypertable_composite_key():
    pk = {column.name for column in ClimateReading.__table__.primary_key}

    assert pk == {"id", "timestamp"}


def test_the_aggregate_views_alias_bucket_as_timestamp():
    from app.infrastructure.models import Climate1hView, Climate5mView

    for view in (Climate5mView, Climate1hView):
        assert "bucket" in view.__table__.c
        assert view.timestamp.expression.name == "bucket"
        assert view.timestamp.key == "timestamp"


def test_device_and_reading_are_related_in_both_directions():
    assert ClimateReading.device.property.back_populates == "readings"
    assert Device.readings.property.back_populates == "device"


def test_device_and_location_are_related_in_both_directions():
    assert Device.location.property.back_populates == "devices"
    assert Location.devices.property.back_populates == "location"
