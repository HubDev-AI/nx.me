/**
 * wipeLocalDeviceState — reset every user-owned device-local surface.
 *
 * Called ONLY by the delete-account flow. Logout stays narrow (tokens only).
 * Adding new client-local state? Wire it in here.
 *
 * Coverage map:
 *   SecureStore (Keychain / Keystore) — every SECURE_STORE_KEYS value
 *                                      (each key's SecureStore.deleteItemAsync
 *                                      call is caught in isolation so a
 *                                      single key failure doesn't leak
 *                                      JWT/refresh tokens on device).
 *   AsyncStorage                      — each module owns its own @nxme:*
 *                                      key removal (clearDismissedJobs,
 *                                      clearRefundToastSeen).
 *   MMKV (via mutationQueue)          — offline mutation queue
 *   In-process                        — dismissed-jobs-store, refund-toast-store,
 *                                       queryClient cache
 */
import {
  SECURE_STORE_KEYS,
} from "../constants/config";
import { deleteItem } from "./secure-storage";
import { clearDismissedJobs } from "./dismissed-jobs-store";
import { clearRefundToastSeen } from "./refund-toast-store";
import { mutationQueue } from "./offline-queue";
import { queryClient } from "./query-client";

export async function wipeLocalDeviceState(): Promise<void> {
  // 1. SecureStore — every nxme_* key. Use per-item .catch so a single
  //    failing key (e.g. Keychain access error on one entry) doesn't
  //    short-circuit Promise.all and leave the JWT / refresh token on
  //    device for the next session to pick up.
  await Promise.all(
    Object.values(SECURE_STORE_KEYS).map((key) =>
      deleteItem(key).catch((err) => {
        if (__DEV__) {
          console.warn(
            `wipeLocalDeviceState: deleteItem(${key}) failed`,
            err,
          );
        }
      }),
    ),
  );

  // 2. Module-level caches — each store owns its own AsyncStorage key
  //    removal (so the @nxme:* key cleanup happens here, not via a
  //    duplicate multiRemove at this layer).
  await Promise.all([clearDismissedJobs(), clearRefundToastSeen()]);

  // 3. MMKV-backed offline mutation queue — not reachable via AsyncStorage
  mutationQueue.clear();

  // 4. React Query cache
  queryClient.clear();
}
