(() => {
  const ARTEN = ["Praktikum", "Werkstudent", "Trainee", "Junior / Berufseinstieg"];
  const $ = (id) => document.getElementById(id);
  const state = { tab: "alle", art: new Set(), ort: "", firma: "", fach: "", datum: "", ab: "", q: "" };
  let jobs = [];

  // Favoriten: nur im Browser (localStorage), Schlüssel ist der Stellen-Link
  const FAV_KEY = "studijobs-favoriten";
  const loadFavs = () => {
    try {
      const raw = JSON.parse(localStorage.getItem(FAV_KEY) || "[]");
      return new Set(Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : []);
    } catch { return new Set(); }
  };
  const saveFavs = () => {
    try { localStorage.setItem(FAV_KEY, JSON.stringify([...favs])); } catch { /* Speicher gesperrt: Favoriten gelten nur bis zum Neuladen */ }
  };
  const favs = loadFavs();

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso) => {
    const d = new Date(iso + "T00:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  };
  const daysAgo = (iso) => (Date.now() - new Date(iso + "T00:00:00").getTime()) / 864e5;
  const val = (v) => (!v || v === "k. A." ? '<span class="ka">k. A.</span>' : esc(v));
  const orte = (j) => j.standort.split(/\s*[\/;]\s*/).map((s) => s.trim()).filter(Boolean);

  function readUrl() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.tab = p.get("tab") === "fav" ? "fav" : "alle";
    (p.get("art") || "").split(",").filter(Boolean).forEach((a) => state.art.add(a));
    for (const k of ["ort", "firma", "fach", "datum", "ab", "q"]) state[k] = p.get(k) || "";
  }
  function writeUrl() {
    const p = new URLSearchParams();
    if (state.tab === "fav") p.set("tab", "fav");
    if (state.art.size) p.set("art", [...state.art].join(","));
    for (const k of ["ort", "firma", "fach", "datum", "ab", "q"]) if (state[k]) p.set(k, state[k]);
    history.replaceState(null, "", p.toString() ? "#" + p : location.pathname);
  }

  function fillSelect(el, values, allLabel, current) {
    el.innerHTML = `<option value="">${allLabel}</option>` +
      values.map((v) => `<option${v === current ? " selected" : ""}>${esc(v)}</option>`).join("");
  }

  function matches(j, skip) {
    if (skip !== "art" && state.art.size && !state.art.has(j.art)) return false;
    if (skip !== "ort" && state.ort && !orte(j).includes(state.ort)) return false;
    if (state.firma && j.firma !== state.firma) return false;
    if (state.fach && j.fachbereich !== state.fach) return false;
    if (state.datum && daysAgo(j.veroeffentlicht) > Number(state.datum)) return false;
    if (state.ab && j.veroeffentlicht < state.ab) return false;
    if (state.q) {
      const hay = `${j.titel} ${j.firma} ${j.fachbereich} ${j.standort}`.toLowerCase();
      if (!state.q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  function renderChips() {
    const pool = jobs.filter((j) => matches(j, "art"));
    $("f-art").innerHTML = ARTEN.map((a) => {
      const n = pool.filter((j) => j.art === a).length;
      return `<button type="button" class="chip" data-art="${esc(a)}" aria-pressed="${state.art.has(a)}">${esc(a)}<span class="n">${n}</span></button>`;
    }).join("");
  }

  function renderTabs() {
    const isFav = state.tab === "fav";
    $("tab-alle").setAttribute("aria-selected", String(!isFav));
    $("tab-fav").setAttribute("aria-selected", String(isFav));
    $("fav-n").textContent = jobs.filter((j) => favs.has(j.link)).length;
    $("filters").hidden = isFav;
  }

  function render() {
    const isFav = state.tab === "fav";
    renderTabs();
    renderChips();
    const list = isFav ? jobs.filter((j) => favs.has(j.link)) : jobs.filter((j) => matches(j));
    $("rows").innerHTML = list.map((j) => {
      const on = favs.has(j.link);
      return `
      <tr>
        <td class="c-title"><div class="c-row">
          <button type="button" class="fav" data-link="${esc(j.link)}" aria-pressed="${on}" aria-label="${on ? "Aus Favoriten entfernen" : "Als Favorit markieren"}: ${esc(j.titel)}" title="${on ? "Aus Favoriten entfernen" : "Als Favorit markieren"}">${on ? "★" : "☆"}</button>
          <div class="c-text"><div class="title">${esc(j.titel)}</div><div class="company">${esc(j.firma)}</div></div>
        </div></td>
        <td data-l="Art"><span class="badge">${esc(j.art)}</span></td>
        <td data-l="Fachbereich">${val(j.fachbereich)}</td>
        <td data-l="Standort">${val(j.standort)}</td>
        <td data-l="Start">${val(j.start)}</td>
        <td data-l="Zeitraum">${val(j.umfang)}</td>
        <td class="c-date" data-l="Veröffentlicht" title="${j.datum_geschaetzt ? "Zuerst erfasst am" : "Veröffentlicht am"}">${j.datum_geschaetzt ? "≈ " : ""}${fmtDate(j.veroeffentlicht)}</td>
        <td class="c-link"><a class="go" href="${esc(j.link)}" target="_blank" rel="noopener noreferrer">Zur Stelle ↗</a></td>
      </tr>`;
    }).join("");
    $("count").textContent = isFav
      ? `${list.length} ${list.length === 1 ? "Favorit" : "Favoriten"}`
      : `${list.length} von ${jobs.length} Stellen`;
    $("empty").hidden = isFav || list.length > 0;
    $("empty-fav").hidden = !isFav || list.length > 0;
    document.querySelector(".table-wrap").hidden = list.length === 0;
    writeUrl();
  }

  function renderSources(data) {
    const items = data.firmen.map((f) =>
      `<li><a href="${esc(f.career_url)}" target="_blank" rel="noopener noreferrer">${esc(f.name)}</a> (${f.stellen})` +
      (f.aktiv === false ? ` <span class="ka">· ${esc(f.note || "nicht abrufbar")}</span>`
        : f.ok ? "" : ` <span class="warn" title="${esc(f.note)}">· Abruf fehlgeschlagen</span>`) + "</li>").join("");
    $("sources").innerHTML = `<h2>Berücksichtigte Unternehmen</h2><ul>${items}</ul>`;
  }

  function init(data) {
    jobs = data.stellen;
    readUrl();
    const uniq = (arr) => [...new Set(arr)].sort((a, b) => a.localeCompare(b, "de"));
    fillSelect($("f-ort"), uniq(jobs.flatMap(orte).filter((o) => o !== "k. A.")), "Alle Orte", state.ort);
    const firmen = uniq([...data.firmen.map((f) => f.name), ...jobs.map((j) => j.firma)]);
    const anzahl = (n) => jobs.filter((j) => j.firma === n).length;
    $("f-firma").innerHTML = `<option value="">Alle Firmen</option>` + firmen.map((n) =>
      `<option value="${esc(n)}"${n === state.firma ? " selected" : ""}>${esc(n)} (${anzahl(n)})</option>`).join("");
    fillSelect($("f-fach"), uniq(jobs.map((j) => j.fachbereich)), "Alle Fachbereiche", state.fach);
    $("f-datum").value = state.datum;
    $("f-ab").value = state.ab;
    $("q").value = state.q;
    const upd = new Date(data.aktualisiert);
    $("meta").textContent = `${jobs.length} Stellen · zuletzt aktualisiert am ${upd.toLocaleDateString("de-DE", { day: "2-digit", month: "long", year: "numeric" })}`;
    renderSources(data);
    $("n-firmen").textContent = `${data.firmen.length} Arbeitgeber, z. B. Krones, Aumovio, Infineon`;

    $("rows").addEventListener("click", (e) => {
      const b = e.target.closest(".fav");
      if (!b) return;
      const link = b.dataset.link;
      favs.has(link) ? favs.delete(link) : favs.add(link);
      saveFavs();
      render();
    });
    document.querySelector(".tabs").addEventListener("click", (e) => {
      const t = e.target.closest(".tab");
      if (!t) return;
      state.tab = t.dataset.tab;
      render();
      window.scrollTo({ top: 0 });
    });
    window.addEventListener("storage", (e) => {
      if (e.key !== FAV_KEY) return;
      favs.clear();
      loadFavs().forEach((l) => favs.add(l));
      render();
    });

    $("f-art").addEventListener("click", (e) => {
      const b = e.target.closest(".chip");
      if (!b) return;
      const a = b.dataset.art;
      state.art.has(a) ? state.art.delete(a) : state.art.add(a);
      render();
    });
    const bind = (id, key) => $(id).addEventListener("input", (e) => { state[key] = e.target.value; render(); });
    bind("f-ort", "ort"); bind("f-firma", "firma"); bind("f-fach", "fach"); bind("f-datum", "datum"); bind("f-ab", "ab"); bind("q", "q");
    $("reset").addEventListener("click", () => {
      state.art.clear();
      for (const k of ["ort", "firma", "fach", "datum", "ab", "q"]) state[k] = "";
      for (const id of ["f-ort", "f-firma", "f-fach", "f-datum", "f-ab", "q"]) $(id).value = "";
      render();
    });
    render();
  }

  fetch("data/jobs.json", { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(init)
    .catch(() => {
      $("meta").textContent = "Die Stellen konnten nicht geladen werden. Bitte später erneut versuchen.";
      document.querySelector(".table-wrap").hidden = true;
    });
})();
