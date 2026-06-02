import { useEffect } from "react";
import { useAppStore } from "../store/appStore";
import { getMascotForRoute } from "../lib/mascots";
import { CoralPageWatermark } from "./CoralPageWatermark";

/**
 * CoralAppBackground — the single global, full-viewport watermark.
 *
 * Mount this ONCE at the top of the app shell (App.tsx), OUTSIDE any
 * overflow:hidden container.  CoralPageWatermark renders with position:fixed
 * so it always covers the full screen regardless of parent stacking context.
 *
 * DEV: A console.debug fires on mount and on every activePage change so you
 * can immediately detect duplicate mounts (two "[CoralAppBackground] mount"
 * lines in the console means it was mounted twice).
 *
 * ── Adjust watermark opacity ──────────────────────────────────────────────────
 * Import DEFAULT_WATERMARK_OPACITY from CoralPageWatermark.tsx and change it.
 * Or pass `opacity` as a prop to CoralPageWatermark here.
 */
export function CoralAppBackground() {
  const activePage = useAppStore((s) => s.activePage);
  const variant = getMascotForRoute(activePage);

  useEffect(() => {
    if (import.meta.env.DEV) {
      console.debug("[CoralAppBackground] mount — if you see this twice, it was mounted twice");
    }
    return () => {
      if (import.meta.env.DEV) {
        console.debug("[CoralAppBackground] unmount");
      }
    };
  }, []);

  if (import.meta.env.DEV) {
    console.debug("[CoralAppBackground] render", { activePage, variant });
  }

  return <CoralPageWatermark variant={variant} />;
}
