// The wallet card: available funds as the headline, total and held beside it.
import { fill, h } from "./dom.js";
import { formatMoney } from "./money.js";

function skeleton() {
  return [h("span", { class: "skeleton skeleton-hero" }), h("span", { class: "skeleton skeleton-line" })];
}

export function walletCard({ onRefresh }) {
  const body = h("div", { "aria-busy": "true" }, skeleton());
  const stale = h("p", { class: "stale-note", role: "status", hidden: true },
    "Not up to date. Use Refresh to try again.");
  const refresh = h("button", { type: "button", class: "button button-quiet button-small",
                                testid: "wallet-refresh", onclick: onRefresh }, "Refresh");
  const element = h("section", { class: "card", "aria-labelledby": "wallet-title" },
    h("div", { class: "wallet-head" },
      h("h2", { class: "wallet-label", id: "wallet-title" }, "Available to spend"), refresh),
    body, stale);

  return {
    element,
    show(me) {
      stale.hidden = true;
      body.removeAttribute("aria-busy");
      fill(body,
        h("strong", { class: "wallet-available amount", testid: "wallet-available",
                      "data-amount": me.available }, formatMoney(me.available, me)),
        h("div", { class: "wallet-lines" },
          h("span", {}, "Total balance ",
            h("span", { class: "amount", testid: "wallet-balance", "data-amount": me.balance },
              formatMoney(me.balance, me))),
          me.held > 0
            ? h("span", { class: "badge badge-held" }, "On hold ",
                h("span", { class: "amount", testid: "wallet-held", "data-amount": me.held },
                  formatMoney(me.held, me)))
            : null));
    },
    markStale() { stale.hidden = false; },
  };
}
