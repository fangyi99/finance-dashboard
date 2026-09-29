// The API sends Decimal values as strings (e.g. "12345.60"), so parse before doing maths.
export function formatMoney(
  value: string | number | null,
  currency: string,
): string {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  const [whole, cents] = Math.abs(num).toFixed(2).split(".");
  const withCommas = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${num < 0 ? "-" : ""}${withCommas}.${cents} ${currency}`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
