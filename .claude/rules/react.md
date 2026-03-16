---
alwaysApply: false
globs: ["*.tsx", "*.jsx"]
---
React and JSX/TSX conventions — loaded when working with .tsx or .jsx files.

# React Standards

## Component State Checklist

Every component that fetches data or has async state MUST handle all five states:

```tsx
function UserProfile({ userId }: Props) {
  const { data, error, isLoading } = useUser(userId);

  if (isLoading) return <ProfileSkeleton />;
  if (error) return <ErrorBanner message={error.message} retry={refetch} />;
  if (!data) return <EmptyState message="No user found" />;

  return <ProfileCard user={data} />;
}
```

| State | Must handle | Pattern |
|---|---|---|
| **Loading** | Skeleton or spinner | Prefer skeleton for layout stability |
| **Error** | Error message + retry action | Never show raw error objects to users |
| **Empty** | Empty state with guidance | "No items yet — create your first" |
| **Success** | Render data | The happy path |
| **Disabled** | Visual + interaction lockout | `aria-disabled` + prevent click handlers |

## Design Tokens

- Use CSS variables, theme objects, or Tailwind classes — follow the project's existing convention
- **Never mix approaches** within the same project — pick one and stay consistent
- Use design tokens (`var(--color-primary)`, `var(--spacing-4)`), not hardcoded values

## Accessibility

- Semantic HTML, ARIA labels on interactive elements, keyboard nav, focus management, WCAG AA contrast minimum
