/**
 * useShareDialog — handler triplet behavior + invariants.
 *
 * Covers the R5/R8 blocking-auto-save invariant: a failed save on the
 * Share path MUST abort the native-share hand-off. Also verifies the
 * re-entry guard on Publish, the image-url timeout branch, and the
 * onSaveSuccess / onPublishSuccess patch contracts.
 *
 * Mocks: `apiFetch`, `saveJob`, `parseApiError`, `showToast`. `apiFetch`
 * mirrors the `useSocialAuth.test.ts` pattern (import and cast). No
 * JSX is rendered — `renderHook` drives the hook directly.
 */
import { act, renderHook } from "@testing-library/react-native";

import { useShareDialog } from "./useShareDialog";
import type { ShareDialogJob } from "./ShareDialog";

jest.mock("../../lib/api", () => ({
  apiFetch: jest.fn(),
}));

jest.mock("../../lib/analysis", () => ({
  saveJob: jest.fn(),
}));

jest.mock("../../lib/errors", () => ({
  // Pass-through so tests can assert on the thrown message verbatim
  // without coupling to the project-wide copy bucketing.
  parseApiError: jest.fn((err: unknown) => ({
    kind: "unknown",
    message: err instanceof Error ? err.message : String(err),
  })),
}));

jest.mock("../../lib/toast", () => ({
  showToast: jest.fn(),
}));

// Re-imported after `jest.mock` so the casts resolve to the mocked
// module surface. Safe because jest hoists the mocks above imports.
const { apiFetch } = require("../../lib/api") as {
  apiFetch: jest.Mock;
};
const { saveJob } = require("../../lib/analysis") as {
  saveJob: jest.Mock;
};
const { showToast } = require("../../lib/toast") as {
  showToast: jest.Mock;
};

// ---------- Fixtures ----------

function makeJob(overrides: Partial<ShareDialogJob> = {}): ShareDialogJob {
  return {
    id: "job-1",
    saved_at: null,
    post_id: null,
    share_hash: null,
    ...overrides,
  };
}

interface SetupArgs {
  job?: ShareDialogJob | null;
  username?: string | null;
  imageUrls?: { before: string | null; after: string | null };
  imageUrlsThrows?: unknown;
  generateAndShareImpl?: jest.Mock;
}

function setup(args: SetupArgs = {}) {
  const job = args.job === undefined ? makeJob() : args.job;
  const username = args.username === undefined ? "alice" : args.username;
  const images = args.imageUrls ?? {
    before: "https://cdn.example/before.jpg",
    after: "https://cdn.example/after.jpg",
  };

  const getImageUrls = jest.fn(async () => {
    if (args.imageUrlsThrows !== undefined) {
      throw args.imageUrlsThrows;
    }
    return images;
  });
  const generateAndShare = args.generateAndShareImpl ?? jest.fn();
  const onDialogClose = jest.fn();
  const onSaveSuccess = jest.fn();
  const onPublishSuccess = jest.fn();

  const { result } = renderHook(() =>
    useShareDialog({
      job,
      username,
      generateAndShare,
      getImageUrls,
      onDialogClose,
      onSaveSuccess,
      onPublishSuccess,
    }),
  );

  return {
    result,
    getImageUrls,
    generateAndShare,
    onDialogClose,
    onSaveSuccess,
    onPublishSuccess,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
});

// ---------- handleSave ----------

describe("useShareDialog — handleSave", () => {
  it("happy path: POSTs save, flips saveState, fires onSaveSuccess with saved_at, toasts success", async () => {
    saveJob.mockResolvedValue({ saved_at: "2026-04-18T12:00:00Z" });
    const { result, onSaveSuccess } = setup();

    await act(async () => {
      await result.current.handleSave();
    });

    expect(saveJob).toHaveBeenCalledWith("job-1");
    expect(result.current.saveState).toBe("saved");
    expect(onSaveSuccess).toHaveBeenCalledWith("2026-04-18T12:00:00Z");
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "success" }),
    );
  });

  it("error path: resets saveState, toasts error, does NOT fire onSaveSuccess", async () => {
    saveJob.mockRejectedValue(new Error("save-failed"));
    const { result, onSaveSuccess } = setup();

    await act(async () => {
      await result.current.handleSave();
    });

    expect(result.current.saveState).toBe("pending");
    expect(onSaveSuccess).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error", message: "save-failed" }),
    );
  });

  it("no-op when saveState is not pending (double-submit guard)", async () => {
    saveJob.mockResolvedValue({ saved_at: "2026-04-18T12:00:00Z" });
    const { result } = setup();

    // First save locks the state to "saved".
    await act(async () => {
      await result.current.handleSave();
    });
    expect(result.current.saveState).toBe("saved");
    saveJob.mockClear();

    // Second save must be a no-op.
    await act(async () => {
      await result.current.handleSave();
    });
    expect(saveJob).not.toHaveBeenCalled();
  });

  it("no-op when job is null", async () => {
    const { result } = setup({ job: null });

    await act(async () => {
      await result.current.handleSave();
    });

    expect(saveJob).not.toHaveBeenCalled();
  });
});

// ---------- handleShare ----------

describe("useShareDialog — handleShare (R5/R8)", () => {
  it("already-saved job: skips auto-save, closes dialog before sharing, passes hash URL", async () => {
    const { result, generateAndShare, onDialogClose } = setup({
      job: makeJob({
        saved_at: "2026-04-17T00:00:00Z",
        post_id: "post-xyz",
        share_hash: "abc123",
      }),
    });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(saveJob).not.toHaveBeenCalled();
    // Close-before-share ordering matters for the modal scrim UX.
    expect(onDialogClose).toHaveBeenCalledTimes(1);
    expect(generateAndShare).toHaveBeenCalledWith(
      expect.objectContaining({
        shareUrl: "https://nxme.ai/alice/glow-up/abc123",
        shareMessage: "My NXME glow-up — https://nxme.ai/alice/glow-up/abc123",
      }),
    );
  });

  it("unsaved job: saves first, then shares (blocking auto-save)", async () => {
    saveJob.mockResolvedValue({ saved_at: "2026-04-18T12:00:00Z" });
    const { result, generateAndShare, onSaveSuccess } = setup();

    await act(async () => {
      await result.current.handleShare();
    });

    expect(saveJob).toHaveBeenCalledWith("job-1");
    expect(onSaveSuccess).toHaveBeenCalledWith("2026-04-18T12:00:00Z");
    expect(generateAndShare).toHaveBeenCalledTimes(1);
    // Save-toast does NOT fire on Share path — user only asked to
    // Share, not Save. (Toast suppression is a hook invariant; the
    // only toast surfaces on the save-failure branch below.)
    expect(showToast).not.toHaveBeenCalled();
  });

  it("save failure on Share path: share is NOT called, error toasted, dialog stays open", async () => {
    saveJob.mockRejectedValue(new Error("save-failed"));
    const { result, generateAndShare, onDialogClose } = setup();

    await act(async () => {
      await result.current.handleShare();
    });

    expect(saveJob).toHaveBeenCalledWith("job-1");
    // R5/R8: save failure MUST abort the native share.
    expect(generateAndShare).not.toHaveBeenCalled();
    expect(onDialogClose).not.toHaveBeenCalled();
    expect(result.current.saveState).toBe("pending");
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error" }),
    );
  });

  it("missing image URL pair: toasts timeout message, does not share", async () => {
    const { result, generateAndShare } = setup({
      job: makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
      imageUrls: { before: null, after: null },
    });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(generateAndShare).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "error",
        message: expect.stringContaining("Images didn't finish loading"),
      }),
    );
  });

  it("unpublished job (no post_id): share runs without shareUrl", async () => {
    const { result, generateAndShare } = setup({
      job: makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
    });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(generateAndShare).toHaveBeenCalledWith(
      expect.objectContaining({ shareUrl: undefined, shareMessage: undefined }),
    );
  });

  it("getImageUrls rejection: toasts error, does not share", async () => {
    const { result, generateAndShare } = setup({
      job: makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
      imageUrlsThrows: new Error("network down"),
    });

    await act(async () => {
      await result.current.handleShare();
    });

    expect(generateAndShare).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error", message: "network down" }),
    );
  });
});

// ---------- handlePublish ----------

describe("useShareDialog — handlePublish", () => {
  it("success: POSTs /v1/posts, fires onPublishSuccess(post_id, share_hash), closes dialog, resets flag", async () => {
    apiFetch.mockResolvedValue({
      post_id: "post-xyz",
      share_hash: "abc123",
    });
    const { result, onPublishSuccess, onDialogClose } = setup();

    await act(async () => {
      await result.current.handlePublish();
    });

    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/posts",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ glow_up_job_id: "job-1" }),
      }),
    );
    expect(onPublishSuccess).toHaveBeenCalledWith("post-xyz", "abc123");
    expect(onDialogClose).toHaveBeenCalledTimes(1);
    expect(result.current.isPublishing).toBe(false);
    expect(result.current.publishError).toBeNull();
  });

  it("4xx: sets publishError, resets isPublishing, keeps dialog open", async () => {
    apiFetch.mockRejectedValue(new Error("already published"));
    const { result, onDialogClose, onPublishSuccess } = setup();

    await act(async () => {
      await result.current.handlePublish();
    });

    expect(result.current.publishError).toBe("already published");
    expect(result.current.isPublishing).toBe(false);
    expect(onPublishSuccess).not.toHaveBeenCalled();
    expect(onDialogClose).not.toHaveBeenCalled();
  });

  it("re-entry guard: second tap while first is in flight is a no-op", async () => {
    // Never-resolving promise so the first tap stays in flight.
    let resolveFirst: ((value: unknown) => void) | null = null;
    apiFetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
    );
    const { result } = setup();

    await act(async () => {
      void result.current.handlePublish();
      // Allow the first call's setState to flush.
      await Promise.resolve();
    });
    expect(result.current.isPublishing).toBe(true);
    expect(apiFetch).toHaveBeenCalledTimes(1);

    // Second tap while first is pending — guard rejects it.
    await act(async () => {
      await result.current.handlePublish();
    });
    expect(apiFetch).toHaveBeenCalledTimes(1);

    // Cleanup — resolve the first call so act queue drains.
    await act(async () => {
      resolveFirst?.({ post_id: "post-1", share_hash: "h1" });
      await Promise.resolve();
    });
  });

  it("resetPublishError clears a prior error", async () => {
    apiFetch.mockRejectedValue(new Error("boom"));
    const { result } = setup();

    await act(async () => {
      await result.current.handlePublish();
    });
    expect(result.current.publishError).toBe("boom");

    act(() => {
      result.current.resetPublishError();
    });
    expect(result.current.publishError).toBeNull();
  });

  it("no-op when job is null", async () => {
    const { result } = setup({ job: null });

    await act(async () => {
      await result.current.handlePublish();
    });

    expect(apiFetch).not.toHaveBeenCalled();
  });
});

// ---------- saveState sync with job.saved_at ----------

describe("useShareDialog — saveState sync", () => {
  it("initializes to 'saved' when job.saved_at is present at mount", () => {
    const { result } = setup({
      job: makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
    });
    expect(result.current.saveState).toBe("saved");
  });

  it("promotes pending → saved when job.saved_at hydrates after mount", () => {
    const { result, rerender } = renderHookWithJob(makeJob());
    expect(result.current.saveState).toBe("pending");

    act(() => {
      rerender(makeJob({ saved_at: "2026-04-18T00:00:00Z" }));
    });
    expect(result.current.saveState).toBe("saved");
  });

  it("resets saved → pending when the parent swaps to a different unsaved job", () => {
    const { result, rerender } = renderHookWithJob(
      makeJob({ saved_at: "2026-04-17T00:00:00Z" }),
    );
    expect(result.current.saveState).toBe("saved");

    act(() => {
      rerender(makeJob({ id: "job-2", saved_at: null }));
    });
    expect(result.current.saveState).toBe("pending");
  });
});

/** renderHook helper that threads a changing `job` through rerenders. */
function renderHookWithJob(initial: ShareDialogJob | null) {
  const { result, rerender } = renderHook(
    ({ job }: { job: ShareDialogJob | null }) =>
      useShareDialog({
        job,
        username: "alice",
        generateAndShare: jest.fn(),
        getImageUrls: jest.fn(async () => ({
          before: "https://cdn/before.jpg",
          after: "https://cdn/after.jpg",
        })),
        onDialogClose: jest.fn(),
      }),
    { initialProps: { job: initial } },
  );
  return {
    result,
    rerender: (next: ShareDialogJob | null) => rerender({ job: next }),
  };
}
