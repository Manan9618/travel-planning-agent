// Only the aggregate budget figures (BudgetEvaluation's totals/category
// amounts) are actually currency-converted by the backend
// (BudgetOptimizer.evaluate) — individual line-item costs (a flight price,
// a hotel's price_per_night, an attraction's ticket cost) stay raw USD as
// returned by their providers, same as before. This formatter is only used
// where the underlying number really is in `currencyCode`.
export function formatCurrency(amount: number, currencyCode: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currencyCode,
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    // Not a real ISO 4217 code (shouldn't normally happen — the LLM parser
    // is expected to produce one) — fall back rather than crash the panel.
    return `${currencyCode} ${amount.toFixed(0)}`
  }
}
