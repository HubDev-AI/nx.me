/**
 * Signup screen — redirects to the unified auth screen.
 *
 * Login and signup are now handled by a single screen at /(auth)/login.
 * This file exists only to handle any deep links or navigation that
 * still references the old /(auth)/signup route.
 */
import { useEffect } from "react";
import { useRouter } from "expo-router";

export default function SignupRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/(auth)/login");
  }, [router]);

  return null;
}
