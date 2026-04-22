import { useSession } from "../auth-context";
import { useAppQuery } from "./use-app-query";
import { fetchEntitlement } from "../entitlement";

/**
 * Returns the current user's subscription tier, or null while loading or unauthenticated.
 * Cached via React Query (30s stale time) so all callers share a single fetch.
 */
export function useSubscriptionTier(): "Free" | "Pro" | null {
  const session = useSession();
  const { data } = useAppQuery({
    queryKey: ["entitlement"] as const,
    queryFn: fetchEntitlement,
    enabled: session.isUser,
  });
  return data?.tier ?? null;
}
