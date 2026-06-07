import { redirect } from "next/navigation";

/**
 * Upload is a global action (a modal opened from the top nav / page CTAs), not a
 * destination. This route is intentionally not linked anywhere in the UI; if a
 * stale link or bookmark lands here, send the user home where they can open the
 * upload modal. Kept as a redirect rather than deleted to avoid 404s.
 */
export default function UploadPage() {
  redirect("/");
}
