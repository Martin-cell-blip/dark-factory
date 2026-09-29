// Money for people: the one formatting rule, the one decimal-input rule and the equal split.
// Amounts are integer minor units throughout; decimals only exist as text.

export function formatDecimal(minor, minorUnits) {
  const digits = String(minor);
  if (minorUnits === 0) return digits;
  const padded = digits.padStart(minorUnits + 1, "0");
  return `${padded.slice(0, -minorUnits)}.${padded.slice(-minorUnits)}`;
}

// "100.00 EUR", "1200 JPY", "1.500 BHD".
export function formatMoney(minor, wallet) {
  return `${formatDecimal(minor, wallet.minor_units)} ${wallet.currency}`;
}

const MAX_DIGITS = 15;

// A decimal as a person types it -> minor units, or a reason it cannot be one.
// "15", "15.5" and "15.00" are fine at 2 minor units; "15.005" is refused, never rounded.
export function parseAmount(text, minorUnits) {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(String(text).trim());
  if (!match) return { error: "Enter an amount such as 15 or 15.50." };
  const [, whole, fraction = ""] = match;
  if (fraction.length > minorUnits) {
    return { error: minorUnits === 0
      ? "This currency has no decimal places."
      : `Use at most ${minorUnits} decimal places.` };
  }
  const digits = (whole + fraction.padEnd(minorUnits, "0")).replace(/^0+(?=\d)/, "");
  if (digits.length > MAX_DIGITS) return { error: "That amount is too large." };
  const minor = Number(digits);
  if (minor < 1) return { error: "Enter an amount above zero." };
  return { minor };
}

// Stage-1 section 9: whole minor units, larger shares to the first participants.
export function equalSplit(amount, count) {
  const base = Math.floor(amount / count);
  const remainder = amount - base * count;
  return Array.from({ length: count }, (_, i) => base + (i < remainder ? 1 : 0));
}
