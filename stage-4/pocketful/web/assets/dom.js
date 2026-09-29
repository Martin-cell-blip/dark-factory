// A tiny element builder: h("p", {class: "x", testid: "y", onclick: fn}, "text", child).

function append(element, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : String(child));
  }
}

export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (name === "class") element.className = value;
    else if (name === "testid") element.dataset.testid = value;
    else if (name.startsWith("on")) element.addEventListener(name.slice(2), value);
    else element.setAttribute(name, value === true ? "" : value);
  }
  append(element, children);
  return element;
}

export function fill(element, ...children) {
  element.replaceChildren();
  append(element, children);
}

let fieldCount = 0;

// A labelled field. The label is always visible and tied to the control.
export function field(label, control, hint) {
  fieldCount += 1;
  control.id = control.id || `field-${fieldCount}`;
  return h("div", { class: "field" },
    h("label", { for: control.id }, label),
    control,
    hint ? h("span", { class: "field-hint" }, hint) : null);
}

// Feedback boxes: kind is "success", "refused" or "uncertain" (DESIGN.md states).
export function feedback(kind, testid, title, detail) {
  return h("div", { class: `feedback feedback-${kind}`, testid,
                    role: kind === "success" ? "status" : "alert" },
    h("div", {}, h("strong", {}, title), detail ? h("span", {}, detail) : null));
}
