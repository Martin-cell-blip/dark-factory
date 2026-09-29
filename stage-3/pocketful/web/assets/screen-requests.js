// Requests: incoming (pay or decline) and outgoing (cancel).
import { call, latestWins, newKey, readAll } from "./api.js";
import { feedback, fill, h } from "./dom.js";
import { formatMoney } from "./money.js";
import { walletCard } from "./wallet.js";
import { UNCERTAIN, formatTime, reason, requestStatus } from "./words.js";

const DONE = {
  pay: (r, me) => `Paid ${formatMoney(r.amount, me)} to ${r.requester_handle}.`,
  decline: (r) => `Declined the request from ${r.requester_handle}.`,
  cancel: (r) => `Cancelled your request to ${r.payer_handle}.`,
};

const REFUSED = { pay: "Payment not sent", decline: "Not declined", cancel: "Not cancelled" };

export function requestsScreen(root, ctx) {
  const wallet = walletCard({ onRefresh: () => refresh() });
  const banner = h("div");
  const incoming = h("ul", { class: "list", testid: "incoming-list" });
  const outgoing = h("ul", { class: "list", testid: "outgoing-list" });
  const incomingNote = h("p", { class: "card-hint" });
  const outgoingNote = h("p", { class: "card-hint" });
  const empty = h("div");
  const payKeys = new Map();  // one key per request, so a retried pay is a replay

  async function act(kind, request, button) {
    button.disabled = true;
    let outcome;
    if (kind === "pay") {
      if (!payKeys.has(request.request_id)) payKeys.set(request.request_id, newKey());
      outcome = await call("POST", `/requests/${request.request_id}/pay`,
                           { body: {}, key: payKeys.get(request.request_id) });
    } else {
      outcome = await call("POST", `/requests/${request.request_id}/${kind}`);
    }
    if (outcome.kind === "uncertain") {
      button.disabled = false;
      fill(banner, feedback("uncertain", "request-uncertain", "Not confirmed yet", UNCERTAIN));
      return;
    }
    fill(banner, outcome.kind === "ok"
      ? feedback("success", "request-success", DONE[kind](request, ctx.me))
      : feedback("refused", "request-error", REFUSED[kind], reason(outcome)));
    await refresh();
  }

  function item(request, isIncoming) {
    const [label, badge] = requestStatus(request.status);
    const id = request.request_id;
    const pending = request.status === "pending";
    const words = isIncoming ? `${request.requester_handle} asked you`
      : `You asked ${request.payer_handle}`;
    const buttons = [];
    if (pending && isIncoming) {
      buttons.push(h("button", { type: "button", class: "button button-primary button-small",
                                 testid: `request-pay-${id}`,
                                 onclick: (e) => act("pay", request, e.currentTarget) }, "Pay"));
      buttons.push(h("button", { type: "button", class: "button button-danger button-small",
                                 testid: `request-decline-${id}`,
                                 onclick: (e) => act("decline", request, e.currentTarget) },
                     "Decline"));
    }
    if (pending && !isIncoming) {
      buttons.push(h("button", { type: "button", class: "button button-danger button-small",
                                 testid: `request-cancel-${id}`,
                                 onclick: (e) => act("cancel", request, e.currentTarget) },
                     "Cancel request"));
    }
    return h("li", { testid: `request-item-${id}`, "data-status": request.status },
      h("span", { class: `direction ${isIncoming ? "direction-out" : "direction-in"}`,
                  "aria-hidden": "true" }, isIncoming ? "←" : "→"),
      h("div", { class: "item-main" },
        h("div", { class: "item-parties" }, words),
        h("div", { class: "item-note" }, request.note)),
      h("div", { class: "item-side" },
        h("span", { class: "item-amount amount", testid: `request-amount-${id}` },
          formatMoney(request.amount, ctx.me)),
        h("span", { class: `badge ${badge}` }, label)),
      h("div", { class: "item-meta" },
        h("time", { datetime: request.created_at }, formatTime(request.created_at))),
      buttons.length ? h("div", { class: "item-actions" }, buttons) : null);
  }

  const refresh = latestWins(
    () => readAll(["/me", "/requests?direction=incoming&limit=200",
                   "/requests?direction=outgoing&limit=200"]),
    ([me, inbox, outbox]) => {
      ctx.me = me;
      wallet.show(me);
      fill(incoming, inbox.requests.map((r) => item(r, true)));
      fill(outgoing, outbox.requests.map((r) => item(r, false)));
      incomingNote.textContent = inbox.requests.length ? "" : "No one has asked you for money.";
      outgoingNote.textContent = outbox.requests.length ? "" : "You haven't asked anyone yet.";
      fill(empty, inbox.requests.length || outbox.requests.length ? null
        : h("div", { class: "empty", testid: "empty-requests" },
            h("strong", {}, "No requests yet"),
            "Ask someone for money from Home, or split a bill."));
    },
    () => {
      wallet.markStale();
      fill(banner, feedback("refused", null, "Couldn't load your requests",
        "Showing what we had. Use Refresh to try again."));
    });

  fill(root,
    h("h1", { class: "page-title" }, "Requests"),
    h("p", { class: "page-intro" }, "Money people have asked you for, and money you've asked for."),
    h("div", { class: "stack" },
      wallet.element,
      banner,
      empty,
      h("div", { class: "columns columns-two" },
        h("section", { class: "card", "aria-labelledby": "incoming-title" },
          h("h2", { class: "list-title", id: "incoming-title" }, "Asked of you"),
          incoming, incomingNote),
        h("section", { class: "card", "aria-labelledby": "outgoing-title" },
          h("h2", { class: "list-title", id: "outgoing-title" }, "You asked"),
          outgoing, outgoingNote))));
  refresh();
}
