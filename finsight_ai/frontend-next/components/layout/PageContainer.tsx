import { clsx } from "clsx";
import type { ReactNode } from "react";

interface PageContainerProps {
  children: ReactNode;
  fullHeight?: boolean;
  narrow?: boolean;
  className?: string;
}

export default function PageContainer({
  children,
  fullHeight = false,
  narrow = false,
  className,
}: PageContainerProps) {
  return (
    <section
      className={clsx(
        "mx-auto w-full pb-12",
        narrow ? "max-w-[1000px]" : "max-w-[1320px]",
        fullHeight ? "h-full flex flex-col" : "",
        className
      )}
      style={{
        paddingLeft: "var(--page-x-padding)",
        paddingRight: "var(--page-x-padding)",
      }}
    >
      {children}
    </section>
  );
}
