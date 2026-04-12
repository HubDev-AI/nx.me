import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { THEME } from '../../constants/theme';
import type { AppError, FaceErrorZone } from '../../lib/errors';

interface FaceErrorCardProps {
  error: Extract<AppError, { kind: 'faceAnalysis' }>;
  onTryAgain: () => void;
}

export function FaceErrorCard({ error, onTryAgain }: FaceErrorCardProps) {
  return (
    <View style={styles.card} accessibilityRole="alert">
      <View style={styles.iconRow}>
        <FaceDiagram highlightedZone={error.zone} />
      </View>
      <Text style={styles.title}>{error.message}</Text>
      {error.reason ? <Text style={styles.reason}>{error.reason}</Text> : null}
      <Pressable
        onPress={onTryAgain}
        style={styles.button}
        accessibilityRole="button"
        accessibilityLabel="Try a different photo"
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <Text style={styles.buttonText}>Try a different photo</Text>
      </Pressable>
    </View>
  );
}

function FaceDiagram({ highlightedZone }: { highlightedZone?: FaceErrorZone }) {
  const isHighlighted = highlightedZone !== undefined;
  const color = isHighlighted ? THEME.colors.destructive : THEME.colors.textMuted;
  return (
    <View style={styles.diagram}>
      <Ionicons name="person-circle-outline" size={80} color={color} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: THEME.spacing.lg,
    borderRadius: THEME.radius.lg,
    backgroundColor: THEME.colors.surfaceElevated,
    gap: THEME.spacing.md,
    alignItems: 'center',
  },
  iconRow: {
    alignItems: 'center',
  },
  diagram: {
    alignItems: 'center',
  },
  title: {
    ...THEME.typography.heading,
    color: THEME.colors.textPrimary,
    textAlign: 'center',
  },
  reason: {
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    textAlign: 'center',
  },
  button: {
    marginTop: THEME.spacing.sm,
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.xxl,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.textPrimary,
  },
  buttonText: {
    ...THEME.typography.body,
    color: THEME.colors.bg,
    fontWeight: '600',
  },
});
