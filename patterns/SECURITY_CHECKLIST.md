# Security Checklist

Quick reference for security validation. Referenced from main CLAUDE.md.

---

## Pre-Commit Security Check

Run before every commit:

- [ ] No secrets in code (API keys, passwords, tokens)
- [ ] No hardcoded credentials
- [ ] Environment variables used for all sensitive config
- [ ] Input validation on all external data
- [ ] Parameterized queries (no string concatenation in SQL)
- [ ] Proper authentication checks on protected routes
- [ ] Authorization checks (user can access this resource?)
- [ ] No sensitive data in logs
- [ ] HTTPS for all external requests

---

## Credential Management

### Do This
```python
# Load from environment
import os
API_KEY = os.environ["API_KEY"]

# Or use pydantic-settings
from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    api_key: str
    class Config:
        env_file = ".env"
```

### Never Do This
```python
# NEVER hardcode secrets
API_KEY = "sk-1234567890abcdef"  # BAD!
password = "admin123"  # BAD!
```

---

## Input Validation

### Do This
```python
# Pydantic for Python
from pydantic import BaseModel, Field

class UserInput(BaseModel):
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    name: str = Field(..., min_length=1, max_length=100)
```

```typescript
// Zod for TypeScript
const UserSchema = z.object({
  email: z.string().email(),
  name: z.string().min(1).max(100),
});
```

### Never Do This
```python
# NEVER trust raw input
user_id = request.args.get("id")
query = f"SELECT * FROM users WHERE id = {user_id}"  # SQL INJECTION!
```

---

## Database Security

### Do This
```python
# Parameterized queries
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

# ORM (SQLAlchemy)
user = db.query(User).filter(User.id == user_id).first()
```

### Never Do This
```python
# NEVER concatenate SQL
query = f"SELECT * FROM users WHERE id = {user_id}"  # BAD!
```

---

## Authentication Checklist

- [ ] Passwords hashed with bcrypt/argon2 (never plain text, never MD5/SHA1)
- [ ] JWT tokens have expiration
- [ ] Refresh tokens stored securely (httpOnly cookies)
- [ ] Session tokens invalidated on logout
- [ ] Rate limiting on auth endpoints (10 req/min)
- [ ] Account lockout after failed attempts

---

## Authorization Checklist

- [ ] Every route checks authentication
- [ ] Resource ownership verified before access
- [ ] Role-based access control (RBAC) implemented
- [ ] Sensitive actions require re-authentication
- [ ] Admin routes have additional protection

```python
# Example authorization check
@router.get("/projects/{id}")
async def get_project(id: str, user: User = Depends(get_current_user)):
    project = await get_project_by_id(id)
    if project.owner_id != user.id and user.role != "admin":
        raise HTTPException(403, "Access denied")
    return project
```

---

## Logging Security

### Do This
```python
# Log actions, not sensitive data
logger.info("User logged in", extra={"user_id": user.id})
logger.info("Payment processed", extra={"amount": amount, "order_id": order.id})
```

### Never Do This
```python
# NEVER log sensitive data
logger.info(f"Login attempt: {email} / {password}")  # BAD!
logger.info(f"API call with key: {api_key}")  # BAD!
logger.info(f"Credit card: {card_number}")  # BAD!
```

---

## HTTPS/TLS

- [ ] All external API calls use HTTPS
- [ ] TLS 1.2+ required (prefer 1.3)
- [ ] Certificate validation enabled
- [ ] HSTS header set in production

```python
# Force HTTPS in requests
response = requests.get("https://api.example.com", verify=True)
```

---

## File Upload Security

- [ ] Validate file type (don't trust extension)
- [ ] Limit file size
- [ ] Scan for malware if possible
- [ ] Store outside web root
- [ ] Generate random filenames

```python
ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB

async def validate_upload(file: UploadFile):
    if file.content_type not in ALLOWED_TYPES:
        raise ValueError("Invalid file type")
    if file.size > MAX_SIZE:
        raise ValueError("File too large")
```

---

## Quick Commands

```bash
# Check for secrets in git history
git secrets --scan

# Audit Python dependencies
pip-audit

# Audit npm dependencies
npm audit

# Check for hardcoded secrets
grep -r "password\|secret\|api_key" --include="*.py" --include="*.ts" .
```
