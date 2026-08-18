export function formatBudget(budget: number | null): string {
  if (budget === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(
    budget,
  );
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(d);
}

export function priorityPillClass(priority: string | null): string {
  switch (priority) {
    case "hot":
      return "pill pill-hot";
    case "warm":
      return "pill pill-warm";
    case "cold":
      return "pill pill-cold";
    default:
      return "pill pill-neutral";
  }
}
