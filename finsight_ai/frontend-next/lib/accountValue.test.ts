import { describe, expect, it } from "vitest";
import { buildAccountValueDataset, type AccountValueSnapshot } from "@/lib/accountValue";

describe("buildAccountValueDataset", () => {
  it("uses latest snapshot per account month and computes previous available month delta", () => {
    const snapshots: AccountValueSnapshot[] = [
      {
        account_id: "checking",
        account_name: "Checking",
        institution: "Chase",
        institution_type: "chase",
        account_type: "checking",
        domain: "banking",
        snapshot_date: "2026-07-14",
        value: 10000,
      },
      {
        account_id: "checking",
        account_name: "Checking",
        institution: "Chase",
        institution_type: "chase",
        account_type: "checking",
        domain: "banking",
        snapshot_date: "2026-08-05",
        value: 10800,
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

    const dataset = buildAccountValueDataset(snapshots);
    const checking = dataset.accounts[0];

    expect(checking.latest?.month).toBe("2026-08");
    expect(checking.latest?.value).toBe(11000);
    expect(checking.previous?.month).toBe("2026-07");
    expect(checking.change).toBe(1000);
    expect(dataset.totalLatestValue).toBe(11000);
  });

  it("does not fabricate missing months or carry values forward", () => {
    const snapshots: AccountValueSnapshot[] = [
      {
        account_id: "savings",
        account_name: "Savings",
        institution: "Marcus",
        institution_type: "marcus",
        account_type: "savings",
        domain: "banking",
        snapshot_date: "2026-06-30",
        value: 5000,
      },
      {
        account_id: "savings",
        account_name: "Savings",
        institution: "Marcus",
        institution_type: "marcus",
        account_type: "savings",
        domain: "banking",
        snapshot_date: "2026-08-31",
        value: 6500,
      },
    ];

    const dataset = buildAccountValueDataset(snapshots);

    expect(dataset.months).toEqual(["2026-06", "2026-08"]);
    expect(dataset.accounts[0].previous?.month).toBe("2026-06");
    expect(dataset.accounts[0].change).toBe(1500);
  });
});

