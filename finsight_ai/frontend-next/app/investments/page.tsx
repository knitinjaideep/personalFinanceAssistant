import InvestmentsPageClient from "@/components/investments/InvestmentsPageClient";

export default function InvestmentsPage() {
  return (
    <div
      className="flex flex-col"
      style={{ marginTop: "var(--nav-height)", height: "calc(100dvh - var(--nav-height))" }}
    >
      <div
        className="flex-1 min-h-0 overflow-y-auto"
        style={{
          maskImage: "linear-gradient(to bottom, transparent 0px, black 32px)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent 0px, black 32px)",
        }}
      >
        <div
          className="mx-auto w-full max-w-[1320px] pb-12"
          style={{ paddingLeft: "var(--page-x-padding)", paddingRight: "var(--page-x-padding)", paddingTop: "1.5rem" }}
        >
          <InvestmentsPageClient />
        </div>
      </div>
    </div>
  );
}
