export type CoralFeatureIconKey =
  | "banking"
  | "investments"
  | "documents"
  | "chat";

type IconEntry = { src: string; lightSrc: string; alt: string };

export const coralFeatureIcons: Record<CoralFeatureIconKey, IconEntry> = {
  banking: {
    src: "/icons/banking-icon.png",
    lightSrc: "/icons/banking-icon-light.png",
    alt: "Ocean themed banking icon",
  },
  investments: {
    src: "/icons/investments-icon.png",
    lightSrc: "/icons/investments-icon-light.png",
    alt: "Ocean themed investments icon",
  },
  documents: {
    src: "/icons/documents-icon.png",
    lightSrc: "/icons/documents-icon-light.png",
    alt: "Ocean themed documents icon",
  },
  chat: {
    src: "/icons/chat-icon.png",
    lightSrc: "/icons/chat-icon-light.png",
    alt: "Ocean themed chat icon",
  },
};

export function getCoralFeatureIcon(key: CoralFeatureIconKey, isLight = false) {
  const entry = coralFeatureIcons[key];
  return { src: isLight ? entry.lightSrc : entry.src, alt: entry.alt };
}
