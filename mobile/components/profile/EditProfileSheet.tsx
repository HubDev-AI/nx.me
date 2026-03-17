import { useState, useCallback, useRef, useEffect } from "react";
import {
  View,
  Text,
  TextInput,
  Image,
  Pressable,
  Animated,
  Modal,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";

import {
  BG_CARD,
  BG_ELEVATED,
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  CTA_PRESSED,
  INPUT_FILL,
  BORDER_DEFAULT,
  COLORS,
  ERROR_DARK,
} from "../../constants/colors";
import {
  IMAGE_PICKER as IMAGE_PICKER_CONFIG,
  MIN_TOUCH_TARGET,
  PROFILE_CONFIG,
} from "../../constants/config";
import type { UserProfile, UpdateProfilePayload } from "./types";

const AVATAR_SIZE = 80;
const SHEET_ENTER_DURATION_MS = 300;
const SHEET_EXIT_DURATION_MS = 200;

interface EditProfileSheetProps {
  visible: boolean;
  profile: UserProfile;
  isUpdating: boolean;
  updateError: string | null;
  onSave: (payload: UpdateProfilePayload) => Promise<boolean>;
  onClose: () => void;
}

/**
 * Slide-in sheet for editing display name and avatar.
 * Confirms on unsaved changes before dismissing.
 */
export function EditProfileSheet({
  visible,
  profile,
  isUpdating,
  updateError,
  onSave,
  onClose,
}: EditProfileSheetProps) {
  const [displayName, setDisplayName] = useState(
    profile.display_name ?? "",
  );
  const [avatarUri, setAvatarUri] = useState(profile.avatar_url ?? "");
  const [hasChanges, setHasChanges] = useState(false);

  const slideAnim = useRef(new Animated.Value(0)).current;
  const scrimAnim = useRef(new Animated.Value(0)).current;

  // Reset form when profile changes or sheet opens
  useEffect(() => {
    if (visible) {
      setDisplayName(profile.display_name ?? "");
      setAvatarUri(profile.avatar_url ?? "");
      setHasChanges(false);

      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: 1,
          duration: SHEET_ENTER_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(scrimAnim, {
          toValue: 1,
          duration: SHEET_ENTER_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [visible, profile, slideAnim, scrimAnim]);

  const animateClose = useCallback(
    (callback: () => void) => {
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: 0,
          duration: SHEET_EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(scrimAnim, {
          toValue: 0,
          duration: SHEET_EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start(callback);
    },
    [slideAnim, scrimAnim],
  );

  const handleClose = useCallback(() => {
    if (hasChanges) {
      Alert.alert(
        "Unsaved Changes",
        "You have unsaved changes. Are you sure you want to discard them?",
        [
          { text: "Keep Editing", style: "cancel" },
          {
            text: "Discard",
            style: "destructive",
            onPress: () => animateClose(onClose),
          },
        ],
      );
    } else {
      animateClose(onClose);
    }
  }, [hasChanges, animateClose, onClose]);

  const handleDisplayNameChange = useCallback(
    (text: string) => {
      setDisplayName(text);
      const original = profile.display_name ?? "";
      setHasChanges(text !== original || avatarUri !== (profile.avatar_url ?? ""));
    },
    [profile.display_name, profile.avatar_url, avatarUri],
  );

  const handlePickAvatar = useCallback(async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsEditing: true,
      aspect: IMAGE_PICKER_CONFIG.ASPECT,
      quality: IMAGE_PICKER_CONFIG.QUALITY,
    });

    if (!result.canceled && result.assets[0]) {
      const newUri = result.assets[0].uri;
      setAvatarUri(newUri);
      setHasChanges(true);
    }
  }, []);

  const handleSave = useCallback(async () => {
    const payload: UpdateProfilePayload = {};

    const originalDisplayName = profile.display_name ?? "";
    if (displayName !== originalDisplayName) {
      payload.display_name = displayName.trim();
    }

    const originalAvatarUrl = profile.avatar_url ?? "";
    if (avatarUri !== originalAvatarUrl) {
      payload.avatar_url = avatarUri;
    }

    if (Object.keys(payload).length === 0) {
      animateClose(onClose);
      return;
    }

    const success = await onSave(payload);
    if (success) {
      animateClose(onClose);
    }
  }, [displayName, avatarUri, profile, onSave, animateClose, onClose]);

  const translateY = slideAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [400, 0],
  });

  const scrimOpacity = scrimAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 0.5],
  });

  const isDisplayNameValid =
    displayName.trim().length > 0 &&
    displayName.trim().length <= PROFILE_CONFIG.DISPLAY_NAME_MAX_LENGTH;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={handleClose}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={styles.modalContainer}
      >
        {/* Scrim */}
        <Animated.View
          style={[styles.scrim, { opacity: scrimOpacity }]}
        >
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={handleClose}
            accessibilityLabel="Close edit profile"
            accessibilityRole="button"
          />
        </Animated.View>

        {/* Sheet */}
        <Animated.View
          style={[
            styles.sheet,
            { transform: [{ translateY }] },
          ]}
        >
          {/* Handle bar */}
          <View style={styles.handleBar} />

          {/* Header */}
          <View style={styles.header}>
            <Pressable
              onPress={handleClose}
              style={styles.headerButton}
              accessibilityLabel="Cancel"
              accessibilityRole="button"
            >
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>

            <Text style={styles.headerTitle}>Edit Profile</Text>

            <Pressable
              onPress={handleSave}
              disabled={isUpdating || !isDisplayNameValid}
              style={[
                styles.headerButton,
                (!isDisplayNameValid || isUpdating) &&
                  styles.headerButtonDisabled,
              ]}
              accessibilityLabel="Save profile changes"
              accessibilityRole="button"
              accessibilityState={{ disabled: isUpdating || !isDisplayNameValid }}
            >
              <Text
                style={[
                  styles.saveText,
                  (!isDisplayNameValid || isUpdating) &&
                    styles.saveTextDisabled,
                ]}
              >
                {isUpdating ? "Saving..." : "Save"}
              </Text>
            </Pressable>
          </View>

          {/* Avatar picker */}
          <Pressable
            onPress={handlePickAvatar}
            style={styles.avatarPicker}
            accessibilityLabel="Change avatar photo"
            accessibilityRole="button"
          >
            {avatarUri ? (
              <Image
                source={{ uri: avatarUri }}
                style={styles.avatar}
                accessibilityLabel="Current avatar"
              />
            ) : (
              <View style={[styles.avatar, styles.avatarPlaceholder]}>
                <Ionicons
                  name="person"
                  size={36}
                  color={TEXT_SECONDARY}
                />
              </View>
            )}
            <View style={styles.avatarBadge}>
              <Ionicons name="camera" size={14} color="#FFFFFF" />
            </View>
          </Pressable>
          <Text style={styles.avatarHint}>Tap to change photo</Text>

          {/* Display name input */}
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>Display Name</Text>
            <TextInput
              value={displayName}
              onChangeText={handleDisplayNameChange}
              style={styles.input}
              placeholderTextColor={TEXT_DISABLED}
              placeholder="Your display name"
              maxLength={PROFILE_CONFIG.DISPLAY_NAME_MAX_LENGTH}
              autoCapitalize="words"
              returnKeyType="done"
              accessibilityLabel="Display name"
            />
            <Text style={styles.charCount}>
              {displayName.length}/{PROFILE_CONFIG.DISPLAY_NAME_MAX_LENGTH}
            </Text>
          </View>

          {/* Error message */}
          {updateError ? (
            <View style={styles.errorContainer}>
              <Ionicons
                name="alert-circle"
                size={16}
                color={ERROR_DARK}
              />
              <Text style={styles.errorText}>{updateError}</Text>
            </View>
          ) : null}
        </Animated.View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    justifyContent: "flex-end",
  },
  scrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#000000",
  },
  sheet: {
    backgroundColor: BG_PAGE,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingBottom: 40,
    minHeight: 400,
  },
  handleBar: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: COLORS.neutral.dark[500],
    alignSelf: "center",
    marginTop: 8,
    marginBottom: 8,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 8,
    minHeight: MIN_TOUCH_TARGET,
  },
  headerButton: {
    minWidth: 60,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
  },
  headerButtonDisabled: {
    opacity: 0.4,
  },
  headerTitle: {
    fontSize: 17,
    fontWeight: "600",
    color: TEXT_PRIMARY,
  },
  cancelText: {
    fontSize: 16,
    color: TEXT_SECONDARY,
  },
  saveText: {
    fontSize: 16,
    fontWeight: "600",
    color: CTA_PRIMARY,
    textAlign: "right",
  },
  saveTextDisabled: {
    color: TEXT_DISABLED,
  },
  avatarPicker: {
    alignSelf: "center",
    marginTop: 16,
    position: "relative",
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
  },
  avatarPlaceholder: {
    backgroundColor: BG_ELEVATED,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarBadge: {
    position: "absolute",
    bottom: 0,
    right: 0,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: CTA_PRIMARY,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: BG_PAGE,
  },
  avatarHint: {
    fontSize: 13,
    color: TEXT_SECONDARY,
    textAlign: "center",
    marginTop: 8,
    marginBottom: 24,
  },
  fieldContainer: {
    paddingHorizontal: 16,
    marginBottom: 16,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: "600",
    color: TEXT_SECONDARY,
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  input: {
    backgroundColor: INPUT_FILL,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: BORDER_DEFAULT,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    color: TEXT_PRIMARY,
    minHeight: MIN_TOUCH_TARGET,
  },
  charCount: {
    fontSize: 12,
    color: TEXT_DISABLED,
    textAlign: "right",
    marginTop: 4,
  },
  errorContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 16,
    marginTop: 8,
  },
  errorText: {
    fontSize: 14,
    color: ERROR_DARK,
    flex: 1,
  },
});
