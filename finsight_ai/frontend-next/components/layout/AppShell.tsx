"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";
import TopNav from "./TopNav";
import PageTransition from "./PageTransition";
import UnderwaterBackground from "@/components/coral/UnderwaterBackground";
import { Toaster } from "react-hot-toast";
import { useAppStore } from "@/store/appStore";

// Upload modal is interaction-only and never needed on first paint — load it lazily.
const UploadModal = dynamic(() => import("@/components/upload/UploadModal"), { ssr: false });

export default function AppShell({ children }: { children: React.ReactNode }) {
  const theme = useAppStore((s) => s.theme);
  const initTheme = useAppStore((s) => s.initTheme);
  const openUploadModal = useAppStore((s) => s.openUploadModal);
  const isLight = theme === "light";

  const pathname = usePathname() ?? "/";
  // All pages are full-viewport-height surfaces that manage their own internal
  // scroll and header offset, so they get no top padding from the shell.
  const isChat = true;

  // Sync theme from localStorage after hydration — avoids server/client mismatch
  useEffect(() => { initTheme(); }, [initTheme]);

  // Dev-only: log how long each route subtree takes to commit after navigation.
  useEffect(() => {
    if (process.env.NODE_ENV !== "development") return;
    const t0 = performance.now();
    const id = requestAnimationFrame(() => {
      console.log(`[route] ${pathname} committed in ${(performance.now() - t0).toFixed(1)}ms`);
    });
    return () => cancelAnimationFrame(id);
  }, [pathname]);

  return (
    <div className="relative min-h-screen">
      <UnderwaterBackground />
      <TopNav onUploadClick={openUploadModal} />

      <main
        className={isChat ? "relative z-10 flex flex-col" : "relative z-10 min-h-screen"}
        style={isChat ? { height: "100dvh" } : { paddingTop: "var(--nav-offset)" }}
      >
        {isChat ? children : <PageTransition>{children}</PageTransition>}
      </main>

      <UploadModal />

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            borderRadius: "14px",
            background: isLight ? "rgba(255,255,255,0.97)" : "rgba(6,26,42,0.94)",
            backdropFilter: "blur(16px)",
            color: isLight ? "rgba(11,40,65,0.90)" : "rgba(255,255,255,0.90)",
            border: isLight ? "1px solid rgba(31,111,139,0.20)" : "1px solid rgba(34,211,238,0.20)",
            boxShadow: isLight ? "0 8px 32px rgba(11,60,93,0.15)" : "0 8px 32px rgba(3,17,31,0.50)",
            fontSize: "13px",
            fontWeight: "500",
          },
        }}
      />
    </div>
  );
}
