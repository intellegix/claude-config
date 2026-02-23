---
paths:
  - "**/*.test.ts"
  - "**/*.test.tsx"
  - "**/*.test.py"
  - "**/*.spec.ts"
  - "**/*.spec.tsx"
  - "**/*.spec.py"
  - tests/**/*.ts
  - tests/**/*.py
  - __tests__/**/*.ts
  - __tests__/**/*.tsx
---

# Test Development Rules

These rules apply when working on test files.

## Test Structure

Follow Arrange-Act-Assert pattern:

```typescript
describe('ProjectService', () => {
  // Setup/teardown
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // Group related tests
  describe('calculateProfitability', () => {
    it('returns positive margin for profitable projects', () => {
      // Arrange
      const project = createMockProject({ revenue: 100000, costs: 75000 });

      // Act
      const result = calculateProfitability(project);

      // Assert
      expect(result.margin).toBe(0.25);
      expect(result.status).toBe('profitable');
    });

    it('handles zero revenue gracefully', () => {
      // Arrange
      const project = createMockProject({ revenue: 0, costs: 1000 });

      // Act
      const result = calculateProfitability(project);

      // Assert
      expect(result.margin).toBe(-Infinity);
      expect(result.status).toBe('loss');
    });
  });
});
```

```python
# Python with pytest
class TestProjectService:
    def setup_method(self):
        """Run before each test method."""
        self.service = ProjectService()

    def test_calculate_profitability_returns_positive_margin(self):
        # Arrange
        project = create_mock_project(revenue=100000, costs=75000)

        # Act
        result = self.service.calculate_profitability(project)

        # Assert
        assert result.margin == 0.25
        assert result.status == "profitable"

    def test_calculate_profitability_handles_zero_revenue(self):
        # Arrange
        project = create_mock_project(revenue=0, costs=1000)

        # Act
        result = self.service.calculate_profitability(project)

        # Assert
        assert result.margin == float("-inf")
        assert result.status == "loss"
```

## Naming Conventions

Test names should describe the behavior:

```typescript
// ✅ Good - describes behavior
it('returns empty array when no projects match filter')
it('throws ValidationError when email is invalid')
it('sends notification email after successful registration')

// ❌ Bad - describes implementation
it('calls database.query')
it('uses regex to validate')
it('loops through array')
```

## Factory Functions

Use factories for test data (DRY, type-safe):

```typescript
// tests/factories/project.ts
import { faker } from '@faker-js/faker';
import type { Project } from '@/types';

export const createMockProject = (overrides: Partial<Project> = {}): Project => ({
  id: faker.string.uuid(),
  name: faker.company.name(),
  status: 'active',
  revenue: faker.number.int({ min: 10000, max: 1000000 }),
  costs: faker.number.int({ min: 5000, max: 500000 }),
  createdAt: faker.date.past(),
  updatedAt: faker.date.recent(),
  ...overrides,
});
```

```python
# tests/factories/project.py
from faker import Faker
from src.models import Project

fake = Faker()

def create_mock_project(**overrides) -> Project:
    defaults = {
        "id": fake.uuid4(),
        "name": fake.company(),
        "status": "active",
        "revenue": fake.random_int(min=10000, max=1000000),
        "costs": fake.random_int(min=5000, max=500000),
        "created_at": fake.past_datetime(),
    }
    return Project(**{**defaults, **overrides})
```

## Mocking Guidelines

Mock external services, not internal modules:

```typescript
// ✅ Good - mock external API
jest.mock('@/services/procore-client');
const mockProcoreClient = procoreClient as jest.Mocked<typeof procoreClient>;
mockProcoreClient.getProjects.mockResolvedValue([createMockProject()]);

// ❌ Avoid - mocking internal utilities
jest.mock('@/lib/format-currency'); // Let real implementation run
```

```python
# Python - use pytest-mock or unittest.mock
def test_sync_projects(mocker):
    # Mock external API
    mock_procore = mocker.patch('src.services.procore_client')
    mock_procore.get_projects.return_value = [create_mock_project()]

    result = sync_service.sync_all()

    assert len(result) == 1
    mock_procore.get_projects.assert_called_once()
```

## Async Testing

```typescript
// Jest
it('fetches and returns user data', async () => {
  const user = await userService.getById('123');
  expect(user.name).toBe('Test User');
});

// With waitFor for React components
it('displays data after loading', async () => {
  render(<UserProfile userId="123" />);

  await waitFor(() => {
    expect(screen.getByText('Test User')).toBeInTheDocument();
  });
});
```

```python
# pytest with pytest-asyncio
import pytest

@pytest.mark.asyncio
async def test_fetch_user_data():
    user = await user_service.get_by_id("123")
    assert user.name == "Test User"
```

## Component Testing (React)

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProjectCard } from '../ProjectCard';

describe('ProjectCard', () => {
  it('renders project name and status', () => {
    const project = createMockProject({ name: 'Test Project', status: 'active' });

    render(<ProjectCard project={project} />);

    expect(screen.getByText('Test Project')).toBeInTheDocument();
    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('calls onSelect when clicked', async () => {
    const onSelect = jest.fn();
    const project = createMockProject();

    render(<ProjectCard project={project} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole('article'));

    expect(onSelect).toHaveBeenCalledWith(project.id);
  });

  it('shows loading state while fetching metrics', () => {
    // Mock the hook to return loading state
    jest.spyOn(hooks, 'useProjectMetrics').mockReturnValue({
      data: undefined,
      isLoading: true,
    });

    render(<ProjectCard project={createMockProject()} />);

    expect(screen.getByTestId('skeleton')).toBeInTheDocument();
  });
});
```

## API Testing

```python
# FastAPI with TestClient
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_create_project_returns_201():
    response = client.post(
        "/api/v1/projects",
        json={"name": "Test Project", "client_id": "uuid-here"},
        headers={"Authorization": "Bearer valid-token"}
    )

    assert response.status_code == 201
    assert response.json()["success"] is True
    assert response.json()["data"]["name"] == "Test Project"

def test_create_project_validates_name():
    response = client.post(
        "/api/v1/projects",
        json={"name": "", "client_id": "uuid-here"},  # Empty name
        headers={"Authorization": "Bearer valid-token"}
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
```

## Coverage Requirements

- Minimum 80% line coverage for new code
- 100% coverage for utility functions
- Focus on behavior coverage, not line coverage
- Don't test trivial code (simple getters, pass-through)

## What NOT to Test

- Third-party library internals
- TypeScript types (that's what type-check is for)
- Trivial code (simple getters, constant values)
- Implementation details that could change
- Private functions directly (test through public API)

## Test Isolation

Each test should:
- Run independently (no shared state)
- Clean up after itself
- Not depend on test execution order
- Be idempotent (same result every run)
