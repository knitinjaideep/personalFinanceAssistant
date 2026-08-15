import { Suspense } from "react";
import PageShell from "@/components/coral-ds/PageShell";
import LoadingState from "@/components/coral/LoadingState";
import MonthlyClosePageClient from "@/components/overview/MonthlyClosePageClient";

export default function MonthlyClosePage() {
  return (
    <PageShell>
      <Suspense fallback={<LoadingState columns={5} rows={3} message="Loading monthly close..." />}>
        <MonthlyClosePageClient />
      </Suspense>
    </PageShell>
  );
}
