/**
 * PhotoPicker — camera/gallery selection with permission handling.
 * Presents a bottom action sheet with two options: camera or gallery.
 */
import { useState, useCallback } from "react";
import {
  View,
  Text,
  Pressable,
  Image,
  Alert,
  StyleSheet,
} from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";
import * as ImagePicker from "expo-image-picker";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import { IMAGE_PICKER } from "../../constants/config";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SelectedPhoto {
  uri: string;
  fileName: string;
  mimeType: string;
  width: number;
  height: number;
  fileSize: number | undefined;
}

interface PhotoPickerProps {
  photo: SelectedPhoto | null;
  onPhotoSelected: (photo: SelectedPhoto) => void;
  onPhotoClear: () => void;
  disabled?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MIME_FALLBACK = "image/jpeg";

function extractMimeType(asset: ImagePicker.ImagePickerAsset): string {
  if (asset.mimeType) return asset.mimeType;
  const ext = asset.uri.split(".").pop()?.toLowerCase();
  if (ext === "png") return "image/png";
  if (ext === "heic" || ext === "heif") return "image/heic";
  return MIME_FALLBACK;
}

function extractFileName(asset: ImagePicker.ImagePickerAsset): string {
  if (asset.fileName) return asset.fileName;
  const segments = asset.uri.split("/");
  return segments[segments.length - 1] ?? "photo.jpg";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PhotoPicker({
  photo,
  onPhotoSelected,
  onPhotoClear,
  disabled = false,
}: PhotoPickerProps) {
  const { theme } = useTheme();
  const [isPickerOpen, setIsPickerOpen] = useState(false);

  // Press scale animations for option pills and change button
  const cameraScale = useSharedValue(1);
  const galleryScale = useSharedValue(1);
  const changeScale = useSharedValue(1);
  const cameraPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: cameraScale.value }],
  }));
  const galleryPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: galleryScale.value }],
  }));
  const changePressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: changeScale.value }],
  }));

  const handleAsset = useCallback(
    (result: ImagePicker.ImagePickerResult) => {
      if (result.canceled || result.assets.length === 0) return;
      const asset = result.assets[0];
      if (!asset) return;
      onPhotoSelected({
        uri: asset.uri,
        fileName: extractFileName(asset),
        mimeType: extractMimeType(asset),
        width: asset.width,
        height: asset.height,
        fileSize: asset.fileSize ?? undefined,
      });
    },
    [onPhotoSelected],
  );

  const pickFromGallery = useCallback(async () => {
    if (disabled || isPickerOpen) return;
    setIsPickerOpen(true);
    try {
      const permission =
        await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert(
          "Permission needed",
          "Please allow access to your photo library in Settings.",
        );
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        allowsEditing: true,
        aspect: IMAGE_PICKER.ASPECT,
        quality: IMAGE_PICKER.QUALITY,
      });
      handleAsset(result);
    } finally {
      setIsPickerOpen(false);
    }
  }, [disabled, isPickerOpen, handleAsset]);

  const pickFromCamera = useCallback(async () => {
    if (disabled || isPickerOpen) return;
    setIsPickerOpen(true);
    try {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        Alert.alert(
          "Permission needed",
          "Please allow camera access in Settings.",
        );
        return;
      }
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ["images"],
        allowsEditing: true,
        aspect: IMAGE_PICKER.ASPECT,
        quality: IMAGE_PICKER.QUALITY,
      });
      handleAsset(result);
    } finally {
      setIsPickerOpen(false);
    }
  }, [disabled, isPickerOpen, handleAsset]);

  // --- Render: photo selected ---
  if (photo) {
    return (
      <View style={styles.previewContainer}>
        <Image
          source={{ uri: photo.uri }}
          style={styles.previewImage}
          accessibilityLabel="Selected photo preview"
        />
        {/* Change photo overlay button */}
        <Animated.View style={[styles.changeButtonWrapper, changePressStyle]}>
          <Pressable
            onPress={onPhotoClear}
            onPressIn={() => { changeScale.value = withSpring(0.95, THEME.animation.press); }}
            onPressOut={() => { changeScale.value = withSpring(1, THEME.animation.press); }}
            style={styles.changeButton}
            accessibilityLabel="Change selected photo"
            accessibilityRole="button"
            hitSlop={8}
          >
            <Ionicons name="camera-reverse-outline" size={16} color={THEME.colors.textPrimary} />
            <Text style={styles.changeButtonText}>Change</Text>
          </Pressable>
        </Animated.View>
      </View>
    );
  }

  // --- Render: no photo selected — large dashed border area ---
  return (
    <View style={[
      styles.pickerContainer,
      { borderColor: theme.accent + "40" },
    ]}>
      {/* Central icon + text prompt */}
      <Ionicons
        name="camera-outline"
        size={48}
        color={disabled ? THEME.colors.textDisabled : theme.accent}
        style={styles.centerIcon}
      />
      <Text style={[
        styles.promptText,
        disabled && styles.promptTextDisabled,
      ]}>
        Tap to select a photo
      </Text>

      {/* Camera / Gallery option pills */}
      <View style={styles.optionRow}>
        <Animated.View style={cameraPressStyle}>
          <Pressable
            onPress={pickFromCamera}
            onPressIn={() => {
              if (!disabled) cameraScale.value = withSpring(0.96, THEME.animation.press);
            }}
            onPressOut={() => {
              cameraScale.value = withSpring(1, THEME.animation.press);
            }}
            style={[
              styles.optionPill,
              disabled && styles.optionPillDisabled,
            ]}
            disabled={disabled}
            accessibilityLabel="Take a photo with camera"
            accessibilityRole="button"
          >
            <Ionicons
              name="camera-outline"
              size={18}
              color={disabled ? THEME.colors.textDisabled : theme.accent}
            />
            <Text
              style={[styles.optionLabel, disabled && styles.optionLabelDisabled]}
            >
              Camera
            </Text>
          </Pressable>
        </Animated.View>

        <Animated.View style={galleryPressStyle}>
          <Pressable
            onPress={pickFromGallery}
            onPressIn={() => {
              if (!disabled) galleryScale.value = withSpring(0.96, THEME.animation.press);
            }}
            onPressOut={() => {
              galleryScale.value = withSpring(1, THEME.animation.press);
            }}
            style={[
              styles.optionPill,
              disabled && styles.optionPillDisabled,
            ]}
            disabled={disabled}
            accessibilityLabel="Choose a photo from gallery"
            accessibilityRole="button"
          >
            <Ionicons
              name="images-outline"
              size={18}
              color={disabled ? THEME.colors.textDisabled : theme.accent}
            />
            <Text
              style={[styles.optionLabel, disabled && styles.optionLabelDisabled]}
            >
              Gallery
            </Text>
          </Pressable>
        </Animated.View>
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const PREVIEW_SIZE = 280;

const styles = StyleSheet.create({
  /* ---- Empty state: dashed border area ---- */
  pickerContainer: {
    alignItems: "center",
    justifyContent: "center",
    borderRadius: THEME.radius.lg,
    borderWidth: 2,
    borderStyle: "dashed",
    paddingVertical: THEME.spacing.xxxl + 8,
    paddingHorizontal: THEME.spacing.xxl,
    minWidth: PREVIEW_SIZE,
  },
  centerIcon: {
    marginBottom: THEME.spacing.md,
  },
  promptText: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: THEME.colors.textSecondary,
    marginBottom: THEME.spacing.xxl,
  },
  promptTextDisabled: {
    color: THEME.colors.textDisabled,
  },

  /* Option pills — glass style, side by side */
  optionRow: {
    flexDirection: "row",
    gap: THEME.spacing.md,
  },
  optionPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingVertical: THEME.spacing.sm + 2,
    paddingHorizontal: THEME.spacing.lg,
  },
  optionPillDisabled: {
    opacity: 0.5,
  },
  optionLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    color: THEME.colors.textPrimary,
  },
  optionLabelDisabled: {
    color: THEME.colors.textDisabled,
  },

  /* ---- Photo selected: preview with change overlay ---- */
  previewContainer: {
    alignItems: "center",
    justifyContent: "center",
  },
  previewImage: {
    width: PREVIEW_SIZE,
    height: PREVIEW_SIZE,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    backgroundColor: THEME.colors.surface,
  },
  changeButtonWrapper: {
    position: "absolute",
    bottom: THEME.spacing.md,
    right: THEME.spacing.md,
  },
  changeButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingVertical: THEME.spacing.xs + 2,
    paddingHorizontal: THEME.spacing.md,
  },
  changeButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 12,
    color: THEME.colors.textPrimary,
  },
});
