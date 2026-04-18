/**
 * ResultScreen (Unit 8) — ShareDialog wiring, auto-save-before-share,
 * Publish flow, and header-right Delete overflow.
 *
 * The screen imports far more than a test runtime can load (Reanimated,
 * BeforeAfterSlider, QueryStateView, Watermark, native-view-shot,
 * Stripe, etc.), so every heavyweight surface is stubbed to a pure-JS
 * shim. The tests exercise the behaviors Unit 8 adds:
 *
 *   - Share/Save/Publish path routing through the dialog
 *   - Blocking auto-save: POST /save fires before the share sheet
 *   - shareUrl derivation: undefined when no post, hash URL when post exists
 *   - Publish flow: POST /v1/posts → local state merge → dialog close
 *   - Guest session (canPublishGlowup=false) hides the Publish row
 *   - Error paths: save failure skips share sheet; publish failure stays open
 *   - Delete overflow: Alert.alert confirm → DELETE /v1/jobs/{id}
 *
 * Mocks follow `mobile/components/result/ShareDialog.test.tsx` for
 * reanimated / vector-icons / safe-area-context, and stub `apiFetch` +
 * `saveJob` + `useShareComposite` + `useCapabilities` + `useAuth` +
 * `expo-router` so the test boots without a native runtime.
 */
import { fireEvent, render, act, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";

import type { Capabilities } from "../../../lib/capabilities";

// ---------------------------------------------------------------------------
// Module mocks — must precede the SUT import.
// ---------------------------------------------------------------------------

// Reanimated — pure-JS stub, mirrors ShareDialog.test.tsx.
jest.mock("react-native-reanimated", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const makePassthrough =
    () =>
    ({ children, ...rest }: { children?: unknown }) =>
      ReactMock.createElement(RN.View, rest, children);
  return {
    __esModule: true,
    default: {
      View: makePassthrough(),
    },
    View: makePassthrough(),
    Easing: {
      inOut: (_fn: unknown) => (v: unknown) => v,
      quad: (v: unknown) => v,
    },
    FadeIn: {
      duration: () => ({ delay: () => ({}) }),
    },
    runOnJS: (fn: (...args: unknown[]) => unknown) => fn,
    useAnimatedStyle: () => ({}),
    useReducedMotion: () => false,
    useSharedValue: (initial: unknown) =>
      ReactMock.useRef({ value: initial }).current,
    withRepeat: (v: unknown) => v,
    withSpring: (v: unknown) => v,
    withTiming: (
      v: unknown,
      _cfg?: unknown,
      cb?: (finished: boolean) => void,
    ) => {
      if (typeof cb === "function") cb(true);
      return v;
    },
  };
});

// Safe-area insets — constant for deterministic layout.
jest.mock("react-native-safe-area-context", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  return {
    __esModule: true,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
    SafeAreaView: ({ children, ...rest }: { children?: unknown }) =>
      ReactMock.createElement(RN.View, rest, children),
  };
});

// expo-router — stubbed navigation/hooks so the screen can read params.
const mockRouter = {
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
  canGoBack: jest.fn(() => false),
};
const mockUseLocalSearchParams = jest.fn(() => ({ jobId: "job-123" }));
jest.mock("expo-router", () => {
  const ReactMock = require("react");
  return {
    __esModule: true,
    useLocalSearchParams: () => mockUseLocalSearchParams(),
    useRouter: () => mockRouter,
    Stack: {
      Screen: ({ children }: { children?: unknown }) =>
        ReactMock.createElement(ReactMock.Fragment, null, children),
    },
  };
});

// Ionicons — stub, keeps the test free of font-load async side effects.
jest.mock("@expo/vector-icons", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const Ionicons = ({ name }: { name: string }) =>
    ReactMock.createElement(RN.View, { accessibilityLabel: `icon-${name}` });
  return { __esModule: true, Ionicons };
});

// Haptics — fire-and-forget.
jest.mock("expo-haptics", () => ({
  __esModule: true,
  impactAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: "light", Medium: "medium" },
  NotificationFeedbackType: { Error: "error" },
}));

// UI primitives — stubbed so the screen doesn't pull in fonts/themes.
jest.mock("../../../components/ui/PageBackground", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  return {
    __esModule: true,
    PageBackground: () => ReactMock.createElement(RN.View),
  };
});
jest.mock("../../../components/ui/PressableScale", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const PressableScale = ({
    onPress,
    children,
    accessibilityLabel,
  }: {
    onPress: () => void;
    children?: unknown;
    accessibilityLabel?: string;
  }) =>
    ReactMock.createElement(
      RN.Pressable,
      { onPress, accessibilityLabel, accessibilityRole: "button" },
      children,
    );
  return { __esModule: true, PressableScale };
});
jest.mock("../../../components/ui/QueryStateView", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const QueryStateView = ({ children }: { children?: unknown }) =>
    ReactMock.createElement(RN.View, null, children);
  return { __esModule: true, QueryStateView };
});
jest.mock("../../../components/ui/Text", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const Heading = ({ children }: { children?: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  const Body = ({ children }: { children?: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  const Caption = ({ children }: { children?: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  const Label = ({ children }: { children?: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  return { __esModule: true, Heading, Body, Caption, Label };
});
jest.mock("../../../components/ui/HeaderBackButton", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  return {
    __esModule: true,
    HeaderBackButton: ({ onPress }: { onPress: () => void }) =>
      ReactMock.createElement(RN.Pressable, {
        onPress,
        accessibilityLabel: "Go back",
        accessibilityRole: "button",
      }),
    HeaderBackButtonSpacer: () => ReactMock.createElement(RN.View),
  };
});
jest.mock("../../../components/ui/ZoomableImageModal", () => {
  const ReactMock = require("react");
  return {
    __esModule: true,
    ZoomableImageModal: () => ReactMock.createElement(ReactMock.Fragment, null),
  };
});
jest.mock("../../../components/ui/Button", () => {
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

// Share composite — capture calls instead of rendering the offscreen view.
interface GenerateAndShareParams {
  beforeUrl: string;
  afterUrl: string;
  rightLabel: string;
  shareUrl?: string;
  shareMessage?: string;
}
const mockGenerateAndShare: jest.Mock<
  Promise<void>,
  [GenerateAndShareParams]
> = jest.fn(async (_params: GenerateAndShareParams) => undefined);
jest.mock("../../../components/result/ShareComposite", () => {
  const ReactMock = require("react");
  return {
    __esModule: true,
    useShareComposite: () => ({
      ShareCompositeView: ReactMock.createElement(ReactMock.Fragment, null),
      generateAndShare: mockGenerateAndShare,
      isCapturing: false,
    }),
  };
});

// BeforeAfterSlider — the zoom handlers aren't under test here.
jest.mock("../../../components/result/BeforeAfterSlider", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  return {
    __esModule: true,
    default: () => ReactMock.createElement(RN.View),
  };
});

// Capabilities — matrix comes from setCaps below.
jest.mock("../../../lib/capabilities", () => ({
  __esModule: true,
  useCapabilities: jest.fn(),
}));

// Auth context — username drives the shareUrl derivation.
const mockUseAuth = jest.fn(() => ({ username: "alice" }));
jest.mock("../../../lib/auth-context", () => ({
  __esModule: true,
  useAuth: () => mockUseAuth(),
}));

// API layer — captured calls let us assert the save/publish/delete chain.
const mockApiFetch = jest.fn(async (_path: string, _opts?: unknown) => undefined as unknown);
jest.mock("../../../lib/api", () => ({
  __esModule: true,
  apiFetch: (path: string, opts?: unknown) => mockApiFetch(path, opts),
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    url: string;
    headers: Headers | null;
    constructor(status: number, body: string, url: string) {
      super(`API ${status}: ${url}`);
      this.status = status;
      this.body = body;
      this.url = url;
      this.headers = null;
      this.name = "ApiError";
    }
  },
}));

// saveJob — distinct from apiFetch so we can track the auto-save call
// independently of other apiFetch-wrapped calls.
const mockSaveJob = jest.fn(async (_jobId: string) => ({
  saved_at: "2026-04-18T00:00:00Z",
}));
jest.mock("../../../lib/analysis", () => {
  // Preserve the real module's type exports so the screen's imports still
  // type-check; only override the runtime functions the test cares about.
  const actual = jest.requireActual("../../../lib/analysis");
  return {
    __esModule: true,
    ...actual,
    saveJob: (id: string) => mockSaveJob(id),
    getJobStatus: jest.fn(),
  };
});

// React Query — stub useAppQuery, useQueryClient, useAppMutation.
type Job = {
  job_id: string;
  status: string;
  estimated_wait_seconds: number | null;
  elapsed_seconds: number | null;
  before_image_url: string | null;
  after_image_url: string | null;
  identity_preserved: boolean | null;
  failure_reason: string | null;
  credit_refunded: boolean | null;
  retry_eligible: boolean | null;
  user_guidance: string | null;
  saved_at: string | null;
  post_id?: string | null;
  share_hash?: string | null;
};
let mockCurrentJob: Job | null = null;
const mockRefetch = jest.fn(async () => ({ data: mockCurrentJob }));
jest.mock("../../../lib/hooks/use-app-query", () => ({
  __esModule: true,
  useAppQuery: () => ({
    data: mockCurrentJob,
    isLoading: false,
    error: null,
    appError: null,
    refetch: mockRefetch,
  }),
}));
jest.mock("../../../lib/hooks/use-app-mutation", () => ({
  __esModule: true,
  useAppMutation: (opts: {
    mutationFn: () => Promise<unknown>;
    onSuccess?: (data: unknown) => void;
    onError?: (err: unknown) => void;
  }) => {
    const mutate = jest.fn(async () => {
      try {
        const data = await opts.mutationFn();
        opts.onSuccess?.(data);
      } catch (err) {
        opts.onError?.(err);
      }
    });
    return {
      mutate,
      appError: null,
      isLoading: false,
      isPending: false,
      data: undefined,
    };
  },
}));
const mockRemoveQueries = jest.fn();
const mockInvalidateQueries = jest.fn();
jest.mock("@tanstack/react-query", () => ({
  __esModule: true,
  useQueryClient: () => ({
    removeQueries: mockRemoveQueries,
    invalidateQueries: mockInvalidateQueries,
  }),
}));

// use-refund-toast — fire-and-forget for this surface.
jest.mock("../../../lib/hooks/use-refund-toast", () => ({
  __esModule: true,
  useRefundToast: () => undefined,
}));

// Theme — deterministic, no flag-driven branching.
jest.mock("../../../lib/theme-context", () => ({
  __esModule: true,
  useTheme: () => ({ theme: { accent: "#ff00ff" } }),
}));

// Toast — capture invocations so error-path tests can assert.
const mockShowToast = jest.fn();
jest.mock("../../../lib/toast", () => ({
  __esModule: true,
  showToast: (...args: unknown[]) => mockShowToast(...args),
}));

// useFonts — static font-name map.
jest.mock("../../../hooks/useFonts", () => ({
  __esModule: true,
  FONTS: {
    display: "display",
    body: "body",
    bodyMedium: "bodyMedium",
    bodySemiBold: "bodySemiBold",
    bodyBold: "bodyBold",
  },
}));

// Colors — only constants the ResultActions subtree imports.
jest.mock("../../../constants/colors", () => ({
  __esModule: true,
  CTA_PRIMARY: "#000",
  TEXT_SECONDARY: "#999",
  CREDIT_BADGE_BG: "#eee",
  CREDIT_BADGE_TEXT: "#111",
  CREDIT_BADGE_ICON: "#222",
  OVERLAY_MEDIUM: "rgba(0,0,0,0.5)",
}));

// Now import the SUT and the capabilities mock handle. The import has to
// land after every `jest.mock()` call above — hoisting only works within a
// single block, and several of these mocks close over jest.fn() handles
// declared alongside them. Hence the eslint-disable.
// eslint-disable-next-line import/first
import ResultScreen from "../[jobId]";

const capsMod = require("../../../lib/capabilities") as {
  useCapabilities: jest.Mock;
};

const BASE_CAPS: Capabilities = {
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

function setCaps(overrides: Partial<Capabilities> = {}) {
  capsMod.useCapabilities.mockReturnValue({ ...BASE_CAPS, ...overrides });
}

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    job_id: "job-123",
    status: "completed",
    estimated_wait_seconds: null,
    elapsed_seconds: null,
    before_image_url: "https://img.test/before.png",
    after_image_url: "https://img.test/after.png",
    identity_preserved: true,
    failure_reason: null,
    credit_refunded: null,
    retry_eligible: null,
    user_guidance: null,
    saved_at: null,
    post_id: null,
    share_hash: null,
    ...overrides,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockCurrentJob = makeJob();
  setCaps({ canPublishGlowup: true, canEditProfile: true });
  mockUseAuth.mockReturnValue({ username: "alice" });
  mockApiFetch.mockReset();
  mockApiFetch.mockResolvedValue(undefined);
  mockSaveJob.mockReset();
  mockSaveJob.mockResolvedValue({ saved_at: "2026-04-18T00:00:00Z" });
  mockGenerateAndShare.mockReset();
  mockGenerateAndShare.mockResolvedValue(undefined);
});

function openShareDialog(
  queryByText: (text: string) => unknown,
): void {
  // The primary button swaps label based on `canPublishGlowup` — try both.
  const btn =
    (queryByText("Share & Publish…") as never) ??
    (queryByText("Share…") as never);
  if (!btn) throw new Error("Primary share button not rendered");
  fireEvent.press(btn);
}

// ---------------------------------------------------------------------------
// Primary-row label (Unit 8 adaptive copy)
// ---------------------------------------------------------------------------

describe("ResultScreen — primary row label", () => {
  it("shows 'Share & Publish…' when canPublishGlowup=true", () => {
    setCaps({ canPublishGlowup: true });
    const { getByText } = render(<ResultScreen />);
    expect(getByText("Share & Publish…")).toBeTruthy();
  });

  it("shows 'Share…' (no false promise) when canPublishGlowup=false", () => {
    setCaps({ canPublishGlowup: false });
    const { getByText, queryByText } = render(<ResultScreen />);
    expect(getByText("Share…")).toBeTruthy();
    expect(queryByText("Share & Publish…")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Share path (R5 + R8: blocking auto-save, no 404 links)
// ---------------------------------------------------------------------------

describe("ResultScreen — Share path", () => {
  it("saved_at=null + post_id=null → auto-saves, opens sheet with shareUrl undefined", async () => {
    mockCurrentJob = makeJob({ saved_at: null, post_id: null });
    const { queryByText, getByTestId } = render(<ResultScreen />);

    openShareDialog(queryByText);

    await act(async () => {
      fireEvent.press(getByTestId("share-dialog-row-share"));
    });

    // Save fired.
    expect(mockSaveJob).toHaveBeenCalledTimes(1);
    expect(mockSaveJob).toHaveBeenCalledWith("job-123");

    // Share sheet composed, but without a card-web URL (R5).
    expect(mockGenerateAndShare).toHaveBeenCalledTimes(1);
    expect(mockGenerateAndShare).toHaveBeenCalledWith(
      expect.objectContaining({ shareUrl: undefined }),
    );
  });

  it("saved_at=null + post exists → auto-saves, opens sheet with hash URL", async () => {
    mockCurrentJob = makeJob({
      saved_at: null,
      post_id: "post-abc",
      share_hash: "hashxyz",
    });
    const { queryByText, getByTestId } = render(<ResultScreen />);

    openShareDialog(queryByText);

    await act(async () => {
      fireEvent.press(getByTestId("share-dialog-row-share"));
    });

    expect(mockSaveJob).toHaveBeenCalledTimes(1);
    expect(mockGenerateAndShare).toHaveBeenCalledTimes(1);
    expect(mockGenerateAndShare).toHaveBeenCalledWith(
      expect.objectContaining({
        shareUrl: "https://nxme.ai/alice/glow-up/hashxyz",
      }),
    );
  });

  it("saved_at already set → Save row hidden, Share skips auto-save", async () => {
    mockCurrentJob = makeJob({ saved_at: "2026-04-18T00:00:00Z" });
    const { queryByText, getByTestId, queryByTestId } = render(<ResultScreen />);

    openShareDialog(queryByText);

    // Save row should be hidden when already saved.
    expect(queryByTestId("share-dialog-row-save")).toBeNull();

    await act(async () => {
      fireEvent.press(getByTestId("share-dialog-row-share"));
    });

    expect(mockSaveJob).not.toHaveBeenCalled();
    expect(mockGenerateAndShare).toHaveBeenCalledTimes(1);
  });

  it("save failure → toast error, does NOT open share sheet", async () => {
    mockCurrentJob = makeJob({ saved_at: null });
    mockSaveJob.mockRejectedValueOnce(new Error("network down"));

    const { queryByText, getByTestId } = render(<ResultScreen />);

    openShareDialog(queryByText);

    await act(async () => {
      fireEvent.press(getByTestId("share-dialog-row-share"));
    });

    // Save attempted.
    expect(mockSaveJob).toHaveBeenCalledTimes(1);
    // Error surfaced via toast (native layer — renders above the dialog
    // Modal, so the user actually sees it).
    expect(mockShowToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error" }),
    );
    // Native share sheet NOT called — R5/R8 "no silent 404 links".
    expect(mockGenerateAndShare).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Publish path (R4 — explicit confirm)
// ---------------------------------------------------------------------------

describe("ResultScreen — Publish path", () => {
  it("Publish tap + confirm → POST /v1/posts fires, dialog closes, post_id set locally", async () => {
    mockCurrentJob = makeJob({ post_id: null });
    mockApiFetch.mockImplementation(async (path: string, opts?: unknown) => {
      const options = opts as { method?: string } | undefined;
      if (path === "/v1/posts" && options?.method === "POST") {
        return { post_id: "post-xyz", share_hash: "newhash" } as unknown;
      }
      return undefined;
    });

    const { queryByText, getByTestId, queryByTestId } = render(<ResultScreen />);

    openShareDialog(queryByText);
    fireEvent.press(getByTestId("share-dialog-row-publish"));

    await act(async () => {
      fireEvent.press(getByTestId("share-dialog-confirm-publish"));
    });

    expect(mockApiFetch).toHaveBeenCalledWith(
      "/v1/posts",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ glow_up_job_id: "job-123" }),
      }),
    );

    // Dialog closed — confirm panel gone.
    await waitFor(() => {
      expect(queryByTestId("share-dialog-confirm-publish")).toBeNull();
    });

    // Re-opening the dialog: Publish row should be hidden now that
    // post_id is set in local state.
    openShareDialog(queryByText);
    expect(queryByTestId("share-dialog-row-publish")).toBeNull();
  });

  it("Publish POST failure → inline error inside confirm panel, panel stays open", async () => {
    mockCurrentJob = makeJob({ post_id: null });
    const apiError = new Error("publish failed");
    mockApiFetch.mockImplementation(async (path: string, opts?: unknown) => {
      const options = opts as { method?: string } | undefined;
      if (path === "/v1/posts" && options?.method === "POST") {
        throw apiError;
      }
      return undefined;
    });

    const { queryByText, getByTestId, queryByTestId } = render(<ResultScreen />);

    openShareDialog(queryByText);
    fireEvent.press(getByTestId("share-dialog-row-publish"));

    await act(async () => {
      fireEvent.press(getByTestId("share-dialog-confirm-publish"));
    });

    // Panel still open.
    expect(queryByTestId("share-dialog-confirm-publish")).not.toBeNull();
  });

  it("guest session (canPublishGlowup=false) → Publish row hidden", () => {
    setCaps({ canPublishGlowup: false });
    mockCurrentJob = makeJob({ saved_at: null, post_id: null });
    const { queryByText, getByTestId, queryByTestId } = render(<ResultScreen />);

    openShareDialog(queryByText);

    expect(queryByTestId("share-dialog-row-save")).not.toBeNull();
    expect(getByTestId("share-dialog-row-share")).toBeTruthy();
    expect(queryByTestId("share-dialog-row-publish")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Delete overflow (R6 — header reachability)
// ---------------------------------------------------------------------------

describe("ResultScreen — Delete overflow", () => {
  it("renders the overflow button on success", () => {
    const { getByTestId } = render(<ResultScreen />);
    expect(getByTestId("result-header-overflow")).toBeTruthy();
  });

  it("tapping overflow opens Alert with Cancel + Delete", () => {
    const alertSpy = jest
      .spyOn(Alert, "alert")
      .mockImplementation(() => undefined);
    const { getByTestId } = render(<ResultScreen />);

    fireEvent.press(getByTestId("result-header-overflow"));

    expect(alertSpy).toHaveBeenCalledTimes(1);
    const [title, body, buttons] = alertSpy.mock.calls[0]!;
    expect(title).toBe("Delete this glow-up?");
    expect(body).toMatch(/Links you've already shared/);
    const labels = (buttons as { text: string; style?: string }[]).map(
      (b) => b.text,
    );
    expect(labels).toEqual(["Cancel", "Delete"]);
    alertSpy.mockRestore();
  });

  it("confirming Delete fires DELETE /v1/jobs/{id} + removes query + navigates to profile", async () => {
    const alertSpy = jest.spyOn(Alert, "alert").mockImplementation((
      _title: string,
      _body?: string,
      buttons?: unknown,
    ) => {
      // Auto-press "Delete" so the test doesn't need an async pump.
      const list = buttons as {
        text: string;
        onPress?: () => void | Promise<void>;
      }[];
      const deleteBtn = list.find((b) => b.text === "Delete");
      deleteBtn?.onPress?.();
    });

    const { getByTestId } = render(<ResultScreen />);

    await act(async () => {
      fireEvent.press(getByTestId("result-header-overflow"));
    });

    expect(mockApiFetch).toHaveBeenCalledWith(
      "/v1/jobs/job-123",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(mockRemoveQueries).toHaveBeenCalledWith({
      queryKey: ["job", "job-123"],
    });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({
      queryKey: ["profile.glowups", "alice"],
    });
    expect(mockRouter.replace).toHaveBeenCalledWith("/(tabs)/profile");
    alertSpy.mockRestore();
  });

  it("Delete 5xx → toast error + stays on screen (no navigation)", async () => {
    mockApiFetch.mockRejectedValueOnce(new Error("boom"));

    const alertSpy = jest.spyOn(Alert, "alert").mockImplementation((
      _title: string,
      _body?: string,
      buttons?: unknown,
    ) => {
      const list = buttons as {
        text: string;
        onPress?: () => void | Promise<void>;
      }[];
      const deleteBtn = list.find((b) => b.text === "Delete");
      deleteBtn?.onPress?.();
    });

    const { getByTestId } = render(<ResultScreen />);

    await act(async () => {
      fireEvent.press(getByTestId("result-header-overflow"));
    });

    expect(mockShowToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error" }),
    );
    expect(mockRouter.replace).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });
});
