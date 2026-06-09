/* OLAB Project Dashboard — vanilla JS, no dependencies, works offline. */
(function () {
  "use strict";

  var DATA_CANDIDATES = ["data/projects.json", "../data/projects.json", "projects.json"];
  var STATUS_ORDER = ["active", "writing", "submitted", "published", "paused"];

  var FILTERS = [
    { key: "all", label: "All", test: function () { return true; } },
    { key: "active", label: "Active", test: function (p) { return p.status === "active"; } },
    { key: "writing", label: "Writing", test: function (p) { return p.status === "writing"; } },
    { key: "submitted", label: "Submitted", test: function (p) { return p.status === "submitted"; } },
    { key: "published", label: "Published", test: function (p) { return p.status === "published"; } },
    { key: "open", label: "Open to collaborators", test: function (p) { return (p.collab_state || (p.open_to_collaborators ? "open" : "closed")) !== "closed"; } }
  ];

  var AVATAR_COLORS = ["#7c3aed", "#2563eb", "#0f8a4f", "#b45309", "#be185d", "#0891b2", "#4f46e5", "#ca8a04"];

  var state = { projects: [], activeFilter: "all", view: "grid" };

  // ---- helpers -----------------------------------------------------------
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function initials(name) {
    var parts = String(name).trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function colorFor(str) {
    var sum = 0;
    for (var i = 0; i < str.length; i++) sum = (sum + str.charCodeAt(i)) % 9973;
    return AVATAR_COLORS[sum % AVATAR_COLORS.length];
  }

  function formatDate(iso) {
    if (!iso) return "";
    var d = new Date(iso + "T00:00:00");
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  function timeAgo(iso) {
    if (!iso) return "";
    var then = new Date(iso);
    if (isNaN(then.getTime())) return "";
    var secs = Math.floor((Date.now() - then.getTime()) / 1000);
    if (secs < 60) return "just now";
    var mins = Math.floor(secs / 60);
    if (mins < 60) return mins + " min ago";
    var hrs = Math.floor(mins / 60);
    if (hrs < 24) return hrs + (hrs === 1 ? " hour ago" : " hours ago");
    var days = Math.floor(hrs / 24);
    if (days < 30) return days + (days === 1 ? " day ago" : " days ago");
    return formatDate(String(iso).slice(0, 10));
  }

  function collabState(p) {
    return p.collab_state || (p.open_to_collaborators ? "open" : "closed");
  }

  function collabChip(p) {
    var c = collabState(p);
    var LABEL = { open: "🤝 open", urgent: "🚨 help wanted", closed: "🔒 closed" };
    var TITLE = {
      open: "Open to collaborators",
      urgent: "Urgently seeking collaborators",
      closed: "Not seeking collaborators"
    };
    var chip = el("span", "collab-chip " + c, LABEL[c] || c);
    chip.title = TITLE[c] || "";
    return chip;
  }

  function personChip(name, isLead) {
    var chip = el("span", "chip" + (isLead ? " lead" : ""));
    var av = el("span", "avatar", initials(name));
    av.style.background = colorFor(name);
    chip.appendChild(av);
    chip.appendChild(document.createTextNode(name));
    return chip;
  }

  // ---- shared card body (description, people, meta, open box, footer) -----
  function appendBody(p, container) {
    if (p.description) container.appendChild(el("p", "card-desc", p.description));

    if (p.lead || (Array.isArray(p.contributors) && p.contributors.length)) {
      var people = el("div", "people");
      if (p.lead) {
        var leadLine = el("div", "person-line");
        leadLine.appendChild(el("span", "people-label", "Lead"));
        leadLine.appendChild(personChip(p.lead, true));
        people.appendChild(leadLine);
      }
      if (Array.isArray(p.contributors) && p.contributors.length) {
        var collabLine = el("div", "person-line");
        collabLine.appendChild(el("span", "people-label", "Collaborators"));
        var chips = el("div", "chips");
        p.contributors.forEach(function (name) { chips.appendChild(personChip(name, false)); });
        collabLine.appendChild(chips);
        people.appendChild(collabLine);
      }
      container.appendChild(people);
    }

    var metaItems = [
      ["Venue", p.venue],
      ["Deadline", p.deadline ? formatDate(p.deadline) : ""],
      ["Grant", p.grant],
      ["Collaboration", p.collaboration]
    ].filter(function (item) { return item[1]; });
    if (metaItems.length) {
      var meta = el("div", "meta-row");
      metaItems.forEach(function (item) {
        var span = el("span");
        span.appendChild(el("span", "label", item[0]));
        span.appendChild(document.createTextNode(item[1]));
        meta.appendChild(span);
      });
      container.appendChild(meta);
    }

    var collab = collabState(p);
    if (collab !== "closed") {
      var box = el("div", "open-box" + (collab === "urgent" ? " urgent" : ""));
      box.appendChild(el("div", "open-title",
        collab === "urgent" ? "🚨 Urgently seeking collaborators" : "🤝 Open to collaborators"));
      if (Array.isArray(p.needed_skills) && p.needed_skills.length) {
        var sc = el("div", "skill-chips");
        p.needed_skills.forEach(function (skill) { sc.appendChild(el("span", "skill-chip", skill)); });
        box.appendChild(sc);
      }
      container.appendChild(box);
    }

    var foot = el("div", "card-foot");
    if (p.github_repo) {
      var link = el("a", "repo-link");
      link.href = "https://github.com/" + p.github_repo;
      link.target = "_blank";
      link.rel = "noopener";
      link.appendChild(document.createTextNode("⌥ " + p.github_repo));
      foot.appendChild(link);
    } else {
      foot.appendChild(el("span"));
    }
    if (p.last_updated) foot.appendChild(el("span", "updated", "updated " + timeAgo(p.last_updated)));
    container.appendChild(foot);
  }

  // ---- grid view: the original full card ---------------------------------
  function buildGridCard(p) {
    var card = el("article", "card grid-card");
    var status = (p.status || "active").toLowerCase();

    var head = el("div", "card-head");
    head.appendChild(el("h2", "card-name", p.name || "Untitled project"));
    var hMeta = el("div", "head-meta");
    hMeta.appendChild(collabChip(p));
    hMeta.appendChild(el("span", "pill " + status, status));
    head.appendChild(hMeta);
    card.appendChild(head);

    if (p.deadline_soon) {
      var banner = el("div", "banner");
      banner.appendChild(document.createTextNode("⏰ Deadline soon"));
      if (p.deadline) banner.appendChild(document.createTextNode(" · " + formatDate(p.deadline)));
      card.appendChild(banner);
    }

    appendBody(p, card);
    return card;
  }

  // ---- list view: collapsible row (lead shown in the collapsed header) ----
  function buildListCard(p) {
    var card = el("details", "card list-card");
    var status = (p.status || "active").toLowerCase();

    var summary = el("summary", "card-summary");
    var main = el("span", "summary-main");
    main.appendChild(el("span", "card-name", p.name || "Untitled project"));
    if (p.lead) main.appendChild(el("span", "lead-sub", "Lead · " + p.lead));
    summary.appendChild(main);

    var sMeta = el("span", "summary-meta");
    sMeta.appendChild(collabChip(p));
    if (p.deadline_soon) sMeta.appendChild(el("span", "soon-chip", "⏰ soon"));
    sMeta.appendChild(el("span", "pill " + status, status));
    sMeta.appendChild(el("span", "chevron", "▸"));
    summary.appendChild(sMeta);
    card.appendChild(summary);

    var detail = el("div", "card-detail");
    appendBody(p, detail);
    card.appendChild(detail);
    return card;
  }

  // ---- rendering ---------------------------------------------------------
  function renderFilters() {
    var nav = document.getElementById("filters");
    nav.innerHTML = "";
    FILTERS.forEach(function (f) {
      var count = state.projects.filter(f.test).length;
      if (f.key !== "all" && f.key !== "open" && count === 0) return;
      var btn = el("button", "filter-btn");
      btn.type = "button";
      btn.setAttribute("aria-pressed", String(state.activeFilter === f.key));
      btn.appendChild(document.createTextNode(f.label));
      btn.appendChild(el("span", "count", String(count)));
      btn.addEventListener("click", function () {
        state.activeFilter = f.key;
        render();
      });
      nav.appendChild(btn);
    });
  }

  function render() {
    renderFilters();
    var grid = document.getElementById("grid");
    var empty = document.getElementById("empty");
    grid.className = "grid view-" + state.view;
    grid.innerHTML = "";

    var filter = FILTERS.filter(function (f) { return f.key === state.activeFilter; })[0] || FILTERS[0];
    var visible = state.projects
      .filter(filter.test)
      .sort(function (a, b) {
        var sa = STATUS_ORDER.indexOf(a.status), sb = STATUS_ORDER.indexOf(b.status);
        if (sa !== sb) return sa - sb;
        return (a.name || "").localeCompare(b.name || "");
      });

    empty.hidden = visible.length !== 0;
    var build = state.view === "grid" ? buildGridCard : buildListCard;
    visible.forEach(function (p) { grid.appendChild(build(p)); });
  }

  // ---- layout (grid / list) toggle --------------------------------------
  function updateViewButton() {
    // The button shows the view it switches TO when clicked.
    var label = document.getElementById("view-label");
    var btn = document.getElementById("view-toggle");
    if (state.view === "grid") { label.textContent = "☰ List view"; btn.title = "Switch to list view"; }
    else { label.textContent = "▦ Grid view"; btn.title = "Switch to grid view"; }
  }

  function initView() {
    var stored = null;
    try { stored = localStorage.getItem("dashboard-view"); } catch (e) {}
    if (stored === "grid" || stored === "list") state.view = stored;
    updateViewButton();
    document.getElementById("view-toggle").addEventListener("click", function () {
      state.view = state.view === "grid" ? "list" : "grid";
      try { localStorage.setItem("dashboard-view", state.view); } catch (e) {}
      updateViewButton();
      render();
    });
  }

  // ---- data loading ------------------------------------------------------
  function fetchFirst(paths) {
    var i = 0;
    function attempt() {
      if (i >= paths.length) return Promise.reject(new Error("projects.json not found"));
      var url = paths[i++] + "?t=" + Date.now();
      return fetch(url, { cache: "no-store" }).then(function (res) {
        if (!res.ok) throw new Error(res.status + " for " + url);
        return res.json();
      }).catch(function () { return attempt(); });
    }
    return attempt();
  }

  function load() {
    var statusLine = document.getElementById("status-line");
    statusLine.textContent = "Loading projects…";
    fetchFirst(DATA_CANDIDATES).then(function (data) {
      state.projects = Array.isArray(data) ? data : [];
      var n = state.projects.length;
      statusLine.textContent = n + (n === 1 ? " project" : " projects") + " tracked.";
      document.getElementById("footer-meta").textContent =
        "Self-hosted lab dashboard · static site · no external services.";
      render();
    }).catch(function (err) {
      statusLine.textContent = "Could not load projects.json — " + err.message;
      document.getElementById("empty").hidden = false;
      document.getElementById("empty").textContent =
        "No data yet. Add a project.yaml or run the aggregator to populate the dashboard.";
    });
  }

  // ---- theme toggle ------------------------------------------------------
  function initTheme() {
    var root = document.documentElement;
    var stored = null;
    try { stored = localStorage.getItem("dashboard-theme"); } catch (e) {}
    if (stored === "light" || stored === "dark") root.setAttribute("data-theme", stored);

    document.getElementById("theme-toggle").addEventListener("click", function () {
      var current = root.getAttribute("data-theme");
      if (current === "auto") {
        var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
        current = prefersDark ? "dark" : "light";
      }
      var next = current === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("dashboard-theme", next); } catch (e) {}
    });
  }

  // ---- boot --------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    initView();
    load();
  });
})();
