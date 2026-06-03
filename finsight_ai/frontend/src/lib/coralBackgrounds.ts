export type CoralBackgroundKey =
  | "app"
  | "home"
  | "banking"
  | "investments"
  | "documents"
  | "chat";

export const coralPageBackgrounds = {
  app: {
    src: "/backgrounds/app-ocean-dark.png",
    overlay: "from-[#03111f]/70 via-[#03111f]/50 to-[#03111f]/95",
  },
  home: {
    src: "/backgrounds/home-hero.png",
    overlay: "from-[#03111f]/35 via-[#03111f]/15 to-[#03111f]/80",
  },
  banking: {
    src: "/backgrounds/banking-bg.png",
    overlay: "from-[#03111f]/55 via-[#06263a]/35 to-[#03111f]/90",
  },
  investments: {
    src: "/backgrounds/investments-bg.png",
    overlay: "from-[#03111f]/65 via-[#06263a]/45 to-[#03111f]/95",
  },
  documents: {
    src: "/backgrounds/documents-bg.png",
    overlay: "from-[#03111f]/70 via-[#03111f]/60 to-[#03111f]/95",
  },
  chat: {
    src: "/backgrounds/chat-bg.png",
    overlay: "from-[#03111f]/55 via-[#06263a]/35 to-[#03111f]/90",
  },
} as const;

export function getBackgroundForPage(activePage: string): CoralBackgroundKey {
  if (activePage === "banking") return "banking";
  if (activePage === "investments") return "investments";
  if (activePage === "documents") return "documents";
  if (activePage === "chat") return "chat";
  if (activePage === "overview" || activePage === "home") return "home";
  return "app";
}
