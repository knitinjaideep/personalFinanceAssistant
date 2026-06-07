export type CoralBackgroundKey =
  | "app"
  | "home"
  | "banking"
  | "investments"
  | "documents"
  | "chat";

export const coralPageBackgrounds: Record<
  CoralBackgroundKey,
  { src: string; lightSrc: string; overlay: string }
> = {
  app: {
    src: "/backgrounds/app-ocean-dark.png",
    lightSrc: "/backgrounds/home-hero-light.png",
    overlay: "from-[#03111f]/70 via-[#03111f]/50 to-[#03111f]/95",
  },
  home: {
    src: "/backgrounds/home-hero.png",
    lightSrc: "/backgrounds/home-hero-light.png",
    overlay: "from-[#03111f]/35 via-[#03111f]/15 to-[#03111f]/80",
  },
  banking: {
    src: "/backgrounds/banking-bg.png",
    lightSrc: "/backgrounds/home-hero-light.png",
    overlay: "from-[#03111f]/55 via-[#06263a]/35 to-[#03111f]/90",
  },
  investments: {
    src: "/backgrounds/investments-bg.png",
    lightSrc: "/backgrounds/home-hero-light.png",
    overlay: "from-[#03111f]/65 via-[#06263a]/45 to-[#03111f]/95",
  },
  documents: {
    src: "/backgrounds/documents-bg.png",
    lightSrc: "/backgrounds/home-hero-light.png",
    overlay: "from-[#03111f]/70 via-[#03111f]/60 to-[#03111f]/95",
  },
  chat: {
    src: "/backgrounds/chat-bg.png",
    lightSrc: "/backgrounds/home-hero-light.png",
    overlay: "from-[#03111f]/55 via-[#06263a]/35 to-[#03111f]/90",
  },
};

export function getBackgroundKeyForPath(pathname: string): CoralBackgroundKey {
  if (pathname.startsWith("/banking"))     return "banking";
  if (pathname.startsWith("/investments")) return "investments";
  if (pathname.startsWith("/documents"))  return "documents";
  if (pathname.startsWith("/chat"))       return "chat";
  if (pathname === "/")                   return "home";
  return "app";
}
