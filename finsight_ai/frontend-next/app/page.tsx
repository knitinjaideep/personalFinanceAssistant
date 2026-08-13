import { Suspense } from "react";
import HomePageClient from "@/components/home/HomePageClient";
import PageShell from "@/components/coral-ds/PageShell";
import LoadingState from "@/components/coral/LoadingState";

export default function HomePage() {
  return (
    <PageShell>
      {/* Suspense boundary required by Next.js App Router for any client
       * component that reads useSearchParams() (used by
       * hooks/useFinancialPeriod.ts for the Global Period Filter's URL
       * state — PR 05). */}
      <Suspense fallback={<LoadingState columns={6} rows={3} message="Loading…" />}>
        <HomePageClient />
      </Suspense>
    </PageShell>
  );
}
