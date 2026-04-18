/**
 * wipeLocalDeviceState — reset every user-owned device-local surface.
 *
 * Called ONLY by the delete-account flow. Logout stays narrow (tokens only).
 * Adding new client-local state? Wire it in here.
 *
 * Coverage map:
 *   SecureStore (Keychain / Keystore) — every SECURE_STORE_KEYS value
 *   AsyncStorage                      — every @nxme:* key we own
 *   MMKV (via mutationQueue)          — offline mutation queue
 *   In-process                        — dismissed-jobs-store, refund-toast-store,
 *                                       queryClient cache
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

import {
  SECURE_STORE_KEYS,
  PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
  REFUND_TOAST_SEEN_STORAGE_KEY,
} from "../constants/config";
import { deleteItem } from "./secure-storage";
import { clearDismissedJobs } from "./dismissed-jobs-store";
import { clearRefundToastSeen } from "./refund-toast-store";
import { mutationQueue } from "./offline-queue";
import { queryClient } from "./query-client";

export async function wipeLocalDeviceState(): Promise<void> {
  // 1. SecureStore — every nxme_* key
  await Promise.all(
    Object.values(SECURE_STORE_KEYS).map((key) => deleteItem(key)),
  );

  // 2. AsyncStorage — every @nxme:* key we own
  await AsyncStorage.multiRemove([
    PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
    REFUND_TOAST_SEEN_STORAGE_KEY,
  ]);

  // 3. Module-level caches (also idempotently purges backing AsyncStorage)
  await Promise.all([clearDismissedJobs(), clearRefundToastSeen()]);

  // 4. MMKV-backed offline mutation queue — not reachable via AsyncStorage
  mutationQueue.clear();

  // 5. React Query cache
  queryClient.clear();
}
