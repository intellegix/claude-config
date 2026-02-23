---
paths:
  - src/api/**/*.py
  - src/api/**/*.ts
  - src/routes/**/*.py
  - src/routes/**/*.ts
  - app/api/**/*.py
  - app/api/**/*.ts
---

# API Route Development Rules

These rules apply when working on API endpoints.

## Required Structure (FastAPI)

```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List

from src.auth import get_current_user
from src.models import User
from src.services import resource_service

router = APIRouter(prefix="/api/v1/resources", tags=["resources"])

# Request/Response Models
class CreateResourceRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)

class ResourceResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# Endpoints
@router.get("/", response_model=List[ResourceResponse])
async def list_resources(
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List all resources for the current user."""
    return await resource_service.find_all(
        user_id=current_user.id,
        page=page,
        limit=limit
    )
```

## Required Structure (Express/TypeScript)

```typescript
import { Router, Request, Response } from 'express';
import { z } from 'zod';
import { authenticate, authorize } from '@/middleware/auth';
import { validate } from '@/middleware/validation';
import { resourceService } from '@/services/resource';
import { createSuccessResponse, createErrorResponse } from '@/lib/api-response';

const router = Router();

// Validation Schemas
const CreateResourceSchema = z.object({
  name: z.string().min(1).max(255),
  description: z.string().max(1000).optional(),
});

// Endpoints
router.get('/',
  authenticate,
  async (req: Request, res: Response) => {
    const result = await resourceService.findAll(req.query);
    return res.json(createSuccessResponse(result.data, result.meta));
  }
);

router.post('/',
  authenticate,
  authorize(['admin', 'manager']),
  validate(CreateResourceSchema),
  async (req: Request, res: Response) => {
    const result = await resourceService.create(req.body);
    return res.status(201).json(createSuccessResponse(result));
  }
);

export { router as resourceRouter };
```

## Response Format

**ALWAYS** use the standard envelope:

```json
// Success
{
  "success": true,
  "data": { ... },
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 100,
    "has_more": true
  }
}

// Error
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message",
    "details": { "field": "name", "issue": "required" }
  }
}
```

## HTTP Status Codes

| Code | When to Use |
|------|-------------|
| 200 | Success (GET, PATCH, PUT) |
| 201 | Resource created (POST) |
| 204 | Success with no body (DELETE) |
| 400 | Validation error, bad request |
| 401 | Missing or invalid auth token |
| 403 | Valid auth but insufficient permissions |
| 404 | Resource not found |
| 409 | Conflict (duplicate, state conflict) |
| 422 | Unprocessable entity |
| 429 | Rate limited |
| 500 | Internal server error |
| 502 | Upstream service failure |

## Input Validation

**ALWAYS** validate all input:

```python
# Python - Pydantic
class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    client_id: str = Field(..., pattern=r'^[a-f0-9-]{36}$')  # UUID
    budget: float = Field(None, gt=0)

    @field_validator('name')
    def sanitize_name(cls, v):
        return v.strip()
```

```typescript
// TypeScript - Zod
const CreateProjectSchema = z.object({
  name: z.string().min(1).max(255).trim(),
  clientId: z.string().uuid(),
  budget: z.number().positive().optional(),
});
```

## Error Handling

Catch and format errors consistently:

```python
@router.get("/{resource_id}")
async def get_resource(resource_id: str, current_user: User = Depends(get_current_user)):
    result = await resource_service.get_by_id(resource_id)

    if not result.success:
        if result.error_code == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(status_code=500, detail=result.error)

    return result.data
```

## Authentication & Authorization

Every protected route must:
1. Verify authentication (valid token)
2. Check authorization (correct permissions)
3. Scope data to authorized resources

```python
@router.delete("/{resource_id}")
async def delete_resource(
    resource_id: str,
    current_user: User = Depends(get_current_user),
):
    # Check ownership or admin
    resource = await resource_service.get_by_id(resource_id)
    if resource.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    await resource_service.delete(resource_id)
    return Response(status_code=204)
```

## Audit Logging

Log all data mutations:

```python
from src.audit import audit_log

@router.post("/")
async def create_resource(
    request: CreateResourceRequest,
    current_user: User = Depends(get_current_user),
):
    result = await resource_service.create(request.dict())

    await audit_log(
        user_id=current_user.id,
        action="create",
        resource="resource",
        resource_id=result.id,
    )

    return result
```

## Testing Requirements

Every route must have tests for:
- [ ] Happy path (200/201 response)
- [ ] Validation errors (400 response)
- [ ] Authentication (401 if missing token)
- [ ] Authorization (403 if insufficient permissions)
- [ ] Not found (404 where applicable)
