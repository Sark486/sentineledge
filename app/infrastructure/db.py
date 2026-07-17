from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=0,
    echo=False
)

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)

async def get_db_session():
    async with async_session_maker() as session:
        yield session
