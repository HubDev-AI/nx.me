/**
 * First-run consent sheet for AI Makeup biometric processing.
 *
 * Shown before the first analyzeMakeup call. Agreeing triggers the analyze
 * call which creates the consent row (makeup_analyses.consent_version).
 * The sheet records the consent version locally so subsequent sessions
 * don't re-prompt unless the version bumps.
 */
import { Modal, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { MAKEUP_MAKEUP_CONSENT_VERSION } from "../../constants/config";
import { THEME } from "../../constants/theme";
import { Body, Caption, Heading, Label } from "../ui/Text";
import { Button } from "../ui/Button";
const CONSENT_POINTS = [
  "We analyze skin tone and facial features to recommend makeup looks.",
  "This data is stored for up to 90 days, then automatically deleted.",
  "You can delete your data anytime in Settings.",
  "Your photo and analysis data are never sold or shared with advertisers.",
];

interface MakeupConsentSheetProps {
  visible: boolean;
  onAgree: () => void;
  onCancel: () => void;
}

export function MakeupConsentSheet({ visible, onAgree, onCancel }: MakeupConsentSheetProps) {
  const insets = useSafeAreaInsets();

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onCancel}
      statusBarTranslucent
    >
      <View style={styles.scrim}>
        <Pressable style={styles.backdrop} onPress={onCancel} />
        <View
          style={[
            styles.sheet,
            { paddingBottom: insets.bottom + THEME.spacing.xl },
          ]}
        >
          <View style={styles.handle} />

          <View style={styles.header}>
            <View style={styles.iconWrap}>
              <Ionicons name="shield-checkmark-outline" size={28} color={THEME.colors.textSecondary} />
            </View>
            <Heading size="md" style={styles.title}>
              AI Makeup Uses Your Skin Tone
            </Heading>
            <Body color="secondary" style={styles.subtitle}>
              To recommend makeup looks, we need to analyze your facial features.
              Here&rsquo;s what that means:
            </Body>
          </View>

          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            bounces={false}
          >
            {CONSENT_POINTS.map((point, i) => (
              <View key={i} style={styles.point}>
                <View style={styles.dot} />
                <Caption color="secondary" style={styles.pointText}>
                  {point}
                </Caption>
              </View>
            ))}

            <Caption color="muted" style={styles.legal}>
              By continuing you consent to biometric data processing under our
              Privacy Policy. You may withdraw consent at any time in Settings.
              Consent version {MAKEUP_CONSENT_VERSION}.
            </Caption>
          </ScrollView>

          <View style={styles.actions}>
            <Button
              title="Agree &amp; Continue"
              onPress={onAgree}
              variant="primary"
              size="md"
              block
            />
            <Pressable onPress={onCancel} style={styles.cancelButton}>
              <Label color="muted">Cancel</Label>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    justifyContent: "flex-end",
    backgroundColor: "rgba(0,0,0,0.5)",
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  sheet: {
    backgroundColor: THEME.colors.glass,
    borderTopLeftRadius: THEME.radius.xl,
    borderTopRightRadius: THEME.radius.xl,
    borderCurve: "continuous",
    borderTopWidth: 1,
    borderTopColor: THEME.colors.glassBorder,
    paddingTop: THEME.spacing.sm,
    maxHeight: "80%",
  },
  handle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: THEME.colors.textDisabled,
    alignSelf: "center",
    marginBottom: THEME.spacing.lg,
  },
  header: {
    paddingHorizontal: THEME.spacing.xl,
    marginBottom: THEME.spacing.lg,
  },
  iconWrap: {
    width: 52,
    height: 52,
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
    backgroundColor: THEME.colors.surface,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: THEME.spacing.md,
  },
  title: {
    marginBottom: THEME.spacing.sm,
  },
  subtitle: {
    lineHeight: 22,
  },
  scroll: {
    maxHeight: 220,
  },
  scrollContent: {
    paddingHorizontal: THEME.spacing.xl,
    paddingBottom: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },
  point: {
    flexDirection: "row",
    gap: THEME.spacing.sm,
    alignItems: "flex-start",
  },
  dot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: THEME.colors.textMuted,
    marginTop: 5,
    flexShrink: 0,
  },
  pointText: {
    flex: 1,
    lineHeight: 18,
  },
  legal: {
    lineHeight: 16,
    marginTop: THEME.spacing.sm,
  },
  actions: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },
  cancelButton: {
    alignItems: "center",
    paddingVertical: THEME.spacing.sm,
  },
});
