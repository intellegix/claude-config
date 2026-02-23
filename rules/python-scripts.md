---
paths:
  - "**/*.py"
  - src/**/*.py
  - app/**/*.py
  - scripts/**/*.py
---

# Python Development Rules

These rules apply when working on Python files.

## Type Annotations

**ALWAYS** include type hints on all functions:

```python
# ✅ Correct
def process_data(input_data: dict[str, Any], limit: int = 100) -> list[ProcessedItem]:
    ...

# ❌ Incorrect - missing type hints
def process_data(input_data, limit=100):
    ...
```

## Import Organization

Follow this order (isort compatible):
1. Standard library imports
2. Third-party imports
3. Local imports

```python
# Standard library
import os
from datetime import datetime
from typing import Optional, List

# Third-party
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel

# Local
from src.models import Project
from src.utils import format_currency
```

## Error Handling

Use the Result pattern for operations that can fail:

```python
from dataclasses import dataclass
from typing import TypeVar, Generic, Optional

T = TypeVar('T')

@dataclass
class Result(Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None

# Usage
def get_user(user_id: str) -> Result[User]:
    try:
        user = db.query(User).get(user_id)
        if not user:
            return Result(success=False, error="User not found")
        return Result(success=True, data=user)
    except Exception as e:
        logger.exception("Failed to get user")
        return Result(success=False, error=str(e))
```

## Logging

Use logging, not print:

```python
import logging

logger = logging.getLogger(__name__)

# ✅ Correct
logger.info("Processing started", extra={"count": len(items)})
logger.error("Failed to process", exc_info=True)

# ❌ Incorrect
print("Processing started")
print(f"Error: {e}")
```

## Environment Variables

Never hardcode secrets:

```python
import os

# ✅ Correct
API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY environment variable required")

# ❌ Incorrect
API_KEY = "sk-1234567890abcdef"
```

## Async/Await

Use async for I/O operations:

```python
# ✅ Correct for I/O-bound operations
async def fetch_data(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# ❌ Synchronous I/O blocks the event loop
def fetch_data(url: str) -> dict:
    return requests.get(url).json()
```

## Docstrings

Add docstrings to public functions:

```python
def calculate_profit_margin(revenue: float, costs: float) -> float:
    """Calculate gross profit margin.

    Args:
        revenue: Total revenue in dollars
        costs: Total direct costs in dollars

    Returns:
        Profit margin as a decimal (0.25 = 25%)

    Raises:
        ValueError: If revenue is zero or negative
    """
    if revenue <= 0:
        raise ValueError("Revenue must be positive")
    return (revenue - costs) / revenue
```

## Testing

Follow Arrange-Act-Assert pattern:

```python
def test_calculate_profit_margin_returns_correct_value():
    # Arrange
    revenue = 100000
    costs = 75000

    # Act
    result = calculate_profit_margin(revenue, costs)

    # Assert
    assert result == 0.25
```

## Security

- Never use `eval()` or `exec()` on user input
- Use parameterized queries for database operations
- Validate all external input with Pydantic
- Sanitize file paths to prevent path traversal
