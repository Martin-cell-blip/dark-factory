// The top bar shared by every screen: brand, navigation and the signed-in person.
import { session } from "./api.js";
import { h } from "./dom.js";

const DESTINATIONS = [
  ["/", "Home"],
  ["/requests", "Requests"],
  ["/split", "Split"],
  ["/authorizations", "Holds"],
];

function logOut() {
  session.clear();
  location.assign("/login");
}

export function topbar(me, path) {
  const brand = h("a", { class: "brand", href: me ? "/" : "/login" },
    h("span", { class: "brand-mark", "aria-hidden": "true" }, "P"), "Pocketful");
  if (!me) {
    const [href, label] = path === "/login" ? ["/signup", "Create account"] : ["/login", "Log in"];
    return h("div", { class: "topbar-inner" }, brand,
      h("div", { class: "who" }, h("a", { class: "button button-quiet button-small", href }, label)));
  }
  return h("div", { class: "topbar-inner" }, brand,
    h("nav", { class: "nav", "aria-label": "Main" },
      DESTINATIONS.map(([href, label]) =>
        h("a", { href, "aria-current": href === path ? "page" : null }, label))),
    h("div", { class: "who" },
      h("div", { class: "who-name", testid: "current-user" },
        h("strong", {}, me.display_name),
        h("span", { class: "who-handle" }, "@", h("span", { testid: "current-handle" }, me.handle))),
      h("button", { type: "button", class: "button button-quiet button-small",
                    testid: "logout-button", onclick: logOut }, "Log out")));
}
