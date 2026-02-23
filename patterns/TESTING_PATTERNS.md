# Testing Patterns Reference

Detailed patterns for writing tests. Referenced from main CLAUDE.md.

---

## Arrange-Act-Assert Pattern {#aaa-pattern}

Every test should have three clear sections.

### Python

```python
import pytest
from src.services import calculate_profit_margin
from tests.factories import create_mock_project

def test_calculate_profit_margin_returns_positive_for_profitable():
    # Arrange
    project = create_mock_project(revenue=100000, costs=75000)

    # Act
    result = calculate_profit_margin(project)

    # Assert
    assert result == 0.25

def test_calculate_profit_margin_returns_negative_for_loss():
    # Arrange
    project = create_mock_project(revenue=50000, costs=75000)

    # Act
    result = calculate_profit_margin(project)

    # Assert
    assert result == -0.5

def test_calculate_profit_margin_raises_for_zero_revenue():
    # Arrange
    project = create_mock_project(revenue=0, costs=1000)

    # Act & Assert
    with pytest.raises(ValueError, match="Revenue must be positive"):
        calculate_profit_margin(project)
```

### TypeScript

```typescript
import { calculateProfitMargin } from '../profit';
import { createMockProject } from '../../tests/factories';

describe('calculateProfitMargin', () => {
  it('returns positive margin for profitable projects', () => {
    // Arrange
    const project = createMockProject({ revenue: 100000, costs: 75000 });

    // Act
    const result = calculateProfitMargin(project);

    // Assert
    expect(result).toBe(0.25);
  });

  it('returns negative margin for loss projects', () => {
    // Arrange
    const project = createMockProject({ revenue: 50000, costs: 75000 });

    // Act
    const result = calculateProfitMargin(project);

    // Assert
    expect(result).toBe(-0.5);
  });

  it('throws for zero revenue', () => {
    // Arrange
    const project = createMockProject({ revenue: 0, costs: 1000 });

    // Act & Assert
    expect(() => calculateProfitMargin(project)).toThrow('Revenue must be positive');
  });
});
```

---

## Mocking External Services {#mocking}

Mock external services, not internal modules.

### Python with pytest-mock

```python
import pytest
from unittest.mock import AsyncMock
from src.services import ProjectSyncService
from tests.factories import create_mock_project

@pytest.fixture
def mock_procore(mocker):
    """Mock Procore API client."""
    mock = mocker.patch('src.services.sync.procore_client')
    mock.get_projects = AsyncMock(return_value=[])
    mock.get_budgets = AsyncMock(return_value={'items': [], 'total': 0})
    return mock

@pytest.mark.asyncio
async def test_sync_projects_fetches_from_procore(mock_procore):
    # Arrange
    mock_procore.get_projects.return_value = [
        create_mock_project(name="Project A"),
        create_mock_project(name="Project B"),
    ]
    service = ProjectSyncService()

    # Act
    result = await service.sync_all()

    # Assert
    assert len(result) == 2
    mock_procore.get_projects.assert_called_once()

@pytest.mark.asyncio
async def test_sync_handles_api_error(mock_procore):
    # Arrange
    mock_procore.get_projects.side_effect = Exception("API rate limited")
    service = ProjectSyncService()

    # Act
    result = await service.sync_all()

    # Assert
    assert result.success is False
    assert "rate limited" in result.error.lower()
```

### TypeScript with Jest

```typescript
import { projectService } from '../project-service';
import { procoreClient } from '../procore-client';

jest.mock('../procore-client');
const mockProcoreClient = procoreClient as jest.Mocked<typeof procoreClient>;

describe('ProjectService.sync', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches projects from Procore', async () => {
    // Arrange
    mockProcoreClient.getProjects.mockResolvedValue([
      createMockProject({ name: 'Project A' }),
      createMockProject({ name: 'Project B' }),
    ]);

    // Act
    const result = await projectService.sync();

    // Assert
    expect(result).toHaveLength(2);
    expect(mockProcoreClient.getProjects).toHaveBeenCalledTimes(1);
  });

  it('handles API errors gracefully', async () => {
    // Arrange
    mockProcoreClient.getProjects.mockRejectedValue(new Error('Rate limited'));

    // Act
    const result = await projectService.sync();

    // Assert
    expect(result.success).toBe(false);
    expect(result.error).toContain('Rate limited');
  });
});
```

---

## React Component Testing {#component-testing}

Test components with React Testing Library.

```typescript
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ProjectCard } from '../ProjectCard';
import { createMockProject } from '../../tests/factories';

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('ProjectCard', () => {
  it('renders project name and status', () => {
    // Arrange
    const project = createMockProject({ name: 'Test Project', status: 'active' });

    // Act
    render(<ProjectCard project={project} />, { wrapper: createWrapper() });

    // Assert
    expect(screen.getByText('Test Project')).toBeInTheDocument();
    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('calls onSelect when clicked', async () => {
    // Arrange
    const onSelect = jest.fn();
    const project = createMockProject({ id: '123' });
    const user = userEvent.setup();

    // Act
    render(<ProjectCard project={project} onSelect={onSelect} />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('article'));

    // Assert
    expect(onSelect).toHaveBeenCalledWith('123');
  });

  it('shows loading skeleton while fetching', () => {
    // Arrange
    const project = createMockProject();

    // Act
    render(<ProjectCard project={project} isLoading />, {
      wrapper: createWrapper(),
    });

    // Assert
    expect(screen.getByTestId('skeleton')).toBeInTheDocument();
  });
});
```

---

## API Integration Testing {#api-testing}

Test API endpoints end-to-end.

```python
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_create_project_success():
    # Arrange
    payload = {
        "name": "Test Project",
        "client_id": "550e8400-e29b-41d4-a716-446655440000",
        "budget": 100000,
    }

    # Act
    response = client.post(
        "/api/v1/projects",
        json=payload,
        headers={"Authorization": "Bearer valid-test-token"},
    )

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["name"] == "Test Project"

def test_create_project_validation_error():
    # Arrange
    payload = {"name": "", "client_id": "not-a-uuid"}

    # Act
    response = client.post(
        "/api/v1/projects",
        json=payload,
        headers={"Authorization": "Bearer valid-test-token"},
    )

    # Assert
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"

def test_create_project_unauthorized():
    # Act
    response = client.post("/api/v1/projects", json={"name": "Test"})

    # Assert
    assert response.status_code == 401
```
