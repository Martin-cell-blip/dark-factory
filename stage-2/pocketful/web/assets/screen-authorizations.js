// Holds (authorisations): reserve money for someone to collect later, collect or release.
import { call, latestWins, newKey, readAll } from "./api.js";
import { feedback, field, fill, h } from "./dom.js";
import { formatDecimal, formatMoney, parseAmount } from "./money.js";
import { moneyForm } from "./money-form.js";
import { walletCard } from "./wallet.js";
import { UNCERTAIN, expiryText, formatTime, holdStatus, reason } from "./words.js";

// The authorise form, also offered on Home.
export function holdForm(ctx, onDone) {
  return moneyForm(ctx, {
    prefix: "authorize", title: "Hold for someone", submitLabel: "Place hold",
    handleLabel: "For (handle)",
    hint: "Reserve money now; they collect it later. Held money can't be spent meanwhile.",
    refusedTitle: "Hold not placed", path: "/authorizations", visibility: true,
    bodyFor: ({ handle, minor, note, visibility }) =>
      ({ to_handle: handle, amount: minor, note, visibility }),
    successText: (hold) =>
      `Holding ${formatMoney(hold.amount, ctx.me)} for ${hold.to_handle}. ${expiryText(hold.expires_at)}.`,
    onDone,
  });
}

export function authorizationsScreen(root, ctx) {
  const wallet = walletCard({ onRefresh: () => refresh() });
  const banner = h("div");
  const list = h("ul", { class: "list", testid: "authorization-list" });
  const empty = h("div");
  const captureKeys = new Map();  // id -> {amount, key}: an unchanged retry is a replay

  function keyFor(id, amount) {
    const known = captureKeys.get(id);
    if (known && known.amount === amount) return known.key;
    const key = newKey();
    captureKeys.set(id, { amount, key });
    return key;
  }

  async function settle(outcome, success, refusedTitle, button) {
    if (outcome.kind === "uncertain") {
      button.disabled = false;
      fill(banner, feedback("uncertain", "authorization-uncertain", "Not confirmed yet", UNCERTAIN));
      return;
    }
    fill(banner, outcome.kind === "ok"
      ? feedback("success", "authorization-success", success(outcome.data))
      : feedback("refused", "authorization-error", refusedTitle, reason(outcome)));
    await refresh();
  }

  async function collect(hold, input, button) {
    const parsed = parseAmount(input.value, ctx.me.minor_units);
    if (parsed.error) {
      fill(banner, feedback("refused", "authorization-error", "Nothing collected", parsed.error));
      return;
    }
    button.disabled = true;
    const id = hold.authorization_id;
    const outcome = await call("POST", `/authorizations/${id}/capture`,
                               { body: { amount: parsed.minor }, key: keyFor(id, parsed.minor) });
    await settle(outcome, (payment) =>
      `Collected ${formatMoney(payment.amount, ctx.me)} from ${payment.from_handle}.`,
    "Nothing collected", button);
  }

  async function release(hold, button) {
    button.disabled = true;
    const outcome = await call("POST", `/authorizations/${hold.authorization_id}/void`);
    await settle(outcome, (voided) =>
      `Released the hold for ${voided.to_handle}; ${formatMoney(voided.amount - voided.captured_amount, ctx.me)} is available again.`,
    "Hold not released", button);
  }

  function item(hold) {
    const id = hold.authorization_id;
    const outgoing = hold.from_user_id === ctx.me.user_id;
    const open = hold.status === "open";
    const [label, badge] = holdStatus(hold.status);
    const actions = [];
    if (open && !outgoing) {
      const amount = h("input", { testid: `authorization-capture-amount-${id}`, inputmode: "decimal",
                                  autocomplete: "off",
                                  value: formatDecimal(hold.remaining_amount, ctx.me.minor_units) });
      actions.push(field(`Amount to collect (${ctx.me.currency})`, amount));
      actions.push(h("button", { type: "button", class: "button button-primary button-small",
                                 testid: `authorization-capture-${id}`,
                                 onclick: (e) => collect(hold, amount, e.currentTarget) }, "Collect"));
    }
    if (open && outgoing) {
      actions.push(h("button", { type: "button", class: "button button-danger button-small",
                                 testid: `authorization-void-${id}`,
                                 onclick: (e) => release(hold, e.currentTarget) }, "Release hold"));
    }
    return h("li", { testid: `authorization-item-${id}`, "data-status": hold.status },
      h("span", { class: `direction ${outgoing ? "direction-out" : "direction-in"}`,
                  "aria-hidden": "true" }, outgoing ? "↑" : "↓"),
      h("div", { class: "item-main" },
        h("div", { class: "item-parties" }, `${hold.from_handle} → ${hold.to_handle}`),
        h("div", { class: "item-note" }, hold.note)),
      h("div", { class: "item-side" },
        h("span", { class: "item-amount amount", testid: `authorization-amount-${id}` },
          formatMoney(hold.amount, ctx.me)),
        h("span", { class: `badge ${badge}` }, label)),
      h("div", { class: "item-meta" },
        hold.status === "captured"
          ? h("span", {}, "Collected ", h("span", { class: "amount", testid: `authorization-captured-${id}` },
              formatMoney(hold.captured_amount, ctx.me)))
          : null,
        open && hold.captured_amount > 0
          ? h("span", {}, `Collected so far ${formatMoney(hold.captured_amount, ctx.me)}, `
              + `${formatMoney(hold.remaining_amount, ctx.me)} still held`)
          : null,
        h("span", {}, expiryText(hold.expires_at)),
        h("time", { class: "tabular", datetime: hold.expires_at,
                    testid: `authorization-expires-${id}` }, hold.expires_at),
        h("span", {}, "Placed ", h("time", { datetime: hold.created_at }, formatTime(hold.created_at)))),
      actions.length ? h("div", { class: "item-actions" }, actions) : null);
  }

  const refresh = latestWins(
    () => readAll(["/me", "/authorizations?limit=200"]),
    ([me, holds]) => {
      ctx.me = me;
      wallet.show(me);
      fill(list, holds.authorizations.map(item));
      fill(empty, holds.authorizations.length ? null
        : h("div", { class: "empty", testid: "empty-authorizations" },
            h("strong", {}, "No holds yet"),
            "Holds you place, and holds placed for you, appear here."));
    },
    () => {
      wallet.markStale();
      fill(banner, feedback("refused", null, "Couldn't load your holds",
        "Showing what we had. Use Refresh to try again."));
    });

  fill(root,
    h("h1", { class: "page-title" }, "Holds"),
    h("p", { class: "page-intro" },
      "Money set aside for someone to collect. It stays yours until they collect it, you release it, or it expires."),
    h("div", { class: "columns columns-home" },
      h("div", { class: "stack" }, wallet.element, holdForm(ctx, refresh)),
      h("section", { class: "card", "aria-labelledby": "holds-title" },
        h("h2", { class: "card-title", id: "holds-title" }, "Your holds"),
        h("p", { class: "card-hint" }, "Newest first. Collect holds placed for you; release your own."),
        banner, empty, list)));
  refresh();
}
