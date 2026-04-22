/**
 * Makeup Preset Picker screen.
 *
 * Route: /makeup/preset-picker?uploadId=<id>
 * Reached from /upload?action=makeup after photo upload completes.
 */
import { useCallback } from "react";
import { StyleSheet, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import {
  HeaderBackButton,
  HeaderBackButtonSpacer,
} from "../../components/ui/HeaderBackButton";
import { Heading } from "../../components/ui/Text";
import { PresetPicker } from "../../components/makeup/PresetPicker";

export default function PresetPickerScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { uploadId } = useLocalSearchParams<{ uploadId: string }>();

  const handleBack = useCallback(() => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/(tabs)/create");
    }
  }, [router]);

  const handleJobCreated = useCallback(
    (jobId: string) => {
      router.replace(`/result/${jobId}`);
    },
    [router],
  );

  if (!uploadId) {
    router.replace("/(tabs)/create");
    return null;
  }

  return (
    <View style={styles.container}>
      <PageBackground overlayOpacity={0.88} />

      <View style={[styles.header, { paddingTop: insets.top }]}>
        <HeaderBackButton onPress={handleBack} />
        <Heading size="md" style={styles.headerTitle} maxFontSizeMultiplier={1.3}>
          Choose a Look
        </Heading>
        <HeaderBackButtonSpacer />
      </View>

      <PresetPicker
        uploadId={uploadId}
        onJobCreated={handleJobCreated}
        onCancel={handleBack}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: THEME.spacing.lg,
    paddingBottom: THEME.spacing.md,
  },
  headerTitle: {
    flex: 1,
    textAlign: "center",
  },
});
