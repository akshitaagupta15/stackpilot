import pytest
from app.ratelimit import limiter


@pytest.fixture(autouse=True)
def _fresh_limiter():
    limiter.reset()
    yield
