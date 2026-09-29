// Home: wallet, the pay / request / hold forms and the activity feed.
import { latestWins, readAll } from "./api.js";
import { feedback, fill, h } from "./dom.js";
import { formatMoney } from "./money.js";
import { moneyForm } from "./money-form.js";
import { walletCard } from "./wallet.js";
import { formatTime } from "./words.js";
import { holdForm } from "./screen-authorizations.js";

function activityItem(payment, me) {
  const sent = payment.from_user_id === me.user_id;
  const received = payment.to_user_id === me.user_id;
  const [glyph, tone, word] = sent ? ["↑", "direction-out", "Sent"]
    : received ? ["↓", "direction-in", "Received"] : ["↔", "", "Between others"];
  const origin = payment.authorization_id ? "Collected hold"
    : payment.request_id ? "Paid request" : payment.settlement_id ? "Settlement" : null;
  const id = payment.payment_id;
  return h("li", { testid: `activity-item-${id}`, "data-visibility": payment.visibility },
    h("span", { class: `direction ${tone}`, "aria-hidden": "true" }, glyph),
    h("div", { class: "item-main" },
      h("div", { class: "item-parties", testid: `activity-parties-${id}` },
        `${payment.from_handle} → ${payment.to_handle}`),
      h("div", { class: "item-note", testid: `activity-note-${id}` }, payment.note)),
    h("div", { class: "item-side" },
      h("span", { class: "item-amount amount", testid: `activity-amount-${id}` },
        formatMoney(payment.amount, me))),
    h("div", { class: "item-meta" },
      h("span", {}, word),
      h("time", { datetime: payment.created_at }, formatTime(payment.created_at)),
      payment.visibility === "private" ? h("span", { class: "badge badge-private" }, "Private") : null,
      origin ? h("span", { class: "badge badge-neutral" }, origin) : null));
}

function renderFeed(container, payments, me) {
  container.removeAttribute("aria-busy");
  if (payments.length === 0) {
    fill(container, h("div", { class: "empty", testid: "empty-activity" },
      h("strong", {}, "No activity yet"),
      "Payments you send or receive, and public payments, show up here."));
    return;
  }
  fill(container, h("ul", { class: "list", testid: "activity-list" },
    payments.map((payment) => activityItem(payment, me))));
}

export function homeScreen(root, ctx) {
  const wallet = walletCard({ onRefresh: () => refresh() });
  const feedProblem = h("div");
  const feed = h("div", { "aria-busy": "true" },
    h("span", { class: "skeleton skeleton-line" }), h("span", { class: "skeleton skeleton-line" }));

  const refresh = latestWins(
    () => readAll(["/me", "/activity?limit=50"]),
    ([me, activity]) => {
      ctx.me = me;
      wallet.show(me);
      fill(feedProblem);
      renderFeed(feed, activity.payments, me);
    },
    () => {
      wallet.markStale();
      fill(feedProblem, feedback("refused", null, "Couldn't load your latest activity",
        "Showing what we had. Use Refresh to try again."));
    });

  const pay = moneyForm(ctx, {
    prefix: "pay", title: "Pay", submitLabel: "Send money", handleLabel: "To (handle)",
    hint: "Money moves straight away.", refusedTitle: "Payment not sent",
    path: "/payments", visibility: true,
    bodyFor: ({ handle, minor, note, visibility }) =>
      ({ to_handle: handle, amount: minor, note, visibility }),
    successText: (payment) => `Sent ${formatMoney(payment.amount, ctx.me)} to ${payment.to_handle}.`,
    onDone: refresh,
  });
  const ask = moneyForm(ctx, {
    prefix: "request", title: "Request", submitLabel: "Send request",
    handleLabel: "From (handle)", hint: "They can pay or decline it from their requests.",
    refusedTitle: "Request not sent", path: "/requests", visibility: false,
    bodyFor: ({ handle, minor, note }) => ({ payer_handle: handle, amount: minor, note }),
    successText: (request) =>
      `Asked ${request.payer_handle} for ${formatMoney(request.amount, ctx.me)}.`,
    onDone: refresh,
  });

  fill(root,
    h("h1", { class: "visually-hidden" }, "Home"),
    h("div", { class: "columns columns-home" },
      h("div", { class: "stack" }, wallet.element,
        h("a", { class: "jump-link", href: "#activity-title" }, "Jump to your activity ↓"),
        pay, ask, holdForm(ctx, refresh)),
      h("section", { class: "card", "aria-labelledby": "activity-title" },
        h("h2", { class: "card-title", id: "activity-title" }, "Activity"),
        h("p", { class: "card-hint" }, "Your payments and public payments, newest first."),
        feedProblem, feed)));
  refresh();
}
