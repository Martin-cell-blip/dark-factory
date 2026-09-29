// Start-up: who is signed in, then the screen named by the URL path.
import { call, session } from "./api.js";
import { feedback, fill, h } from "./dom.js";
import { loadingScreen, topbar } from "./layout.js";
import { authorizationsScreen } from "./screen-authorizations.js";
import { loginScreen, signupScreen } from "./screen-auth.js";
import { homeScreen } from "./screen-home.js";
import { requestsScreen } from "./screen-requests.js";
import { splitScreen } from "./screen-split.js";

const SCREENS = {
  "/": homeScreen,
  "/requests": requestsScreen,
  "/split": splitScreen,
  "/authorizations": authorizationsScreen,
  "/login": loginScreen,
  "/signup": signupScreen,
};
const SIGNED_OUT_OK = new Set(["/login", "/signup"]);

function renderScreen(path, main, me) {
  fill(document.getElementById("topbar"), topbar(me, path));
  (SCREENS[path] || homeScreen)(main, { me });
}

// The shell (top bar, navigation, log out) appears at once; the person and the screen's
// data fill in when GET /me answers, and an unreachable service is shown inside the shell.
async function start() {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const main = document.getElementById("main");
  if (!session.token) {
    if (SIGNED_OUT_OK.has(path)) renderScreen(path, main, null);
    else location.replace("/login");
    return;
  }
  fill(document.getElementById("topbar"), topbar(null, path, { pending: true }));
  fill(main, loadingScreen());
  const outcome = await call("GET", "/me");
  if (outcome.kind === "ok") {
    renderScreen(path, main, outcome.data);
  } else if (outcome.kind === "uncertain") {
    fill(main, h("section", { class: "card narrow-card" },
      feedback("refused", null, "Pocketful can't be reached right now",
        "Your money is safe. Check your connection, then try again."),
      h("div", { class: "actions card-foot" },
        h("button", { type: "button", class: "button button-primary",
                      onclick: () => location.reload() }, "Try again"))));
  } else if (SIGNED_OUT_OK.has(path)) {
    session.clear();
    renderScreen(path, main, null);
  }
}

start();
