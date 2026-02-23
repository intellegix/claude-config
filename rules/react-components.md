---
paths:
  - src/components/**/*.tsx
  - src/components/**/*.jsx
  - src/features/**/*.tsx
  - src/features/**/*.jsx
  - app/components/**/*.tsx
  - components/**/*.tsx
---

# React Component Development Rules

These rules apply when working on React components.

## Component Structure

Follow this order within components:

```typescript
// 1. Imports (grouped)
import { useState, useCallback, useMemo, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

import type { Project } from '@/types';

// 2. Type Definitions
interface ProjectCardProps {
  /** The project to display */
  project: Project;
  /** Called when the card is clicked */
  onSelect?: (id: string) => void;
  /** Whether this card is currently selected */
  isSelected?: boolean;
  /** Additional CSS classes */
  className?: string;
}

// 3. Component Definition
export const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  onSelect,
  isSelected = false,
  className,
}) => {
  // 3a. Hooks (always at the top, same order every render)
  const [isExpanded, setIsExpanded] = useState(false);
  const { data: metrics, isLoading } = useProjectMetrics(project.id);

  // 3b. Derived/computed values
  const profitMargin = useMemo(() => {
    if (!metrics) return null;
    return (metrics.revenue - metrics.costs) / metrics.revenue;
  }, [metrics]);

  // 3c. Callbacks
  const handleClick = useCallback(() => {
    onSelect?.(project.id);
  }, [project.id, onSelect]);

  const handleExpand = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setIsExpanded(prev => !prev);
  }, []);

  // 3d. Effects
  useEffect(() => {
    // Side effects here
  }, [dependency]);

  // 3e. Early returns for loading/error states
  if (isLoading) {
    return <ProjectCardSkeleton />;
  }

  // 3f. Main render
  return (
    <Card
      onClick={handleClick}
      className={cn(
        'cursor-pointer transition-shadow hover:shadow-md',
        isSelected && 'ring-2 ring-primary',
        className
      )}
    >
      {/* Component content */}
    </Card>
  );
};
```

## Typing Props

Use interfaces with JSDoc comments:

```typescript
interface ButtonProps {
  /** Button variant determines visual style */
  variant?: 'primary' | 'secondary' | 'destructive';
  /** Size of the button */
  size?: 'sm' | 'md' | 'lg';
  /** Loading state disables button and shows spinner */
  isLoading?: boolean;
  /** Content to display in the button */
  children: React.ReactNode;
  /** Click handler */
  onClick?: () => void;
}
```

## State Management

Choose the right tool:

```typescript
// Local UI state - useState
const [isOpen, setIsOpen] = useState(false);

// Server state - React Query
const { data, isLoading, error } = useQuery({
  queryKey: ['projects', projectId],
  queryFn: () => fetchProject(projectId),
  staleTime: 5 * 60 * 1000, // 5 minutes
});

// Global client state - Zustand
const selectedProject = useDashboardStore((s) => s.selectedProjectId);
const setSelectedProject = useDashboardStore((s) => s.setSelectedProject);

// Form state - React Hook Form
const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
  resolver: zodResolver(formSchema),
});
```

## Styling with Tailwind

Use the `cn()` utility for conditional classes:

```typescript
import { cn } from '@/lib/utils';

// ✅ Correct
<div className={cn(
  'rounded-lg border bg-card p-4',
  isActive && 'ring-2 ring-primary',
  isError && 'border-destructive',
  className
)}>

// ❌ Avoid inline styles
<div style={{ backgroundColor: isActive ? 'blue' : 'gray' }}>
```

## Performance Optimization

```typescript
// Memoize expensive computations
const sortedItems = useMemo(() => {
  return [...items].sort((a, b) => a.name.localeCompare(b.name));
}, [items]);

// Memoize callbacks passed to children
const handleItemClick = useCallback((id: string) => {
  onSelect(id);
}, [onSelect]);

// Use React.memo sparingly - only when measurably needed
export const ExpensiveList = React.memo(({ items }: Props) => {
  // ...
});
```

## Data Fetching Hooks

Create custom hooks for data fetching:

```typescript
// hooks/useProject.ts
export const useProject = (projectId: string) => {
  return useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectService.getById(projectId),
    staleTime: 5 * 60 * 1000,
    enabled: !!projectId,
  });
};

export const useUpdateProject = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: projectService.update,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['project', data.id] });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });
};
```

## Error Handling

Handle loading, error, and empty states:

```typescript
const { data, isLoading, error } = useProjects();

if (isLoading) {
  return <ProjectListSkeleton />;
}

if (error) {
  return (
    <Alert variant="destructive">
      <AlertTitle>Error loading projects</AlertTitle>
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  );
}

if (!data?.length) {
  return <EmptyState message="No projects found" />;
}

return <ProjectList projects={data} />;
```

## Accessibility

Follow a11y best practices:

```typescript
// ✅ Correct
<button
  onClick={handleClick}
  aria-label="Close modal"
  aria-pressed={isActive}
>
  <XIcon aria-hidden="true" />
</button>

// Use semantic HTML
<nav aria-label="Main navigation">
<main>
<article>
<aside>
```

## Testing

Co-locate tests with components:

```
components/
  ProjectCard/
    ProjectCard.tsx
    ProjectCard.test.tsx
    index.ts
```

Required tests:
- Renders without crashing
- Displays correct content
- Handles user interactions
- Handles loading/error states
