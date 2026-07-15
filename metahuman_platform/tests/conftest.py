import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

from server import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@asynccontextmanager
async def app_client():
    lifespan = app.router.lifespan_context(app)
    await lifespan.__aenter__()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        await lifespan.__aexit__(None, None, None)
