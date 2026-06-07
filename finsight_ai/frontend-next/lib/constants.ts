export const ROUTES = {
  HOME: "/",
  BANKING: "/banking",
  INVESTMENTS: "/investments",
  DOCUMENTS: "/documents",
  CHAT: "/chat",
  // Upload is a global action (modal), not a route — no UPLOAD entry by design.
} as const;

export const API_PATHS = {
  DOCUMENTS: "/documents",
  DOCUMENTS_STATS: "/documents/stats",
  DOCUMENTS_UPLOAD: "/documents/upload-local",
  DOCUMENTS_SOURCES: "/documents/sources/list",
  DOCUMENTS_HEALTH: "/documents/ingestion-health",
  CHAT_QUERY: "/chat/query",
  DASHBOARD_SUMMARY: "/dashboard/summary",
  DASHBOARD_BANKING: "/dashboard/banking",
  DASHBOARD_INVESTMENTS: "/dashboard/investments",
  CATALOG_INSTITUTIONS: "/catalog/institutions",
  CATALOG_MONTHS: "/catalog/months",
  CATALOG_PREVIEW: "/catalog/destination-preview",
  HEALTH: "/health",
} as const;
