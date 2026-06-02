import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "../store/appStore";
import { CoralMascot } from "./CoralMascot";
// CoralMascot now renders through CoralDropletImage, so the floating button
// mascot automatically gets bubble/droplet styling at size="sm".

/**
 * CoralFloatingButton — a fixed bottom-right "Ask Coral" launcher.
 *
 * Behaviour:
 *  - Uses the main mascot.
 *  - Expands to show "Ask Coral" on hover (label hidden on small screens to
 *    avoid crowding).
 *  - Clicking navigates to the chat page.
 *  - Hidden while already on the chat page.
 *
 * To disable globally, remove <CoralFloatingButton /> from App.tsx.
 */
export function CoralFloatingButton() {
  const activePage = useAppStore((s) => s.activePage);
  const setActivePage = useAppStore((s) => s.setActivePage);

  const hidden = activePage === "chat";

  return (
    <AnimatePresence>
      {!hidden && (
        <motion.button
          type="button"
          onClick={() => setActivePage("chat")}
          title="Ask Coral"
          aria-label="Ask Coral — open chat"
          initial={{ opacity: 0, scale: 0.8, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.8, y: 12 }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: "spring", stiffness: 380, damping: 28 }}
          className="group fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full pl-2 pr-2 py-2 sm:hover:pr-4"
          style={{
            background:
              "linear-gradient(135deg, rgba(7,24,38,0.96) 0%, rgba(15,61,85,0.95) 100%)",
            border: "1px solid rgba(95,168,211,0.30)",
            boxShadow:
              "0 12px 36px rgba(4,14,26,0.50), 0 0 24px rgba(95,168,211,0.18)",
          }}
        >
          <CoralMascot variant="main" size="sm" animated glow className="shrink-0" />
          {/* Label expands on hover (desktop only) */}
          <span className="hidden max-w-0 overflow-hidden whitespace-nowrap text-[13px] font-semibold text-white transition-all duration-300 sm:inline-block sm:group-hover:max-w-[120px] sm:group-hover:pr-1">
            Ask Coral
          </span>
        </motion.button>
      )}
    </AnimatePresence>
  );
}
