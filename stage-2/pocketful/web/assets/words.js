// Words for people: times, statuses and the reasons behind refusals.

// The screens are in English, so dates are too, whatever the browser locale.
const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

export function formatTime(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : dateTime.format(date);
}

// One wording for every hold: "Expires 30 Sept 2026, 03:18 (in 2 h)" or "Expired …",
// always in the reader's local time.
export function expiryText(iso) {
  const minutes = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  if (minutes <= 0) return `Expired ${formatTime(iso)}`;
  const soon = minutes < 60 ? `${minutes} min` : `${Math.round(minutes / 60)} h`;
  return `Expires ${formatTime(iso)} (in ${soon})`;
}

const REASONS = {
  insufficient_funds: "Not enough available funds. Money on hold can't be spent.",
  self_payment: "You can't send money to yourself.",
  self_request: "You can't ask yourself for money.",
  not_found: "We couldn't find that. Check the handle and try again.",
  forbidden: "You can't do that with this item.",
  request_not_pending: "This request is no longer pending.",
  authorization_not_open: "This hold is no longer open.",
  authorization_expired: "This hold has expired, so nothing can be collected.",
  capture_exceeds_authorization: "That's more than what's left on hold.",
  idempotency_key_reuse: "This was already sent with different details. Change a field and try again.",
  missing_idempotency_key: "Something went wrong preparing the request. Try again.",
  email_taken: "An account with this email already exists. Log in instead.",
  handle_taken: "The handle from this email is taken. Try another email address.",
  unauthenticated: "That email and password don't match an account.",
  payload_too_large: "That's too long to send.",
};

export function reason(outcome) {
  if (REASONS[outcome.code]) return REASONS[outcome.code];
  if (outcome.code === "validation_failed" && outcome.message) {
    return `Please check the details: ${outcome.message}.`;
  }
  return "That didn't go through. Please check the details and try again.";
}

export const UNCERTAIN = "We couldn't confirm the result. It may have gone through. "
  + "Submit again without changing anything to finish safely: it won't be sent twice.";

const REQUEST_STATUS = {
  pending: ["Pending", "badge-pending"],
  paid: ["Paid", "badge-success"],
  declined: ["Declined", "badge-neutral"],
  cancelled: ["Cancelled", "badge-neutral"],
};

const HOLD_STATUS = {
  open: ["On hold", "badge-held"],
  captured: ["Collected", "badge-success"],
  voided: ["Released", "badge-neutral"],
  expired: ["Expired", "badge-neutral"],
};

export function requestStatus(status) { return REQUEST_STATUS[status] || [status, "badge-neutral"]; }
export function holdStatus(status) { return HOLD_STATUS[status] || [status, "badge-neutral"]; }
