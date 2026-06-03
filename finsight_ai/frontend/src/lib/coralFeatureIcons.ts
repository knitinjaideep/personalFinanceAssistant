export type CoralFeatureIconKey =
  | "banking"
  | "investments"
  | "documents"
  | "chat";

export const coralFeatureIcons: Record<CoralFeatureIconKey, { src: string; alt: string }> = {
  banking: {
    src: "/icons/banking-icon.png",
    alt: "Ocean themed banking icon",
  },
  investments: {
    src: "/icons/investments-icon.png",
    alt: "Ocean themed investments icon",
  },
  documents: {
    src: "/icons/documents-icon.png",
    alt: "Ocean themed documents icon",
  },
  chat: {
    src: "/icons/chat-icon.png",
    alt: "Ocean themed chat icon",
  },
};

export function getCoralFeatureIcon(key: CoralFeatureIconKey) {
  return coralFeatureIcons[key];
}
