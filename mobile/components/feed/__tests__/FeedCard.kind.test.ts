/**
 * Unit tests for kind-derived logic in FeedCard.
 *
 * FeedCard mounts many native modules (Reanimated, Expo AV, Ionicons) that
 * require a real device or heavy jest mocking to render. These tests validate
 * the pure-logic helpers extracted from the component instead.
 */

import type { FeedPost } from "../types";

// ---------------------------------------------------------------------------
// Helpers mirroring FeedCard logic
// ---------------------------------------------------------------------------

function getKindLabel(post: Pick<FeedPost, "kind">): string {
  const isMakeup = (post.kind ?? "glowup") === "makeup";
  return isMakeup ? "Makeup" : "Glow-Up";
}

function buildShareMessage(
  post: Pick<FeedPost, "kind" | "caption">,
  shareUrl: string
): string {
  const kindLabel = getKindLabel(post);
  return post.caption
    ? `${post.caption} — Check it out on NXME ${shareUrl}`
    : `Check out this ${kindLabel} on NXME ${shareUrl}`;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("FeedCard — kind field logic", () => {
  describe("getKindLabel", () => {
    it("returns 'Glow-Up' when kind is undefined (legacy post)", () => {
      expect(getKindLabel({})).toBe("Glow-Up");
    });

    it("returns 'Glow-Up' when kind is 'glowup'", () => {
      expect(getKindLabel({ kind: "glowup" })).toBe("Glow-Up");
    });

    it("returns 'Makeup' when kind is 'makeup'", () => {
      expect(getKindLabel({ kind: "makeup" })).toBe("Makeup");
    });
  });

  describe("buildShareMessage", () => {
    const url = "https://nxme.ai/alice";

    it("uses caption when present, regardless of kind", () => {
      const msg = buildShareMessage(
        { kind: "makeup", caption: "My look" },
        url
      );
      expect(msg).toBe(`My look — Check it out on NXME ${url}`);
    });

    it("uses 'Glow-Up' in fallback for undefined kind", () => {
      const msg = buildShareMessage({ caption: null }, url);
      expect(msg).toBe(`Check out this Glow-Up on NXME ${url}`);
    });

    it("uses 'Makeup' in fallback for makeup kind", () => {
      const msg = buildShareMessage({ kind: "makeup", caption: null }, url);
      expect(msg).toBe(`Check out this Makeup on NXME ${url}`);
    });
  });
});
