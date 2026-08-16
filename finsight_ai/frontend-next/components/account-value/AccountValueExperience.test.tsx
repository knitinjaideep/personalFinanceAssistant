import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
  AccountValueSummaryCard,
  AccountValueViewToggle,
  type AccountValueViewMode,
} from "@/components/account-value/AccountValueExperience";
import { buildAccountValueDataset, type AccountValueSnapshot } from "@/lib/accountValue";
import { useState } from "react";

const SNAPSHOTS: AccountValueSnapshot[] = [
  {
    account_id: "checking",
    account_name: "Checking",
    institution: "Chase",
    institution_type: "chase",
    account_type: "checking",
    domain: "banking",
    snapshot_date: "2026-07-31",
    value: 10000,
  },
  {
    account_id: "checking",
    account_name: "Checking",
    institution: "Chase",
    institution_type: "chase",
    account_type: "checking",
    domain: "banking",
    snapshot_date: "2026-08-31",
    value: 11000,
  },
];

function ExpandableHarness() {
  const account = buildAccountValueDataset(SNAPSHOTS).accounts[0];
  const [selected, setSelected] = useState(false);
  return (
    <AccountValueSummaryCard
      account={account}
      color="#2563eb"
      selected={selected}
      onSelect={() => setSelected((value) => !value)}
    />
  );
}

function ToggleHarness() {
  const [value, setValue] = useState<AccountValueViewMode>("line");
  return <AccountValueViewToggle value={value} onChange={setValue} />;
}

describe("account value interaction components", () => {
  it("uses button semantics and aria-expanded for summary-card expansion", async () => {
    const user = userEvent.setup();
    render(<ExpandableHarness />);

    const button = screen.getByRole("button", { name: /checking/i });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");

    await user.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps line/table view state independent from account expansion", async () => {
    const user = userEvent.setup();
    render(<ToggleHarness />);

    expect(screen.getByRole("button", { name: /line chart/i })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: /table view/i }));
    expect(screen.getByRole("button", { name: /table view/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /line chart/i })).toHaveAttribute("aria-pressed", "false");
  });
});

