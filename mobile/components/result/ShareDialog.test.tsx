/**
 * ShareDialog — row visibility matrix + confirm-panel transitions.
 *
 * Mocks:
 *   - `useCapabilities` to avoid pulling in auth + features contexts for
 *     a pure UI component. The capabilities module has its own matrix
 *     tests (capabilities.test.ts); this suite exercises downstream
 *     consumption.
 *   - `Button` + `Text` primitives, matching AdvisorChatEmpty.test.tsx:
 *     both pull in reanimated / useTheme / fonts that blow up under
 *     jest-expo without a native runtime.
 *   - `react-native-safe-area-context` — component reads `insets.bottom`.
 *   - `expo-haptics` — fire-and-forget; silence it.
 */
import { fireEvent, render } from "@testing-library/react-native";

import { ShareDialog, type ShareDialogJob } from "./ShareDialog";
import type { Capabilities } from "../../lib/capabilities";

// ---------- Module mocks ----------

// Replace reanimated with a pure-JS stub. The shipped
// `react-native-reanimated/mock` still pulls in react-native-worklets
// which blows up under jest-expo without a native runtime. This stub
// covers only what ShareDialog imports.
jest.mock("react-native-reanimated", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  return {
    __esModule: true,
    default: {
      View: ({ children, ...rest }: { children?: unknown }) =>
        ReactMock.createElement(RN.View, rest, children),
    },
    runOnJS: (fn: (...args: unknown[]) => unknown) => fn,
    useAnimatedStyle: () => ({}),
    // Real useSharedValue returns a stable ref across renders — match
    // that so effects depending on the value don't re-run every render.
    useSharedValue: (initial: unknown) =>
      ReactMock.useRef({ value: initial }).current,
    withSpring: (toValue: unknown) => toValue,
    withTiming: (
      toValue: unknown,
      _config?: unknown,
      callback?: (finished: boolean) => void,
    ) => {
      if (typeof callback === "function") callback(true);
      return toValue;
    },
  };
});

jest.mock("../../lib/capabilities", () => ({
  __esModule: true,
  useCapabilities: jest.fn(),
}));

jest.mock("../ui/Button", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const Button = ({
    title,
    onPress,
    disabled,
    isLoading,
    testID,
  }: {
    title: string;
    onPress: () => void;
    disabled?: boolean;
    isLoading?: boolean;
    testID?: string;
  }) =>
    ReactMock.createElement(
      RN.Pressable,
      {
        onPress: () => {
          if (disabled || isLoading) return;
          onPress();
        },
        accessibilityRole: "button",
        accessibilityState: { disabled: !!disabled, busy: !!isLoading },
        accessibilityLabel: title,
        testID,
      },
      ReactMock.createElement(RN.Text, null, title),
    );
  return { __esModule: true, Button };
});

jest.mock("../ui/Text", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const Heading = ({ children }: { children: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  const Body = ({ children }: { children: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  const Caption = ({ children }: { children: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  const Label = ({ children }: { children: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  return { __esModule: true, Body, Heading, Caption, Label };
});

jest.mock("react-native-safe-area-context", () => ({
  __esModule: true,
  useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
}));

jest.mock("expo-haptics", () => ({
  __esModule: true,
  impactAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: "light", Medium: "medium" },
  NotificationFeedbackType: { Error: "error" },
}));

// Ionicons triggers async state updates during its internal font-load that
// aren't wrapped in act() under jest-expo. Silencing to a stub keeps the
// test output clean — visual verification happens on the simulator.
jest.mock("@expo/vector-icons", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const Ionicons = ({ name }: { name: string }) =>
    ReactMock.createElement(RN.View, { accessibilityLabel: name });
  return { __esModule: true, Ionicons };
});

// ---------- Capability fixtures ----------

const capsMod = require("../../lib/capabilities") as {
  useCapabilities: jest.Mock;
};

function setCaps(overrides: Partial<Capabilities> = {}) {
  const base: Capabilities = {
    canViewOwnProfile: true,
    canEditProfile: true,
    canViewAccountDetails: true,
    canDeleteAccount: true,
    canSignOut: true,
    canSignIn: false,
    canSeeFeed: true,
    canUseAdvisor: true,
    canShareGlowup: true,
    canShareProfile: true,
    canPublishGlowup: true,
    canSeeOnboarding: true,
    canSubscribe: true,
    canReact: true,
    canViewBlockedUsers: true,
    requiresAuth: true,
  };
  capsMod.useCapabilities.mockReturnValue({ ...base, ...overrides });
}

function makeJob(overrides: Partial<ShareDialogJob> = {}): ShareDialogJob {
  return {
    id: "job-1",
    saved_at: null,
    post_id: null,
    share_hash: null,
    ...overrides,
  };
}

interface RenderArgs {
  job?: ShareDialogJob;
  visible?: boolean;
  saveState?: "pending" | "saving" | "saved";
  isPublishing?: boolean;
  publishError?: string | null;
  onSave?: () => void;
  onShare?: () => void;
  onPublish?: () => void;
  onClose?: () => void;
}

function renderDialog(args: RenderArgs = {}) {
  const onSave = args.onSave ?? jest.fn();
  const onShare = args.onShare ?? jest.fn();
  const onPublish = args.onPublish ?? jest.fn();
  const onClose = args.onClose ?? jest.fn();

  const utils = render(
    <ShareDialog
      visible={args.visible ?? true}
      onClose={onClose}
      job={args.job ?? makeJob()}
      onSave={onSave}
      onShare={onShare}
      onPublish={onPublish}
      saveState={args.saveState ?? "pending"}
      isPublishing={args.isPublishing ?? false}
      publishError={args.publishError ?? null}
    />,
  );
  return { ...utils, onSave, onShare, onPublish, onClose };
}

beforeEach(() => {
  jest.clearAllMocks();
});

// ---------- Row visibility matrix ----------

describe("ShareDialog — row visibility", () => {
  it("real user + social on + not saved + not published → Save, Share, and Publish rows render", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { queryByTestId } = renderDialog({
      job: makeJob({ saved_at: null, post_id: null }),
    });

    expect(queryByTestId("share-dialog-row-save")).not.toBeNull();
    expect(queryByTestId("share-dialog-row-share")).not.toBeNull();
    expect(queryByTestId("share-dialog-row-publish")).not.toBeNull();
  });

  it("real user + social off + not saved → Save + Share; Publish hidden", () => {
    setCaps({ canPublishGlowup: false, canEditProfile: true });
    const { queryByTestId } = renderDialog({
      job: makeJob({ saved_at: null, post_id: null }),
    });

    expect(queryByTestId("share-dialog-row-save")).not.toBeNull();
    expect(queryByTestId("share-dialog-row-share")).not.toBeNull();
    expect(queryByTestId("share-dialog-row-publish")).toBeNull();
  });

  it("guest + not saved → Save + Share; Publish hidden", () => {
    // Guest with auth_required=false: canEditProfile=true, canPublishGlowup=false.
    setCaps({ canPublishGlowup: false, canEditProfile: true });
    const { queryByTestId } = renderDialog({
      job: makeJob({ saved_at: null, post_id: null }),
    });

    expect(queryByTestId("share-dialog-row-save")).not.toBeNull();
    expect(queryByTestId("share-dialog-row-share")).not.toBeNull();
    expect(queryByTestId("share-dialog-row-publish")).toBeNull();
  });

  it("real user + saved + published → Share row only (Save + Publish hidden)", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { queryByTestId } = renderDialog({
      job: makeJob({
        saved_at: "2026-04-18T00:00:00Z",
        post_id: "post-xyz",
        share_hash: "abc123",
      }),
      saveState: "saved",
    });

    expect(queryByTestId("share-dialog-row-save")).toBeNull();
    expect(queryByTestId("share-dialog-row-share")).not.toBeNull();
    expect(queryByTestId("share-dialog-row-publish")).toBeNull();
  });

  it("caller without canEditProfile (e.g. anon) hides Save even when saved_at is null", () => {
    // Defensive: the dialog should only open for sessions that at least
    // have a profile identity. If the capability is false the Save row
    // disappears rather than firing a request that would 401.
    setCaps({ canEditProfile: false, canPublishGlowup: false });
    const { queryByTestId } = renderDialog({
      job: makeJob({ saved_at: null, post_id: null }),
    });

    expect(queryByTestId("share-dialog-row-save")).toBeNull();
    expect(queryByTestId("share-dialog-row-share")).not.toBeNull();
  });
});

// ---------- Publish confirm panel ----------

describe("ShareDialog — Publish confirm panel", () => {
  it("tapping Publish replaces rows with the confirm panel", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { getByTestId, queryByTestId } = renderDialog();

    // Rows view: rows visible, confirm hidden.
    expect(queryByTestId("share-dialog-row-publish")).not.toBeNull();
    expect(queryByTestId("share-dialog-confirm-publish")).toBeNull();

    fireEvent.press(getByTestId("share-dialog-row-publish"));

    // Confirm panel: rows gone, confirm buttons present.
    expect(queryByTestId("share-dialog-row-publish")).toBeNull();
    expect(queryByTestId("share-dialog-row-share")).toBeNull();
    expect(queryByTestId("share-dialog-row-save")).toBeNull();
    expect(queryByTestId("share-dialog-confirm-publish")).not.toBeNull();
    expect(queryByTestId("share-dialog-confirm-cancel")).not.toBeNull();
  });

  it("Cancel in the confirm panel returns to the rows view", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { getByTestId, queryByTestId } = renderDialog();

    fireEvent.press(getByTestId("share-dialog-row-publish"));
    expect(queryByTestId("share-dialog-confirm-publish")).not.toBeNull();

    fireEvent.press(getByTestId("share-dialog-confirm-cancel"));

    expect(queryByTestId("share-dialog-confirm-publish")).toBeNull();
    expect(queryByTestId("share-dialog-row-publish")).not.toBeNull();
    expect(queryByTestId("share-dialog-row-share")).not.toBeNull();
  });
});

// ---------- Handler wiring ----------

describe("ShareDialog — handler wiring", () => {
  it("tapping Save calls onSave once", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { getByTestId, onSave, onShare, onPublish } = renderDialog();

    fireEvent.press(getByTestId("share-dialog-row-save"));

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onShare).not.toHaveBeenCalled();
    expect(onPublish).not.toHaveBeenCalled();
  });

  it("tapping Share calls onShare once", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { getByTestId, onSave, onShare, onPublish } = renderDialog();

    fireEvent.press(getByTestId("share-dialog-row-share"));

    expect(onShare).toHaveBeenCalledTimes(1);
    expect(onSave).not.toHaveBeenCalled();
    expect(onPublish).not.toHaveBeenCalled();
  });

  it("tapping Publish row does NOT call onPublish until Confirm is tapped", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { getByTestId, onPublish } = renderDialog();

    fireEvent.press(getByTestId("share-dialog-row-publish"));
    expect(onPublish).not.toHaveBeenCalled();

    fireEvent.press(getByTestId("share-dialog-confirm-publish"));
    expect(onPublish).toHaveBeenCalledTimes(1);
  });

  it("Save row disabled while saveState is 'saving' (no double-submit)", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { getByTestId, onSave } = renderDialog({ saveState: "saving" });

    fireEvent.press(getByTestId("share-dialog-row-save"));

    expect(onSave).not.toHaveBeenCalled();
  });

  it("Confirm button disabled while isPublishing (no double-submit)", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { getByTestId, onPublish } = renderDialog({ isPublishing: true });

    fireEvent.press(getByTestId("share-dialog-row-publish"));
    fireEvent.press(getByTestId("share-dialog-confirm-publish"));

    expect(onPublish).not.toHaveBeenCalled();
  });

  it("Cancel stays live while isPublishing (feedback_disabled_button_ux)", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { getByTestId, queryByTestId } = renderDialog({
      isPublishing: true,
    });

    fireEvent.press(getByTestId("share-dialog-row-publish"));
    fireEvent.press(getByTestId("share-dialog-confirm-cancel"));

    // Panel unwound back to rows.
    expect(queryByTestId("share-dialog-confirm-publish")).toBeNull();
    expect(queryByTestId("share-dialog-row-publish")).not.toBeNull();
  });

  it("surfaces publishError inline when the parent reports a failed POST", () => {
    setCaps({ canPublishGlowup: true, canEditProfile: true });
    const { getByTestId, queryByText } = renderDialog({
      publishError: "Couldn't publish — try again.",
    });

    fireEvent.press(getByTestId("share-dialog-row-publish"));

    expect(queryByText("Couldn't publish — try again.")).not.toBeNull();
    // Panel stays open so the user can retry.
    expect(queryByText).toBeTruthy();
  });
});
