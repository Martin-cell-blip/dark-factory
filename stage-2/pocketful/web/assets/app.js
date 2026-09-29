// Start-up: who is signed in, then the screen named by the URL path.
import { call, session } from "./api.js";
import { feedback, fill, h } from "./dom.js";
import { topbar } from "./layout.js";
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

async function signedInPerson() {
  if (!session.token) return { me: null };
  const outcome = await call("GET", "/me");
  if (outcome.kind === "ok") return { me: outcome.data };
  if (outcome.kind === "refused") session.clear();
  return { me: null, unreachable: outcome.kind === "uncertain" };
}

async function start() {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const main = document.getElementById("main");
  const { me, unreachable } = await signedInPerson();
  if (unreachable) {
    fill(main, feedback("refused", null, "Pocketful can't be reached right now",
      h("a", { href: path }, "Try again")));
    return;
  }
  if (!me && !SIGNED_OUT_OK.has(path)) {
    location.replace("/login");
    return;
  }
  fill(document.getElementById("topbar"), topbar(me, path));
  const screen = SCREENS[path] || homeScreen;
  screen(main, { me });
}

start();
