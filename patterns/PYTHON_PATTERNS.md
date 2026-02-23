# Python Patterns Reference

Detailed code patterns for Python development. Referenced from main CLAUDE.md.

---

## Result Pattern {#result-pattern}

Use for operations that can fail. Provides type-safe error handling.

```python
from dataclasses import dataclass
from typing import TypeVar, Generic, Optional

T = TypeVar('T')

@dataclass
class Result(Generic[T]):
    """Type-safe result wrapper for operations that can fail."""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

    @classmethod
    def ok(cls, data: T) -> "Result[T]":
        """Create successful result."""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, code: str = "UNKNOWN") -> "Result[T]":
        """Create failure result."""
        return cls(success=False, error=error, error_code=code)

# Usage Example
def get_project(project_id: str) -> Result[Project]:
    try:
        project = db.query(Project).filter_by(id=project_id).first()
        if not project:
            return Result.fail("Project not found", "NOT_FOUND")
        return Result.ok(project)
    except Exception as e:
        logger.exception("Failed to get project")
        return Result.fail(str(e), "DATABASE_ERROR")

# Consuming Results
result = get_project("123")
if result.success:
    print(f"Found: {result.data.name}")
else:
    print(f"Error [{result.error_code}]: {result.error}")
```

---

## Pydantic Validation {#pydantic-validation}

Use Pydantic for all external input validation.

```python
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime

class CreateProjectRequest(BaseModel):
    """Request model for creating a project."""
    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    client_id: str = Field(..., pattern=r'^[a-f0-9-]{36}$', description="Client UUID")
    budget: Optional[float] = Field(None, gt=0, description="Budget in dollars")
    start_date: datetime = Field(..., description="Project start date")
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator('name')
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """Strip whitespace from name."""
        return v.strip()

    @field_validator('tags')
    @classmethod
    def lowercase_tags(cls, v: list[str]) -> list[str]:
        """Normalize tags to lowercase."""
        return [tag.lower().strip() for tag in v]

    @model_validator(mode='after')
    def validate_dates(self) -> 'CreateProjectRequest':
        """Ensure dates are logical."""
        if hasattr(self, 'end_date') and self.end_date:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be after start_date")
        return self

# Usage in FastAPI
@router.post("/projects")
async def create_project(request: CreateProjectRequest):
    # request is already validated
    return await project_service.create(request.model_dump())
```

---

## Async/Await Patterns {#async-patterns}

Use async for all I/O operations.

```python
import aiohttp
import asyncio
from typing import Any

async def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    """Fetch JSON from URL with timeout."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            response.raise_for_status()
            return await response.json()

async def fetch_multiple(urls: list[str]) -> list[dict]:
    """Fetch multiple URLs concurrently."""
    tasks = [fetch_json(url) for url in urls]
    return await asyncio.gather(*tasks, return_exceptions=True)

# With retry logic
async def fetch_with_retry(
    url: str,
    max_retries: int = 3,
    base_delay: float = 1.0
) -> dict[str, Any]:
    """Fetch with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return await fetch_json(url)
        except aiohttp.ClientError as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay}s: {e}")
            await asyncio.sleep(delay)
```

---

## Logging Configuration {#logging-config}

Structured logging setup for production.

```python
import logging
import sys
from typing import Any

def setup_logging(
    level: str = "INFO",
    json_format: bool = False
) -> logging.Logger:
    """Configure application logging."""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        # JSON format for production
        import json
        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_data = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)
                if hasattr(record, "extra"):
                    log_data.update(record.extra)
                return json.dumps(log_data)
        handler.setFormatter(JsonFormatter())
    else:
        # Human-readable for development
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))

    logger.addHandler(handler)
    return logger

# Usage
logger = logging.getLogger(__name__)
logger.info("Processing started", extra={"record_count": 100, "batch_id": "abc123"})
```

---

## Factory Functions for Tests {#test-factories}

Create consistent test data with factories.

```python
from faker import Faker
from datetime import datetime
from typing import Any

fake = Faker()

def create_mock_project(**overrides: Any) -> Project:
    """Create a mock project with sensible defaults."""
    defaults = {
        "id": fake.uuid4(),
        "name": fake.company(),
        "status": "active",
        "client_id": fake.uuid4(),
        "revenue": fake.random_int(min=10000, max=1000000),
        "costs": fake.random_int(min=5000, max=500000),
        "created_at": fake.past_datetime(),
        "updated_at": datetime.utcnow(),
    }
    return Project(**{**defaults, **overrides})

def create_mock_user(**overrides: Any) -> User:
    """Create a mock user with sensible defaults."""
    defaults = {
        "id": fake.uuid4(),
        "email": fake.email(),
        "name": fake.name(),
        "role": "viewer",
        "is_active": True,
    }
    return User(**{**defaults, **overrides})

# Usage in tests
def test_calculate_profit_margin():
    # Arrange - use factory with specific overrides
    project = create_mock_project(revenue=100000, costs=75000)

    # Act
    result = calculate_profit_margin(project)

    # Assert
    assert result == 0.25
```

---

## Environment Variable Loading {#env-loading}

Safe environment variable access pattern.

```python
import os
from typing import Optional
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings loaded from environment."""
    # Required
    database_url: str
    api_key: str
    jwt_secret: str

    # Optional with defaults
    log_level: str = "INFO"
    debug: bool = False
    max_connections: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

# Simple access for scripts
def get_required_env(key: str) -> str:
    """Get required environment variable or raise."""
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"{key} environment variable required")
    return value

# Usage
settings = get_settings()
print(settings.database_url)
```
