export function safeText(value: unknown, max = 24): string {
  return String(value ?? "")
    .replace(/[\u0000-\u001F<>]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}

export function bonusLabel(bonus: string | undefined): string {
  if (bonus === "double_points") {
    return "Double Points";
  }
  if (bonus === "gold_bonus") {
    return "Gold Bonus";
  }
  return "";
}
