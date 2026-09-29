// Log in and sign up. A successful one stores the token and opens Home.
import { call, session } from "./api.js";
import { feedback, field, fill, h } from "./dom.js";
import { reason } from "./words.js";

function authScreen(root, { title, intro, fields, submitTestid, submitLabel, path, bodyOf, other }) {
  const status = h("div");
  const submit = h("button", { type: "submit", class: "button button-primary",
                               testid: submitTestid }, submitLabel);

  async function onSubmit(event) {
    event.preventDefault();
    submit.disabled = true;
    const outcome = await call("POST", path, { body: bodyOf(), signedIn: false });
    submit.disabled = false;
    if (outcome.kind === "ok") {
      session.save(outcome.data.token);
      location.assign("/");
      return;
    }
    fill(status, feedback("refused", "auth-error", "That didn't work",
      outcome.kind === "refused" ? reason(outcome)
        : "We couldn't reach Pocketful. Check your connection and try again."));
  }

  fill(root, h("section", { class: "card narrow" },
    h("h1", { class: "page-title" }, title),
    h("p", { class: "page-intro" }, intro),
    h("form", { novalidate: true, onsubmit: onSubmit }, fields, status,
      h("div", { class: "actions" }, submit)),
    h("p", { class: "card-foot" }, other)));
}

export function loginScreen(root) {
  const email = h("input", { type: "email", testid: "login-email", autocomplete: "email" });
  const password = h("input", { type: "password", testid: "login-password",
                                autocomplete: "current-password" });
  authScreen(root, {
    title: "Log in", intro: "Welcome back to Pocketful.",
    fields: [field("Email", email), field("Password", password)],
    submitTestid: "login-submit", submitLabel: "Log in", path: "/auth/login",
    bodyOf: () => ({ email: email.value.trim(), password: password.value }),
    other: ["New here? ", h("a", { href: "/signup" }, "Create an account")],
  });
}

export function signupScreen(root) {
  const email = h("input", { type: "email", testid: "signup-email", autocomplete: "email" });
  const password = h("input", { type: "password", testid: "signup-password",
                                autocomplete: "new-password" });
  const name = h("input", { testid: "signup-display-name", autocomplete: "name" });
  authScreen(root, {
    title: "Create your account",
    intro: "Your handle comes from your email: ann.lee@example.com becomes ann_lee.",
    fields: [field("Your name", name), field("Email", email),
             field("Password", password, "At least 8 characters.")],
    submitTestid: "signup-submit", submitLabel: "Create account", path: "/auth/signup",
    bodyOf: () => ({ email: email.value.trim(), password: password.value,
                     display_name: name.value.trim() }),
    other: ["Already have an account? ", h("a", { href: "/login" }, "Log in")],
  });
}
