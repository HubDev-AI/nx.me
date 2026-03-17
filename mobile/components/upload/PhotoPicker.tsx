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
  Platform,
  AccessibilityInfo,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_CARD,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  CTA_PRESSED,
  BORDER_DEFAULT,
  COLORS,
} from "../../constants/colors";
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
  const [isPickerOpen, setIsPickerOpen] = useState(false);

  const handleAsset = useCallback(
    (result: ImagePicker.ImagePickerResult) => {
      if (result.canceled || result.assets.length === 0) return;
      const asset = result.assets[0];
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
        <Pressable
          onPress={onPhotoClear}
          style={styles.clearButton}
          accessibilityLabel="Remove selected photo"
          accessibilityRole="button"
          hitSlop={8}
        >
          <Ionicons name="close-circle" size={28} color={TEXT_PRIMARY} />
        </Pressable>
      </View>
    );
  }

  // --- Render: no photo selected ---
  return (
    <View style={styles.pickerContainer}>
      <Pressable
        onPress={pickFromCamera}
        style={({ pressed }) => [
          styles.optionButton,
          pressed && styles.optionButtonPressed,
          disabled && styles.optionButtonDisabled,
        ]}
        disabled={disabled}
        accessibilityLabel="Take a photo with camera"
        accessibilityRole="button"
      >
        <Ionicons
          name="camera-outline"
          size={32}
          color={disabled ? TEXT_DISABLED : CTA_PRIMARY}
        />
        <Text
          style={[styles.optionLabel, disabled && styles.optionLabelDisabled]}
        >
          Camera
        </Text>
      </Pressable>

      <View style={styles.divider} />

      <Pressable
        onPress={pickFromGallery}
        style={({ pressed }) => [
          styles.optionButton,
          pressed && styles.optionButtonPressed,
          disabled && styles.optionButtonDisabled,
        ]}
        disabled={disabled}
        accessibilityLabel="Choose a photo from gallery"
        accessibilityRole="button"
      >
        <Ionicons
          name="images-outline"
          size={32}
          color={disabled ? TEXT_DISABLED : CTA_PRIMARY}
        />
        <Text
          style={[styles.optionLabel, disabled && styles.optionLabelDisabled]}
        >
          Gallery
        </Text>
      </Pressable>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const SPACING = 8;
const PREVIEW_SIZE = 280;

const styles = StyleSheet.create({
  pickerContainer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: BG_CARD,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER_DEFAULT,
    borderStyle: "dashed",
    padding: SPACING * 4,
    gap: SPACING * 3,
  },
  optionButton: {
    alignItems: "center",
    justifyContent: "center",
    padding: SPACING * 2,
    borderRadius: 12,
    minWidth: 100,
    minHeight: 88,
  },
  optionButtonPressed: {
    backgroundColor: BG_ELEVATED,
  },
  optionButtonDisabled: {
    opacity: 0.5,
  },
  optionLabel: {
    marginTop: SPACING,
    fontSize: 14,
    fontWeight: "600",
    color: TEXT_PRIMARY,
  },
  optionLabelDisabled: {
    color: TEXT_DISABLED,
  },
  divider: {
    width: 1,
    height: 56,
    backgroundColor: BORDER_DEFAULT,
  },
  previewContainer: {
    alignItems: "center",
    justifyContent: "center",
  },
  previewImage: {
    width: PREVIEW_SIZE,
    height: PREVIEW_SIZE,
    borderRadius: 16,
    backgroundColor: BG_CARD,
  },
  clearButton: {
    position: "absolute",
    top: -8,
    right: -8,
    backgroundColor: BG_ELEVATED,
    borderRadius: 14,
    padding: 2,
  },
});
