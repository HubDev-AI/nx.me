import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { THEME } from '../../constants/theme';
import { LoadingSkeleton } from './LoadingSkeleton';
import type { AppError } from '../../lib/errors';

interface ErrorAction {
  label: string;
  onPress: () => void;
}

interface QueryStateViewProps {
  isLoading: boolean;
  isEmpty?: boolean;
  error: AppError | null;
  onRetry?: () => void;
  skeleton?: React.ReactNode;
  emptyMessage?: string;
  emptyAction?: { label: string; onPress: () => void };
  /**
   * Extra action shown in the error state. Pair with non-retryable
   * errors (notFound, permission, auth) so the user is never stranded
   * on a screen with only a "Try again" button that won't help. When
   * the error IS retryable, `errorAction` renders as a secondary
   * option next to Retry.
   */
  errorAction?: ErrorAction;
  children: React.ReactNode;
}

export function QueryStateView({
  isLoading,
  isEmpty = false,
  error,
  onRetry,
  skeleton,
  emptyMessage = 'Nothing here yet.',
  emptyAction,
  errorAction,
  children,
}: QueryStateViewProps) {
  if (isLoading) {
    return <View style={styles.container}>{skeleton ?? <DefaultSkeleton />}</View>;
  }

  if (error) {
    return <ErrorState error={error} onRetry={onRetry} errorAction={errorAction} />;
  }

  if (isEmpty) {
    return <EmptyState message={emptyMessage} action={emptyAction} />;
  }

  return <>{children}</>;
}

function DefaultSkeleton() {
  return (
    <View style={{ gap: THEME.spacing.md, padding: THEME.spacing.lg }}>
      <LoadingSkeleton height={24} width="60%" />
      <LoadingSkeleton height={120} />
      <LoadingSkeleton height={16} />
      <LoadingSkeleton height={16} width="80%" />
    </View>
  );
}

function ErrorState({
  error,
  onRetry,
  errorAction,
}: {
  error: AppError;
  onRetry?: () => void;
  errorAction?: ErrorAction;
}) {
  const canRetry = onRetry !== undefined && isRetryable(error.kind);
  return (
    <View style={styles.stateContainer} accessibilityRole="alert">
      <View style={styles.iconCircle}>
        <Ionicons name={iconForError(error.kind)} size={32} color={THEME.colors.textSecondary} />
      </View>
      <Text style={styles.title}>{titleForError(error.kind)}</Text>
      <Text style={styles.message}>{error.message}</Text>
      {canRetry && (
        <Pressable
          onPress={onRetry}
          style={styles.button}
          accessibilityRole="button"
          accessibilityLabel="Try again"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Text style={styles.buttonText}>Try again</Text>
        </Pressable>
      )}
      {errorAction && (
        <Pressable
          onPress={errorAction.onPress}
          style={canRetry ? styles.buttonSecondary : styles.button}
          accessibilityRole="button"
          accessibilityLabel={errorAction.label}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Text style={canRetry ? styles.buttonSecondaryText : styles.buttonText}>
            {errorAction.label}
          </Text>
        </Pressable>
      )}
    </View>
  );
}

function EmptyState({
  message,
  action,
}: {
  message: string;
  action?: { label: string; onPress: () => void };
}) {
  return (
    <View style={styles.stateContainer}>
      <View style={styles.iconCircle}>
        <Ionicons name="sparkles-outline" size={32} color={THEME.colors.textSecondary} />
      </View>
      <Text style={styles.message}>{message}</Text>
      {action && (
        <Pressable
          onPress={action.onPress}
          style={styles.button}
          accessibilityRole="button"
          accessibilityLabel={action.label}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Text style={styles.buttonText}>{action.label}</Text>
        </Pressable>
      )}
    </View>
  );
}

function isRetryable(kind: AppError['kind']): boolean {
  return ['network', 'server', 'unknown', 'rateLimit'].includes(kind);
}

function iconForError(kind: AppError['kind']): React.ComponentProps<typeof Ionicons>['name'] {
  switch (kind) {
    case 'network':
      return 'cloud-offline-outline';
    case 'notFound':
      return 'search-outline';
    case 'permission':
    case 'auth':
      return 'lock-closed-outline';
    case 'rateLimit':
      return 'hourglass-outline';
    default:
      return 'alert-circle-outline';
  }
}

function titleForError(kind: AppError['kind']): string {
  switch (kind) {
    case 'network':
      return "Can't reach the internet";
    case 'server':
      return 'Our server hiccupped';
    case 'notFound':
      return 'Not found';
    case 'permission':
      return 'No access';
    case 'auth':
      return 'Signed out';
    case 'rateLimit':
      return 'Slow down';
    case 'validation':
      return 'Check your input';
    default:
      return 'Something went wrong';
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  stateContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: THEME.spacing.xxl,
    gap: THEME.spacing.md,
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: THEME.colors.surfaceElevated,
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    ...THEME.typography.heading,
    color: THEME.colors.textPrimary,
    textAlign: 'center',
  },
  message: {
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    textAlign: 'center',
    maxWidth: 280,
  },
  button: {
    marginTop: THEME.spacing.md,
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.xxl,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.surfaceElevated,
  },
  buttonText: {
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
    fontWeight: '600',
  },
  buttonSecondary: {
    marginTop: THEME.spacing.sm,
    paddingVertical: THEME.spacing.sm,
    paddingHorizontal: THEME.spacing.xl,
  },
  buttonSecondaryText: {
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    fontWeight: '500',
  },
});
