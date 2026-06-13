"use client";

import { memo, useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Home, Landmark, TrendingUp, FileText, MessageSquare,
  Upload, Sun, Moon, Menu, X,
} from "lucide-react";
import { useAppStore } from "@/store/appStore";

const NAV_ITEMS = [
  { href: "/",            label: "Home",        icon: Home },
  { href: "/banking",     label: "Banking",     icon: Landmark },
  { href: "/investments", label: "Investments", icon: TrendingUp },
  { href: "/documents",   label: "Documents",   icon: FileText },
  { href: "/chat",        label: "Chat",        icon: MessageSquare },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

// ── Brand ─────────────────────────────────────────────────────────────────────

const Brand = memo(function Brand() {
  return (
    <Link href="/" className="group/brand flex items-center gap-2.5 shrink-0" aria-label="Coral home">
      {/* Mascot bubble — same style as CoralDropletImage sm */}
      <div
        className="
          relative shrink-0 overflow-hidden
          transition-all duration-300 ease-out
          group-hover/nav:scale-[1.07]
          group-hover/nav:drop-shadow-[0_0_18px_rgba(45,212,191,0.38)]
        "
        style={{
          width: 34,
          height: 34,
          borderRadius: "45% 55% 52% 48% / 48% 42% 58% 52%",
          background: "rgba(255,255,255,0.10)",
          border: "1px solid rgba(255,255,255,0.26)",
          boxShadow: "0 4px 14px rgba(11,60,93,0.28)",
        }}
      >
        <Image
          src="/mascots/coral-main.png"
          alt="Coral"
          fill
          priority
          className="object-cover"
          style={{ transform: "scale(1.06)", transformOrigin: "center 42%" }}
          sizes="34px"
        />
      </div>

      <span
        className="font-bold tracking-tight hidden sm:block"
        style={{ color: "var(--text-primary)", fontSize: "16px", letterSpacing: "-0.02em" }}
      >
        Coral
      </span>
    </Link>
  );
});

// ── Nav link ──────────────────────────────────────────────────────────────────

function NavLink({
  href, label, Icon, active,
}: {
  href: string; label: string; Icon: typeof Home; active: boolean;
}) {
  return active ? (
    <Link
      href={href}
      className="group/link relative inline-flex items-center gap-1.5 overflow-hidden rounded-full px-4 py-2 nav-active-pill"
    >
      {/* Framer pill for cross-route animation */}
      <motion.span
        layoutId="topnav-pill"
        className="absolute inset-0 rounded-full nav-active-pill-bg"
        transition={{ type: "spring", stiffness: 380, damping: 32 }}
      />

      {/* Inner shine on hover */}
      <span
        className="
          pointer-events-none absolute inset-0 rounded-full
          bg-gradient-to-r from-transparent via-white/28 to-transparent
          opacity-0 transition-opacity duration-300
          group-hover/link:opacity-100
        "
        aria-hidden
      />

      <Icon
        size={15}
        className="
          relative z-10 shrink-0
          transition-transform duration-200
          group-hover/link:-translate-y-px
        "
      />
      <span className="relative z-10 coral-nav-text font-bold" style={{ color: "var(--text-on-accent)" }}>
        {label}
      </span>
    </Link>
  ) : (
    <Link
      href={href}
      className="
        group/link relative inline-flex items-center gap-1.5 rounded-full
        px-3.5 py-2
        coral-nav-text font-semibold
        transition-all duration-200 ease-out
        hover:-translate-y-px
        hover:bg-black/[0.06]
        hover:shadow-[0_8px_24px_rgba(34,211,238,0.06)]
      "
      style={{ color: "var(--text-secondary)" }}
    >
      <Icon
        size={15}
        className="
          relative z-10 shrink-0
          transition-transform duration-200
          group-hover/link:-translate-y-px
        "
      />
      <span
        className="relative z-10 transition-colors duration-200"
        style={{}}
      >
        {label}
      </span>
    </Link>
  );
}

// ── Theme toggle ──────────────────────────────────────────────────────────────

function ThemeToggle() {
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const isLight = theme === "light";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
      className="
        group/toggle
        grid size-10 place-items-center rounded-full
        transition-all duration-200 ease-out
        hover:-translate-y-px
        hover:bg-black/[0.06]
      "
      style={{
        color: "var(--text-secondary)",
        border: "1px solid var(--border-subtle)",
      }}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={isLight ? "sun" : "moon"}
          initial={{ opacity: 0, rotate: -45, scale: 0.6 }}
          animate={{ opacity: 1, rotate: 0, scale: 1 }}
          exit={{ opacity: 0, rotate: 45, scale: 0.6 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className="flex items-center justify-center"
        >
          {isLight
            ? <Sun size={15} className="transition-transform duration-300 group-hover/toggle:rotate-12" style={{ color: "rgba(255,160,20,0.95)" }} />
            : <Moon size={15} className="transition-transform duration-300 group-hover/toggle:rotate-12" style={{ color: "rgba(103,232,249,0.90)" }} />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

// ── Upload button ─────────────────────────────────────────────────────────────

function UploadButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="
        group/upload
        relative inline-flex items-center gap-2 overflow-hidden
        rounded-full font-semibold text-white
        nav-upload-btn
        transition-all duration-220 ease-out
        hover:-translate-y-0.5
        hover:scale-[1.018]
        active:translate-y-0
        active:scale-[0.99]
      "
      style={{ padding: "0.5rem 1.1rem", fontSize: "var(--font-size-nav)" }}
    >
      {/* Shimmer sweep — fires once on hover via animation */}
      <span aria-hidden className="nav-upload-shimmer" />

      <Upload
        size={15}
        className="
          relative z-10 shrink-0
          transition-transform duration-200
          group-hover/upload:-translate-y-px
        "
      />
      <span className="relative z-10 hidden md:block">Upload documents</span>
      <span className="relative z-10 md:hidden">Upload</span>
    </button>
  );
}

// ── Top nav ───────────────────────────────────────────────────────────────────

function TopNav({ onUploadClick }: { onUploadClick: () => void }) {
  const pathname = usePathname() ?? "/";
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => { setMobileOpen(false); }, [pathname]);

  return (
    <div className="fixed top-0 inset-x-0 z-40 pointer-events-none">
      <div className="mx-auto max-w-[1320px] px-4 sm:px-6">
        <motion.nav
          initial={{ y: -24, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          /*
           * group/nav — all children can react to nav-level hover via
           * group-hover/nav: variants without adding JS state.
           *
           * Idle:  ~30% opaque glass that blends into the underwater scene.
           * Hover: richer glass surface + lift + cyan glow ring.
           */
          className="
            group/nav
            pointer-events-auto mt-5
            flex items-center justify-between gap-3
            rounded-full
            px-3 sm:px-4 py-2
          "
          style={{ background: "transparent", border: "none", boxShadow: "none" }}
        >

          {/* ── Left: Brand ── */}
          <Brand />

          {/* ── Center: Desktop links ── */}
          <div className="hidden lg:flex items-center gap-0.5">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.href}
                href={item.href}
                label={item.label}
                Icon={item.icon}
                active={isActive(pathname, item.href)}
              />
            ))}
          </div>

          {/* ── Right: Actions ── */}
          <div className="flex items-center gap-2 shrink-0">
            <div className="hidden sm:block">
              <UploadButton onClick={onUploadClick} />
            </div>
            <ThemeToggle />

            {/* Mobile toggle */}
            <button
              type="button"
              onClick={() => setMobileOpen((o) => !o)}
              aria-label="Toggle menu"
              className="
                lg:hidden grid size-10 place-items-center rounded-full
                transition-all duration-200
                hover:bg-white/[0.08]
              "
              style={{
                background: "var(--btn-glass-bg)",
                border: "1px solid var(--btn-glass-border)",
                color: "var(--text-secondary)",
              }}
            >
              {mobileOpen ? <X size={16} /> : <Menu size={16} />}
            </button>
          </div>
        </motion.nav>

        {/* Mobile drawer */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              initial={{ opacity: 0, transform: "translateY(-8px)" }}
              animate={{ opacity: 1, transform: "translateY(0px)" }}
              exit={{ opacity: 0, transform: "translateY(-8px)" }}
              transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
              className="lg:hidden pointer-events-auto mt-2 rounded-3xl p-2 origin-top"
              style={{
                background: "var(--nav-bg-scrolled)",
                border: "1px solid var(--nav-border-hover)",
                backdropFilter: "blur(28px)",
                WebkitBackdropFilter: "blur(28px)",
                boxShadow: "var(--nav-shadow-scrolled)",
              }}
            >
              {NAV_ITEMS.map((item) => {
                const active = isActive(pathname, item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="flex items-center gap-3 px-4 py-3 rounded-2xl coral-nav-text font-semibold transition-colors"
                    style={{
                      color: active ? "var(--text-on-accent)" : "var(--text-secondary)",
                      background: active ? "var(--accent-coral-grad)" : "transparent",
                    }}
                  >
                    <Icon size={16} />
                    {item.label}
                  </Link>
                );
              })}
              <button
                type="button"
                onClick={() => { setMobileOpen(false); onUploadClick(); }}
                className="sm:hidden w-full mt-1 flex items-center gap-3 px-4 py-3 rounded-2xl coral-nav-text font-semibold text-white"
                style={{ background: "var(--accent-coral-grad)" }}
              >
                <Upload size={16} />
                Upload documents
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

export default memo(TopNav);
