// The pay, request and hold forms: handle, decimal amount, note (and visibility).
//
// Retries follow stage-1 section 7: the form keeps one Idempotency-Key until a field
// changes. Submitting the unchanged form again (after success, a refusal or an uncertain
// outcome) resends the same key and body, so money moves at most once.
import { call, newKey } from "./api.js";
import { feedback, field, fill, h } from "./dom.js";
import { parseAmount } from "./money.js";
import { UNCERTAIN, reason } from "./words.js";

function input(testid, props = {}) {
  return h("input", { testid, autocomplete: "off", spellcheck: "false", ...props });
}

// spec: prefix, title, hint, handleLabel, submitLabel, path, visibility (bool),
//       bodyFor({handle, minor, note, visibility}), successText(data), onDone()
export function moneyForm(ctx, spec) {
  const testid = (name) => `${spec.prefix}-${name}`;
  const handle = input(testid("handle"), { autocapitalize: "none", placeholder: "e.g. ben" });
  const amount = input(testid("amount"), { inputmode: "decimal", placeholder: "0.00" });
  const note = input(testid("note"), { placeholder: "Optional" });
  const visibility = spec.visibility
    ? h("select", { testid: testid("visibility") },
        h("option", { value: "public" }, "Public: anyone can see it"),
        h("option", { value: "private" }, "Private: only the two of you"))
    : null;
  const status = h("div", { class: "form-status" });
  const submit = h("button", { type: "submit", class: "button button-primary",
                               testid: testid("submit") }, spec.submitLabel);
  let key = null;
  let changed = true;
  let busy = false;

  function refuse(message) {
    fill(status, feedback("refused", testid("error"), spec.refusedTitle, message));
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (busy) return;
    const parsed = parseAmount(amount.value, ctx.me.minor_units);
    if (!handle.value.trim()) return refuse("Enter the handle of the person, e.g. ben.");
    if (parsed.error) return refuse(parsed.error);
    const body = spec.bodyFor({ handle: handle.value.trim(), minor: parsed.minor,
                                note: note.value, visibility: visibility && visibility.value });
    if (changed || !key) {
      key = newKey();
      changed = false;
    }
    busy = true;
    submit.disabled = true;
    submit.textContent = "Sending…";
    const outcome = await call("POST", spec.path, { body, key });
    busy = false;
    submit.disabled = false;
    submit.textContent = spec.submitLabel;
    if (outcome.kind === "ok") {
      fill(status, feedback("success", testid("success"), spec.successText(outcome.data)));
    } else if (outcome.kind === "refused") {
      refuse(reason(outcome));
    } else {
      fill(status, feedback("uncertain", testid("uncertain"), "Not confirmed yet", UNCERTAIN));
      return;
    }
    await spec.onDone();
  }

  const form = h("form", { novalidate: true, onsubmit: onSubmit,
                           oninput: () => { changed = true; } },
    h("div", { class: "field-row" },
      field(spec.handleLabel, handle),
      field(`Amount (${ctx.me.currency})`, amount)),
    field("Note", note),
    visibility ? field("Who can see it", visibility) : null,
    status,
    h("div", { class: "actions" }, submit));

  return h("section", { class: "card" },
    h("h2", { class: "card-title" }, spec.title),
    h("p", { class: "card-hint" }, spec.hint),
    form);
}
