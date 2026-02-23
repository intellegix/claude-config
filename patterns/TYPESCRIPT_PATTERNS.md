# TypeScript Patterns Reference

Detailed code patterns for TypeScript/React development. Referenced from main CLAUDE.md.

---

## Result Pattern {#result-pattern}

Type-safe error handling for operations that can fail.

```typescript
// Type definition
type Result<T, E = Error> =
  | { success: true; data: T }
  | { success: false; error: E };

// Helper functions
export const ok = <T>(data: T): Result<T> => ({ success: true, data });
export const fail = <E = Error>(error: E): Result<never, E> => ({ success: false, error });

// Wrapper for async operations
export const safeApiCall = async <T>(
  operation: () => Promise<T>
): Promise<Result<T>> => {
  try {
    const data = await operation();
    return { success: true, data };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error : new Error(String(error))
    };
  }
};

// Usage
const result = await safeApiCall(() => api.getUser(userId));
if (result.success) {
  console.log(result.data.name);
} else {
  console.error(result.error.message);
}
```

---

## Zod Validation {#zod-validation}

Runtime validation with static type inference.

```typescript
import { z } from 'zod';

// Schema definition
export const CreateProjectSchema = z.object({
  name: z.string().min(1).max(255).trim(),
  clientId: z.string().uuid(),
  budget: z.number().positive().optional(),
  startDate: z.string().datetime(),
  tags: z.array(z.string().toLowerCase()).max(10).default([]),
});

// Infer TypeScript type from schema
export type CreateProjectInput = z.infer<typeof CreateProjectSchema>;

// Validation in route handler
export const createProject = async (req: Request, res: Response) => {
  const parsed = CreateProjectSchema.safeParse(req.body);

  if (!parsed.success) {
    return res.status(400).json({
      success: false,
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Invalid input',
        details: parsed.error.flatten(),
      },
    });
  }

  // parsed.data is fully typed
  const project = await projectService.create(parsed.data);
  return res.status(201).json({ success: true, data: project });
};

// Reusable schemas
export const PaginationSchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  sort: z.string().optional(),
  order: z.enum(['asc', 'desc']).default('desc'),
});
```

---

## React Query Patterns {#react-query}

Server state management with TanStack Query.

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Project } from '@/types';

// Query keys factory
export const projectKeys = {
  all: ['projects'] as const,
  lists: () => [...projectKeys.all, 'list'] as const,
  list: (filters: ProjectFilters) => [...projectKeys.lists(), filters] as const,
  details: () => [...projectKeys.all, 'detail'] as const,
  detail: (id: string) => [...projectKeys.details(), id] as const,
};

// Fetch hook
export const useProject = (projectId: string) => {
  return useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => projectService.getById(projectId),
    staleTime: 5 * 60 * 1000, // 5 minutes
    enabled: !!projectId,
  });
};

// List hook with filters
export const useProjects = (filters: ProjectFilters) => {
  return useQuery({
    queryKey: projectKeys.list(filters),
    queryFn: () => projectService.list(filters),
    placeholderData: keepPreviousData, // Keep old data while fetching new
  });
};

// Mutation hook
export const useUpdateProject = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: projectService.update,
    onSuccess: (data) => {
      // Update cache optimistically
      queryClient.setQueryData(projectKeys.detail(data.id), data);
      // Invalidate list queries
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
    },
    onError: (error) => {
      toast.error(`Update failed: ${error.message}`);
    },
  });
};
```

---

## Zustand Store Patterns {#zustand}

Client state management with Zustand.

```typescript
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface DashboardState {
  // State
  selectedProjectId: string | null;
  dateRange: { start: Date; end: Date };
  filters: {
    status: 'all' | 'active' | 'completed';
    sortBy: 'name' | 'date' | 'revenue';
  };

  // Actions
  setSelectedProject: (id: string | null) => void;
  setDateRange: (range: { start: Date; end: Date }) => void;
  updateFilters: (filters: Partial<DashboardState['filters']>) => void;
  reset: () => void;
}

const initialState = {
  selectedProjectId: null,
  dateRange: {
    start: startOfMonth(new Date()),
    end: new Date(),
  },
  filters: {
    status: 'all' as const,
    sortBy: 'name' as const,
  },
};

export const useDashboardStore = create<DashboardState>()(
  devtools(
    persist(
      (set) => ({
        ...initialState,

        setSelectedProject: (id) => set({ selectedProjectId: id }),

        setDateRange: (dateRange) => set({ dateRange }),

        updateFilters: (newFilters) =>
          set((state) => ({
            filters: { ...state.filters, ...newFilters },
          })),

        reset: () => set(initialState),
      }),
      { name: 'dashboard-store' }
    )
  )
);

// Selector usage (prevents unnecessary re-renders)
const selectedId = useDashboardStore((s) => s.selectedProjectId);
const setSelected = useDashboardStore((s) => s.setSelectedProject);
```

---

## Component Structure {#component-structure}

Standard React component organization.

```typescript
// 1. Imports (grouped)
import { useState, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardContent } from '@/components/ui/card';

import type { Project } from '@/types';

// 2. Type definitions
interface ProjectCardProps {
  /** The project to display */
  project: Project;
  /** Called when card is selected */
  onSelect?: (id: string) => void;
  /** Whether this card is selected */
  isSelected?: boolean;
  /** Additional CSS classes */
  className?: string;
}

// 3. Component
export const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  onSelect,
  isSelected = false,
  className,
}) => {
  // 3a. Hooks first (consistent order every render)
  const [isExpanded, setIsExpanded] = useState(false);
  const { data: metrics, isLoading } = useProjectMetrics(project.id);

  // 3b. Derived values
  const profitMargin = useMemo(() => {
    if (!metrics) return null;
    return (metrics.revenue - metrics.costs) / metrics.revenue;
  }, [metrics]);

  // 3c. Callbacks (memoized)
  const handleClick = useCallback(() => {
    onSelect?.(project.id);
  }, [project.id, onSelect]);

  // 3d. Early returns for loading/error
  if (isLoading) {
    return <ProjectCardSkeleton className={className} />;
  }

  // 3e. Main render
  return (
    <Card
      onClick={handleClick}
      className={cn(
        'cursor-pointer transition-shadow hover:shadow-md',
        isSelected && 'ring-2 ring-primary',
        className
      )}
    >
      <CardHeader>
        <h3 className="font-semibold">{project.name}</h3>
        <span className="text-sm text-muted-foreground">{project.status}</span>
      </CardHeader>
      <CardContent>
        {profitMargin !== null && (
          <p>Margin: {(profitMargin * 100).toFixed(1)}%</p>
        )}
      </CardContent>
    </Card>
  );
};
```

---

## API Response Types {#api-types}

Consistent API response typing.

```typescript
// Response envelope
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
  meta?: {
    page?: number;
    limit?: number;
    total?: number;
    hasMore?: boolean;
  };
}

// Type guard
export function isApiError<T>(
  response: ApiResponse<T>
): response is ApiResponse<T> & { success: false; error: NonNullable<ApiResponse<T>['error']> } {
  return !response.success && response.error !== undefined;
}

// Generic fetch wrapper
export async function apiFetch<T>(
  url: string,
  options?: RequestInit
): Promise<ApiResponse<T>> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  const data: ApiResponse<T> = await response.json();

  if (!response.ok && !data.error) {
    return {
      success: false,
      error: {
        code: 'HTTP_ERROR',
        message: `Request failed with status ${response.status}`,
      },
    };
  }

  return data;
}
```
