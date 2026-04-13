/**
 * PhotoPicker — camera/gallery selection with permission handling.
 * Presents a bottom action sheet with two options: camera or gallery.
 */
import { useState, useCallback, useEffect, useRef } from "react";
import {
  View,
  Pressable,
  Image,
  Alert,
  StyleSheet,
  ActivityIndicator,
  useWindowDimensions,
} from "react-native";
import Animated, {
  FadeIn,
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";
import * as ImagePicker from "expo-image-picker";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { IMAGE_PICKER } from "../../constants/config";
import { showToast } from "../../lib/toast";
import { hapticLight } from "../../lib/haptics";
import { Body, Caption } from "../ui/Text";

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
const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10MB

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
  const { width: windowWidth } = useWindowDimensions();
  const previewSize = Math.min(
    PREVIEW_SIZE_MAX,
    Math.max(PREVIEW_SIZE_MIN, windowWidth - PREVIEW_HORIZONTAL_INSET),
  );
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [openingSource, setOpeningSource] = useState<"camera" | "gallery" | null>(null);
  const galleryPermission = useRef<boolean | null>(null);
  const cameraPermission = useRef<boolean | null>(null);

  // Pre-warm permissions on mount so tap feels instant
  useEffect(() => {
    ImagePicker.getMediaLibraryPermissionsAsync().then((p) => {
      galleryPermission.current = p.granted;
    });
    ImagePicker.getCameraPermissionsAsync().then((p) => {
      cameraPermission.current = p.granted;
    });
  }, []);

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

      // Validate file size before accepting the image
      if (asset.fileSize && asset.fileSize > MAX_IMAGE_SIZE) {
        showToast({ kind: 'error', message: "Please select an image under 10MB." });
        return;
      }

      hapticLight();
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
    setOpeningSource("gallery");
    try {
      if (!galleryPermission.current) {
        const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
        galleryPermission.current = permission.granted;
        if (!permission.granted) {
          Alert.alert(
            "Permission needed",
            "Please allow access to your photo library in Settings.",
          );
          return;
        }
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
      setOpeningSource(null);
    }
  }, [disabled, isPickerOpen, handleAsset]);

  const pickFromCamera = useCallback(async () => {
    if (disabled || isPickerOpen) return;
    setIsPickerOpen(true);
    setOpeningSource("camera");
    try {
      if (!cameraPermission.current) {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        cameraPermission.current = permission.granted;
        if (!permission.granted) {
          Alert.alert(
            "Permission needed",
            "Please allow camera access in Settings.",
          );
          return;
        }
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
      setOpeningSource(null);
    }
  }, [disabled, isPickerOpen, handleAsset]);

  // --- Render: photo selected ---
  if (photo) {
    return (
      <View style={styles.previewContainer}>
        <Image
          source={{ uri: photo.uri }}
          style={[
            styles.previewImage,
            { width: previewSize, height: previewSize },
          ]}
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
            hitSlop={12}
          >
            <Ionicons name="camera-reverse-outline" size={16} color={THEME.colors.textPrimary} />
            <Caption weight="medium" color="primary">Change photo</Caption>
          </Pressable>
        </Animated.View>
      </View>
    );
  }

  // --- Render: no photo selected — large dashed border area ---
  return (
    <View
      style={[
        styles.pickerContainer,
        { borderColor: theme.accent + "66", minWidth: previewSize },
      ]}
    >
      {/* Central icon + text prompt */}
      <Ionicons
        name="camera-outline"
        size={48}
        color={disabled ? THEME.colors.textDisabled : theme.accent}
        style={styles.centerIcon}
      />
      <Body
        weight="medium"
        color={disabled ? "disabled" : "secondary"}
        style={styles.promptText}
      >
        Take a selfie or upload a clear photo of your face
      </Body>

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
            style={[styles.optionPill, disabled && styles.optionPillDisabled]}
            disabled={disabled}
            accessibilityLabel="Take a photo with camera"
            accessibilityRole="button"
          >
            {openingSource === "camera" ? (
              <ActivityIndicator size={16} color={theme.accent} />
            ) : (
              <Ionicons
                name="camera-outline"
                size={18}
                color={disabled ? THEME.colors.textDisabled : theme.accent}
              />
            )}
            <Caption weight="medium" color={disabled ? "disabled" : "primary"}>
              Camera
            </Caption>
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
            style={[styles.optionPill, disabled && styles.optionPillDisabled]}
            disabled={disabled}
            accessibilityLabel="Choose a photo from gallery"
            accessibilityRole="button"
          >
            {openingSource === "gallery" ? (
              <ActivityIndicator size={16} color={theme.accent} />
            ) : (
              <Ionicons
                name="images-outline"
                size={18}
                color={disabled ? THEME.colors.textDisabled : theme.accent}
              />
            )}
            <Caption weight="medium" color={disabled ? "disabled" : "primary"}>
              Gallery
            </Caption>
          </Pressable>
        </Animated.View>
      </View>

      {disabled ? (
        <Animated.View
          entering={FadeIn.duration(180)}
          style={styles.disabledOverlay}
          pointerEvents="none"
          accessibilityLiveRegion="polite"
        >
          <Ionicons
            name="lock-closed"
            size={20}
            color={THEME.colors.textSecondary}
          />
          <Caption weight="medium" color="secondary">
            Uploading photo…
          </Caption>
        </Animated.View>
      ) : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const PREVIEW_SIZE_MIN = 240;
const PREVIEW_SIZE_MAX = 320;
/**
 * Horizontal inset to subtract from the window width when computing the
 * responsive preview size — accounts for the outer page padding on both
 * sides of the picker.
 */
const PREVIEW_HORIZONTAL_INSET = 80;

const styles = StyleSheet.create({
  /* ---- Empty state: dashed border area ---- */
  pickerContainer: {
    alignItems: "center",
    justifyContent: "center",
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
    borderWidth: 2,
    borderStyle: "dashed",
    paddingVertical: THEME.spacing.xxxl,
    paddingHorizontal: THEME.spacing.xxl,
    overflow: "hidden",
  },
  centerIcon: {
    marginBottom: THEME.spacing.md,
  },
  promptText: {
    textAlign: "center",
    marginBottom: THEME.spacing.xxl,
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
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingVertical: THEME.spacing.sm + 2,
    paddingHorizontal: THEME.spacing.lg,
  },
  optionPillDisabled: {
    opacity: 0.5,
  },

  /* ---- Photo selected: preview with change overlay ---- */
  previewContainer: {
    alignItems: "center",
    justifyContent: "center",
  },
  previewImage: {
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
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
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingVertical: THEME.spacing.xs + 2,
    paddingHorizontal: THEME.spacing.md,
  },

  /* ---- Disabled overlay ---- */
  disabledOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(10, 10, 10, 0.72)",
    borderRadius: THEME.radius.lg,
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.sm,
  },
});
