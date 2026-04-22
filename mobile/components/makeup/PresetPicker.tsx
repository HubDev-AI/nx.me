/**
 * PresetPicker — grid of makeup preset cards with intensity selector.
 *
 * Flow:
 *   1. Consent check (shows MakeupConsentSheet if not yet consented)
 *   2. POST /makeup/analyze (fires immediately after consent, records consent)
 *   3. Grid shows unsorted presets + "Recommendations loading…" while analyzing
 *   4. On analyze success → sort by recommended_presets, fade header
 *   5. User picks preset + intensity → taps Apply → POST /makeup/generate → job_id
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import Animated, { useAnimatedStyle, withTiming } from "react-native-reanimated";
import * as Crypto from "expo-crypto";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { MAKEUP_CONSENT_STORAGE_KEY } from "../../constants/config";
import { MAKEUP_PRESETS, type MakeupPresetDefinition } from "../../constants/presets";
import type { MakeupIntensity } from "../../lib/makeup";
import { analyzeMakeup, generateMakeup } from "../../lib/makeup";
import { ApiError } from "../../lib/api";
import { Caption, Label } from "../ui/Text";
import { Button } from "../ui/Button";
import { useTheme } from "../../lib/theme-context";
import { PresetCard } from "./PresetCard";
import { IntensitySegmented } from "./IntensitySegmented";
import { MakeupConsentSheet } from "./MakeupConsentSheet";

const CONSENT_VERSION = "1.0";

interface PresetPickerProps {
  uploadId: string;
  onJobCreated: (jobId: string) => void;
  onCancel: () => void;
}

export function PresetPicker({ uploadId, onJobCreated, onCancel }: PresetPickerProps) {
  const { theme } = useTheme();

  const [consentSheetVisible, setConsentSheetVisible] = useState(false);
  const [analyzeState, setAnalyzeState] = useState<
    "pending" | "loading" | "success" | "error"
  >("pending");
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [presets, setPresets] = useState<MakeupPresetDefinition[]>(MAKEUP_PRESETS);
  const [selected, setSelected] = useState<MakeupPresetDefinition | null>(null);
  const [intensity, setIntensity] = useState<MakeupIntensity>("medium");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  const consentChecked = useRef(false);

  const runAnalyze = useCallback(async () => {
    setAnalyzeState("loading");
    setAnalyzeError(null);
    try {
      const result = await analyzeMakeup(uploadId);
      // Re-sort presets by recommended order (slug order from backend)
      if (result.recommended_presets.length > 0) {
        const recommendedSlugs = result.recommended_presets.map((p) => p.slug);
        setPresets([
          ...MAKEUP_PRESETS.filter((p) => recommendedSlugs.includes(p.slug)).sort(
            (a, b) => recommendedSlugs.indexOf(a.slug) - recommendedSlugs.indexOf(b.slug),
          ),
          ...MAKEUP_PRESETS.filter((p) => !recommendedSlugs.includes(p.slug)),
        ]);
        // Pre-select first recommendation
        const firstRec = result.recommended_presets[0];
        if (firstRec) {
          const matchPreset = MAKEUP_PRESETS.find((p) => p.slug === firstRec.slug);
          if (matchPreset) {
            setSelected(matchPreset);
            setIntensity(firstRec.intensity ?? "medium");
          }
        }
      }
      setAnalyzeState("success");
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 403
          ? "Please grant consent to continue."
          : err instanceof ApiError && err.status >= 500
            ? "Analysis failed — please try again."
            : "Couldn't analyze photo. Try again.";
      setAnalyzeError(msg);
      setAnalyzeState("error");
    }
  }, [uploadId]);

  // On mount: check consent, then run analyze
  useEffect(() => {
    if (consentChecked.current) return;
    consentChecked.current = true;

    AsyncStorage.getItem(MAKEUP_CONSENT_STORAGE_KEY).then((stored) => {
      if (stored === CONSENT_VERSION) {
        runAnalyze();
      } else {
        setConsentSheetVisible(true);
      }
    });
  }, [runAnalyze]);

  const handleConsentAgree = useCallback(async () => {
    setConsentSheetVisible(false);
    await AsyncStorage.setItem(MAKEUP_CONSENT_STORAGE_KEY, CONSENT_VERSION);
    runAnalyze();
  }, [runAnalyze]);

  const handleApply = useCallback(async () => {
    if (!selected) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const idempotencyKey = Crypto.randomUUID();
      const result = await generateMakeup(uploadId, selected.slug, intensity, idempotencyKey);
      onJobCreated(result.job_id);
    } catch (err) {
      let msg = "Something went wrong. Try again.";
      if (err instanceof ApiError) {
        if (err.status === 429) msg = "Service busy — try again in a moment.";
        else if (err.status === 403) {
          try {
            const body = JSON.parse(err.body) as { error?: { code?: string } };
            if (body?.error?.code === "CONSENT_REQUIRED") {
              setConsentSheetVisible(true);
              setGenerating(false);
              return;
            }
            if (body?.error?.code === "TIER_REQUIRED") {
              msg = "Pro subscription required.";
            }
          } catch { /* ignore */ }
        } else if (err.status === 400) {
          msg = "Please pick a different preset.";
        }
      }
      setGenerateError(msg);
      setGenerating(false);
    }
  }, [uploadId, selected, intensity, onJobCreated]);

  // Animated header opacity for "Recommendations loading..." fade
  const headerOpacity = useAnimatedStyle(() => ({
    opacity: analyzeState === "success" ? withTiming(0, { duration: 200 }) : 1,
  }));

  const isLoading = analyzeState === "loading";
  const hasError = analyzeState === "error";
  const currentIntensityOptions = selected?.supportedIntensities ?? ["subtle", "light", "medium", "bold"];

  // When selected preset changes, clamp intensity to supported
  const handleSelectPreset = useCallback((preset: MakeupPresetDefinition) => {
    setSelected(preset);
    if (!preset.supportedIntensities.includes(intensity)) {
      setIntensity(preset.defaultIntensity);
    }
  }, [intensity]);

  return (
    <View style={styles.container}>
      <MakeupConsentSheet
        visible={consentSheetVisible}
        onAgree={handleConsentAgree}
        onCancel={() => {
          setConsentSheetVisible(false);
          onCancel();
        }}
      />

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Fading recommendations header */}
        {analyzeState !== "success" && (
          <Animated.View style={[styles.recHeader, headerOpacity]}>
            {isLoading ? (
              <View style={styles.recHeaderRow}>
                <ActivityIndicator size="small" color={THEME.colors.textMuted} />
                <Caption color="muted">Recommendations loading…</Caption>
              </View>
            ) : hasError ? (
              <View style={styles.recHeaderRow}>
                <Caption color="muted">{analyzeError ?? "Browse all looks"}</Caption>
                <Pressable onPress={runAnalyze} hitSlop={8}>
                  <Caption color="secondary">Retry</Caption>
                </Pressable>
              </View>
            ) : null}
          </Animated.View>
        )}

        {/* Preset grid */}
        <View style={styles.grid}>
          {presets.map((preset) => (
            <PresetCard
              key={preset.slug}
              preset={preset}
              selected={selected?.slug === preset.slug}
              onPress={() => handleSelectPreset(preset)}
              accent={theme.accent}
            />
          ))}
        </View>

        {/* Intensity selector */}
        {selected && (
          <View style={styles.intensitySection}>
            <Label color="secondary" style={styles.intensityLabel}>
              Intensity
            </Label>
            <IntensitySegmented
              value={intensity}
              options={currentIntensityOptions}
              onChange={setIntensity}
              accent={theme.accent}
            />
          </View>
        )}

        {generateError && (
          <View style={styles.errorRow}>
            <Ionicons name="warning-outline" size={14} color={THEME.colors.destructive} />
            <Caption color="destructive">{generateError}</Caption>
          </View>
        )}
      </ScrollView>

      {/* Sticky bottom bar */}
      <View style={styles.bottomBar}>
        <Button
          title={generating ? "Applying…" : "Apply"}
          onPress={handleApply}
          variant="primary"
          size="md"
          block
          disabled={!selected || generating}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.lg,
    paddingBottom: THEME.spacing.xxxl,
    gap: THEME.spacing.lg,
  },
  recHeader: {
    minHeight: 24,
  },
  recHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: THEME.spacing.md,
  },
  intensitySection: {
    gap: THEME.spacing.sm,
  },
  intensityLabel: {
    fontSize: 11,
    letterSpacing: 1,
  },
  errorRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
  },
  bottomBar: {
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.lg,
    borderTopWidth: 1,
    borderTopColor: THEME.colors.border,
  },
});
