export type Client = { client_id: string; name: string; accounts_count: number; holdings_count: number };
export type BankRecord = { id: string; client_id: string; revision: number; created_at: string; updated_at: string; source_note: string; owner: string; [key: string]: unknown };
export type CurrencySummary = { currency: string; deals: number; pipeline_value: string | null; expected_fees: string | null; weighted_fees: string | null; value_coverage: number; fee_coverage: number; weighted_coverage: number };
export type Workspace = { clients: Client[]; deals: BankRecord[]; contacts: BankRecord[]; tasks: BankRecord[]; summary: { active_deals: number; open_tasks: number; overdue_tasks: number; by_currency: CurrencySummary[] }; meta: { timestamp: number; warnings: string[] } };
export const stages = { prospect: "Prospect", pitch: "Pitch", mandated: "Mandated", diligence: "Diligence", negotiation: "Negotiation", closed: "Closed", lost: "Lost", on_hold: "On hold" };
export const dealTypes = { sell_side: "Sell-side M&A", buy_side: "Buy-side M&A", capital_raise: "Capital raise", debt_advisory: "Debt advisory", restructuring: "Restructuring" };
export const taskStatuses = { open: "Open", in_progress: "In progress", blocked: "Blocked", completed: "Completed" };
export function money(value: unknown, currency: string): string {
  if (value == null || value === "" || !Number.isFinite(Number(value))) return "Not provided";
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(value));
}
export function calendarDate(value: unknown): string { return value ? new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "No date set"; }
export function downloadJson(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
