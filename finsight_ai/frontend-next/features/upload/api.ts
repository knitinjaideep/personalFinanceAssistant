import { api } from "@/lib/api-client";

export interface AccountOption {
  account_slug: string;
  account_label: string;
  bucket: "banking" | "investments";
  parseable: boolean;
  supported_years: number[];
}

export interface InstitutionOption {
  institution_slug: string;
  institution_label: string;
  accounts: AccountOption[];
}

export interface MonthOption {
  month: number;
  label: string;
}

export interface DestinationPreview {
  rel_path: string;
  abs_path: string;
  filename: string;
  institution_label: string;
  account_label: string;
  bucket: string;
  error?: string;
}

export const catalogApi = {
  institutions: (): Promise<InstitutionOption[]> =>
    api.get<InstitutionOption[]>("/catalog/institutions"),

  months: (): Promise<MonthOption[]> =>
    api.get<MonthOption[]>("/catalog/months"),

  destinationPreview: (
    institutionSlug: string,
    accountSlug: string,
    year: number,
    month: number,
  ): Promise<DestinationPreview> =>
    api.get<DestinationPreview>("/catalog/destination-preview", {
      institution_slug: institutionSlug,
      account_slug: accountSlug,
      year,
      month,
    }),
};
