// A Compare | Records | Graph switch in the header, in place of Chainlit's chat-profile dropdown.
// It drives Chainlit's own profile select underneath, so switching still starts a new chat
// (and Chainlit still asks for confirmation when the current chat has messages).
(() => {
  const MODES = [
    { name: "Compare", hint: "both at once" },
    { name: "Records", hint: "records + search" },
    { name: "Graph", hint: "wander the graph" },
  ];
  const INFO = `
    <p class="wander-info-lead">Same company data, same Claude, same prompt. Only the store differs.</p>
    <dl>
      <dt>Compare</dt>
      <dd>Every question goes to both agents at the same time, and the two answers come back side by side,
          with what each one looked at and the work it took.</dd>
      <dt>Records</dt>
      <dd>An ordinary store: customer, ticket and document records with keyword search, the way most
          teams' systems look. The agent can search, open a record, and list records with filters.</dd>
      <dt>Graph</dt>
      <dd>The same data as a graph. The agent calls one <code>wander</code> tool that walks out from what
          you ask about, keeps where the paths converge more than chance would explain, and prunes the rest.</dd>
    </dl>
    <p class="wander-info-note">Each agent keeps its own conversation, so neither answer can see the other.
       Switching mode starts a new chat.</p>
    <button type="button" class="wander-info-readme">Open the readme</button>`;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const trigger = () => document.getElementById("chat-profiles");
  const current = () => (trigger() ? trigger().innerText.trim() : null);
  // Drive the dropdown with the keyboard: one clean open and one clean selection. (Replayed
  // mouse events could select twice, which cleared Chainlit's pending choice after a cancel.)
  const key = (el, k) => el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));

  async function choose(name) {
    const t = trigger();
    if (!t || current() === name) return;
    document.documentElement.classList.add("wander-switching");
    try {
      const findOption = () =>
        [...document.querySelectorAll('[role="option"]')].find((o) => o.innerText.trim() === name);
      let option = null;
      // Open the dropdown; if it doesn't open (e.g. right after a cancelled "new chat"), try once more.
      for (let attempt = 0; attempt < 2 && !option; attempt++) {
        if (t.getAttribute("aria-expanded") !== "true") {
          t.focus();
          key(t, "Enter");
        }
        for (let i = 0; i < 20 && !option; i++) {
          await sleep(25);
          option = findOption();
        }
      }
      if (option) {
        option.focus();
        key(option, "Enter");
      }
    } finally {
      await sleep(50);
      document.documentElement.classList.remove("wander-switching");
    }
  }

  function build() {
    const root = document.createElement("div");
    root.className = "wander-modes";
    root.innerHTML = `
      <div class="wander-radios" role="radiogroup" aria-label="Mode">
        ${MODES.map((m) => `
          <button type="button" role="radio" class="wander-radio" data-mode="${m.name}" aria-checked="false" tabindex="-1">
            <span class="wander-dot" aria-hidden="true"></span>
            <span class="wander-label">${m.name}</span>
            <span class="wander-hint">${m.hint}</span>
          </button>`).join("")}
      </div>
      <button type="button" class="wander-info-btn" aria-label="What's the difference?" aria-expanded="false"
              aria-controls="wander-info-panel" title="What's the difference?">
        <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
          <circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" stroke-width="1.5"/>
          <line x1="10" y1="9" x2="10" y2="14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
          <circle cx="10" cy="6.1" r="1.1" fill="currentColor"/>
        </svg>
      </button>
      <div id="wander-info-panel" class="wander-info" role="dialog" aria-label="The three modes" hidden>${INFO}</div>`;

    const radios = [...root.querySelectorAll(".wander-radio")];
    radios.forEach((r, i) => {
      r.addEventListener("click", () => choose(r.dataset.mode));
      r.addEventListener("keydown", (e) => {
        const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        if (!step) return;
        e.preventDefault();
        const next = radios[(i + step + radios.length) % radios.length];
        next.focus();
        choose(next.dataset.mode);
      });
    });

    const btn = root.querySelector(".wander-info-btn");
    const panel = root.querySelector(".wander-info");
    const setOpen = (open) => {
      panel.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
    };
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      setOpen(panel.hidden);
    });
    // On phones the Readme button is hidden to make room; this opens it from the panel instead.
    panel.querySelector(".wander-info-readme").addEventListener("click", () => {
      setOpen(false);
      document.getElementById("readme-button")?.click();
    });
    document.addEventListener("click", (e) => {
      if (!panel.hidden && !root.contains(e.target)) setOpen(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !panel.hidden) {
        setOpen(false);
        btn.focus();
      }
    });
    return root;
  }

  function sync(root) {
    const now = current();
    root.querySelectorAll(".wander-radio").forEach((r) => {
      const on = r.dataset.mode === now;
      r.setAttribute("aria-checked", String(on));
      r.tabIndex = on ? 0 : -1;
    });
  }

  function ensure() {
    const header = document.getElementById("header");
    if (!header || !trigger()) return;
    let root = header.querySelector(".wander-modes");
    if (!root) {
      root = build();
      header.appendChild(root);
      document.documentElement.classList.add("wander-has-switch");
    }
    sync(root);
  }

  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      ensure();
    });
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
  ensure();
})();
