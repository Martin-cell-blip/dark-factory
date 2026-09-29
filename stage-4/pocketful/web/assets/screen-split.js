// Split: an amount among handles, with the shares previewed before anything is sent.
import { call, newKey } from "./api.js";
import { feedback, field, fill, h } from "./dom.js";
import { equalSplit, formatMoney, parseAmount } from "./money.js";
import { UNCERTAIN, reason } from "./words.js";

function handlesOf(text) {
  return text.split(",").map((part) => part.trim()).filter(Boolean);
}

export function splitScreen(root, ctx) {
  const amount = h("input", { testid: "split-amount", inputmode: "decimal", autocomplete: "off",
                              placeholder: "0.00" });
  const handles = h("input", { testid: "split-handles", autocomplete: "off", spellcheck: "false",
                               autocapitalize: "none", placeholder: `${ctx.me.handle}, ben, cat` });
  const note = h("input", { testid: "split-note", autocomplete: "off", placeholder: "Optional" });
  const preview = h("div", { "aria-live": "polite" });
  const status = h("div");
  const submit = h("button", { type: "submit", class: "button button-primary",
                               testid: "split-submit" }, "Split and send requests");
  let key = null;
  let changed = true;
  let busy = false;

  function showPreview() {
    const parsed = parseAmount(amount.value, ctx.me.minor_units);
    const people = handlesOf(handles.value);
    if (parsed.error || people.length === 0) {
      fill(preview, h("p", { class: "card-hint" },
        "Enter an amount and handles to see each person's share."));
      return;
    }
    const shares = equalSplit(parsed.minor, people.length);
    fill(preview, h("div", { class: "shares", testid: "split-preview" },
      h("span", { class: "field-hint" }, "Each share"),
      people.map((person, i) => h("div", { class: "share" },
        h("span", {}, person === ctx.me.handle ? `${person} (you)` : person),
        h("span", { class: "amount", testid: `split-share-${person}` },
          formatMoney(shares[i], ctx.me))))));
  }

  function refuse(message) {
    fill(status, feedback("refused", "split-error", "Split not sent", message));
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (busy) return;
    const parsed = parseAmount(amount.value, ctx.me.minor_units);
    const people = handlesOf(handles.value);
    if (parsed.error) return refuse(parsed.error);
    if (people.length === 0) return refuse("Add at least one handle, separated by commas.");
    if (changed || !key) {
      key = newKey();
      changed = false;
    }
    busy = true;
    submit.disabled = true;
    const outcome = await call("POST", "/splits", {
      body: { amount: parsed.minor, participant_handles: people, note: note.value }, key });
    busy = false;
    submit.disabled = false;
    if (outcome.kind === "ok") {
      const asked = outcome.data.requests.map((r) =>
        `${r.payer_handle} ${formatMoney(r.amount, ctx.me)}`);
      fill(status, feedback("success", "split-success",
        asked.length ? `Requests sent: ${asked.join(", ")}.` : "Split recorded; no one else to ask.",
        h("a", { href: "/requests" }, "See your requests")));
    } else if (outcome.kind === "refused") {
      refuse(reason(outcome));
    } else {
      fill(status, feedback("uncertain", "split-uncertain", "Not confirmed yet", UNCERTAIN));
    }
  }

  const form = h("form", { novalidate: true, onsubmit: onSubmit,
                           oninput: () => { changed = true; showPreview(); } },
    field(`Total to split (${ctx.me.currency})`, amount),
    field("Handles", handles, "Separate with commas, in order. Include yourself to take a share."),
    field("Note", note),
    preview,
    status,
    h("div", { class: "actions" }, submit));

  fill(root,
    h("h1", { class: "page-title" }, "Split a bill"),
    h("p", { class: "page-intro" },
      "You paid; everyone else gets a request for their share. Shares are as equal as the currency allows, and any extra goes to the first people listed."),
    h("section", { class: "card narrow-card" }, form));
  showPreview();
}
