# API Design Patterns Reference

Detailed patterns for REST API development. Referenced from main CLAUDE.md.

---

## Response Envelope {#response-envelope}

All APIs use consistent response structure.

### Python/FastAPI

```python
from pydantic import BaseModel
from typing import TypeVar, Generic, Optional, Dict, Any

T = TypeVar('T')

class ApiMeta(BaseModel):
    """Pagination metadata."""
    page: Optional[int] = None
    limit: Optional[int] = None
    total: Optional[int] = None
    has_more: Optional[bool] = None

class ApiError(BaseModel):
    """Error details."""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

class ApiResponse(BaseModel, Generic[T]):
    """Standard API response envelope."""
    success: bool
    data: Optional[T] = None
    error: Optional[ApiError] = None
    meta: Optional[ApiMeta] = None

# Helper functions
def success_response(data: T, meta: Optional[ApiMeta] = None) -> dict:
    return {"success": True, "data": data, "meta": meta}

def error_response(code: str, message: str, details: dict = None) -> dict:
    return {
        "success": False,
        "error": {"code": code, "message": message, "details": details}
    }
```

### TypeScript/Express

```typescript
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: { code: string; message: string; details?: Record<string, unknown> };
  meta?: { page?: number; limit?: number; total?: number; hasMore?: boolean };
}

export const createSuccessResponse = <T>(data: T, meta?: ApiResponse<T>['meta']) => ({
  success: true,
  data,
  meta,
});

export const createErrorResponse = (code: string, message: string, details?: Record<string, unknown>) => ({
  success: false,
  error: { code, message, details },
});
```

---

## FastAPI Route Template {#fastapi-route}

Standard route structure for FastAPI.

```python
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List

from src.auth import get_current_user, require_roles
from src.models import User, Project
from src.services import project_service
from src.schemas import CreateProjectRequest, UpdateProjectRequest, ProjectResponse

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

@router.get("/", response_model=ApiResponse[List[ProjectResponse]])
async def list_projects(
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
):
    """List all projects for the current user."""
    result = await project_service.find_all(
        user_id=current_user.id,
        page=page,
        limit=limit,
        status=status,
    )
    return success_response(
        data=result.items,
        meta=ApiMeta(page=page, limit=limit, total=result.total, has_more=result.has_more)
    )

@router.get("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a single project by ID."""
    project = await project_service.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return success_response(data=project)

@router.post("/", response_model=ApiResponse[ProjectResponse], status_code=201)
async def create_project(
    request: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new project."""
    project = await project_service.create(
        data=request.model_dump(),
        owner_id=current_user.id,
    )
    await audit_log(user_id=current_user.id, action="create", resource="project", resource_id=project.id)
    return success_response(data=project)

@router.patch("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    current_user: User = Depends(get_current_user),
):
    """Update an existing project."""
    project = await project_service.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    updated = await project_service.update(project_id, request.model_dump(exclude_unset=True))
    return success_response(data=updated)

@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    current_user: User = Depends(require_roles(["admin"])),
):
    """Delete a project (admin only)."""
    await project_service.delete(project_id)
    return None
```

---

## Error Handling Middleware {#error-middleware}

Centralized error handling.

```python
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except HTTPException:
            raise  # Let FastAPI handle HTTP exceptions
        except ValidationError as e:
            return JSONResponse(
                status_code=400,
                content=error_response("VALIDATION_ERROR", str(e), e.errors())
            )
        except PermissionError as e:
            return JSONResponse(
                status_code=403,
                content=error_response("FORBIDDEN", str(e))
            )
        except Exception as e:
            logger.exception("Unhandled error")
            return JSONResponse(
                status_code=500,
                content=error_response("INTERNAL_ERROR", "An unexpected error occurred")
            )
```

---

## HTTP Status Code Reference {#status-codes}

| Code | Name | When to Use |
|------|------|-------------|
| 200 | OK | Successful GET, PATCH, PUT |
| 201 | Created | Successful POST creating resource |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid input, validation failed |
| 401 | Unauthorized | Missing or invalid auth token |
| 403 | Forbidden | Valid auth but insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Resource already exists, state conflict |
| 422 | Unprocessable | Semantically invalid input |
| 429 | Too Many Requests | Rate limited |
| 500 | Internal Error | Unexpected server error |
| 502 | Bad Gateway | Upstream service failure |

---

## Rate Limiting {#rate-limiting}

Implement rate limiting with response headers.

```python
from fastapi import Request, HTTPException
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self, requests_per_minute: int = 100):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)

    async def check(self, request: Request) -> dict:
        client_ip = request.client.host
        now = time.time()
        minute_ago = now - 60

        # Clean old requests
        self.requests[client_ip] = [
            t for t in self.requests[client_ip] if t > minute_ago
        ]

        # Check limit
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(minute_ago + 60)),
                }
            )

        # Record request
        self.requests[client_ip].append(now)

        return {
            "X-RateLimit-Limit": str(self.requests_per_minute),
            "X-RateLimit-Remaining": str(self.requests_per_minute - len(self.requests[client_ip])),
            "X-RateLimit-Reset": str(int(now + 60)),
        }
```
