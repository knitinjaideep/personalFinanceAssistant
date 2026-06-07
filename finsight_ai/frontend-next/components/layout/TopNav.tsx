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

const Brand = memo(function Brand() {
  return (
    <Link href="/" className="group flex items-center gap-2.5 shrink-0" aria-label="Coral home">
      <div
        className="relative shrink-0 overflow-hidden transition-transform duration-300 group-hover:scale-105"
        style={{
          width: 34,
          height: 34,
          borderRadius: "45% 55% 52% 48% / 48% 42% 58% 52%",
          background: "rgba(255,255,255,0.10)",
          border: "1px solid rgba(255,255,255,0.30)",
          boxShadow: "0 4px 14px rgba(11,60,93,0.28), 0 0 14px rgba(255,122,90,0.30)",
        }}
      >
        <Image
          src="/mascots/coral-main.png"
          alt="Coral"
          fill
          priority
          className="object-cover"
          style={{ transform: "scale(1.08)", transformOrigin: "center 42%" }}
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

function NavLink({ href, label, Icon, active }: { href: string; label: string; Icon: typeof Home; active: boolean }) {
  return (
    <Link
      href={href}
      className="relative flex items-center gap-1.5 px-3.5 py-2 rounded-full coral-nav-text font-semibold transition-colors duration-200"
      style={{ color: active ? "var(--text-on-accent)" : "var(--text-secondary)" }}
    >
      {active && (
        <motion.span
          layoutId="topnav-pill"
          className="absolute inset-0 rounded-full nav-active-pill"
          transition={{ type: "spring", stiffness: 380, damping: 32 }}
        />
      )}
      <Icon size={15} className="relative z-10 shrink-0" />
      <span className="relative z-10">{label}</span>
    </Link>
  );
}

function ThemeToggle() {
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const isLight = theme === "light";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
      className="relative w-9 h-9 rounded-full flex items-center justify-center transition-all duration-200 hover:scale-105"
      style={{ background: "var(--btn-glass-bg)", border: "1px solid var(--btn-glass-border)" }}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={isLight ? "sun" : "moon"}
          initial={{ opacity: 0, rotate: -45, scale: 0.6 }}
          animate={{ opacity: 1, rotate: 0, scale: 1 }}
          exit={{ opacity: 0, rotate: 45, scale: 0.6 }}
          transition={{ duration: 0.22 }}
          className="flex items-center justify-center"
        >
          {isLight
            ? <Sun size={15} style={{ color: "rgba(255,160,20,0.95)" }} />
            : <Moon size={15} style={{ color: "rgba(103,232,249,0.90)" }} />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

function UploadButton({ onClick, compact }: { onClick: () => void; compact?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="nav-upload-btn relative group flex items-center gap-2 rounded-full font-semibold text-white overflow-hidden transition-all duration-200"
      style={{ padding: compact ? "0.5rem 0.9rem" : "0.5rem 1.1rem", fontSize: "var(--font-size-nav)" }}
    >
      <span aria-hidden className="nav-upload-shimmer" />
      <Upload size={15} className="relative z-10 shrink-0" />
      <span className="relative z-10 hidden md:block">Upload documents</span>
      <span className="relative z-10 md:hidden">Upload</span>
    </button>
  );
}

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

  // Close mobile menu on route change
  useEffect(() => { setMobileOpen(false); }, [pathname]);

  return (
    <div className="fixed top-0 inset-x-0 z-40 pointer-events-none">
      <div className="mx-auto max-w-[1320px] px-4 sm:px-6">
        <motion.nav
          initial={{ y: -24, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="pointer-events-auto mt-4 flex items-center justify-between gap-3 rounded-full px-3 sm:px-4 py-2 transition-all duration-300"
          style={{
            background: scrolled ? "var(--nav-bg-strong)" : "var(--nav-bg)",
            border: "1px solid var(--nav-border)",
            backdropFilter: "blur(22px)",
            WebkitBackdropFilter: "blur(22px)",
            boxShadow: scrolled ? "var(--nav-shadow-strong)" : "var(--nav-shadow)",
          }}
        >
          <Brand />

          {/* Desktop nav */}
          <div className="hidden lg:flex items-center gap-1">
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

          <div className="flex items-center gap-2 shrink-0">
            <div className="hidden sm:block">
              <UploadButton onClick={onUploadClick} compact={scrolled} />
            </div>
            <ThemeToggle />

            {/* Mobile menu toggle */}
            <button
              type="button"
              onClick={() => setMobileOpen((o) => !o)}
              aria-label="Toggle menu"
              className="lg:hidden w-9 h-9 rounded-full flex items-center justify-center transition-all"
              style={{ background: "var(--btn-glass-bg)", border: "1px solid var(--btn-glass-border)", color: "var(--text-secondary)" }}
            >
              {mobileOpen ? <X size={16} /> : <Menu size={16} />}
            </button>
          </div>
        </motion.nav>

        {/* Mobile drawer */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.22 }}
              className="lg:hidden pointer-events-auto mt-2 rounded-3xl p-2 origin-top"
              style={{
                background: "var(--nav-bg-strong)",
                border: "1px solid var(--nav-border)",
                backdropFilter: "blur(22px)",
                WebkitBackdropFilter: "blur(22px)",
                boxShadow: "var(--nav-shadow-strong)",
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
