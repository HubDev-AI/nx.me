/**
 * Memory helpers — shared between MemoryList (rows) and MemoryDetailSheet
 * (tap-to-open modal). Pulled out of MemoryList.tsx so the modal can
 * import icon, label, and text helpers without a circular import back
 * into the list component.
 */
import type { Ionicons } from "@expo/vector-icons";

import type { MemoryType } from "../../lib/advisor";

/** Extract a display string from a memory content object. */
export function memoryContentText(content: Record<string, unknown>): string {
  if (typeof content.text === "string") return content.text;
  if (typeof content.summary === "string") return content.summary;
  return JSON.stringify(content);
}

/**
 * Icon glyph for each memory type. Only `goal` and `user_note` ever
 * surface in the UI today (system-authored types are server-filtered),
 * but every branch is covered so a future "What Ada knows" surface
 * can reuse the helper without forking it.
 */
export function memoryTypeIcon(
  type: MemoryType,
): React.ComponentProps<typeof Ionicons>["name"] {
  switch (type) {
    case "goal":
      return "flag-outline";
    case "user_note":
      return "document-text-outline";
    case "accepted_suggestion":
      return "checkmark-circle-outline";
    case "dismissed_suggestion":
      return "close-circle-outline";
    case "analysis_insight":
      return "analytics-outline";
    default:
      return "bookmark-outline";
  }
}

const MEMORY_TYPE_LABEL: Record<MemoryType, string> = {
  goal: "Goal",
  user_note: "Note",
  accepted_suggestion: "Accepted suggestion",
  dismissed_suggestion: "Dismissed suggestion",
  analysis_insight: "Insight",
};

export function memoryTypeLabel(type: MemoryType): string {
  return MEMORY_TYPE_LABEL[type] ?? "Memory";
}
