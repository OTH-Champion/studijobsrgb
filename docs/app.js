(() => {
  const ARTEN = ["Praktikum", "Werkstudent", "Trainee", "Junior / Berufseinstieg"];
  const $ = (id) => document.getElementById(id);
  const state = { art: new Set(), ort: "", firma: "", fach: "", datum: "", q: "" };
  let jobs = [];

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
    (p.get("art") || "").split(",").filter(Boolean).forEach((a) => state.art.add(a));
    for (const k of ["ort", "firma", "fach", "datum", "q"]) state[k] = p.get(k) || "";
  }
  function writeUrl() {
    const p = new URLSearchParams();
    if (state.art.size) p.set("art", [...state.art].join(","));
    for (const k of ["ort", "firma", "fach", "datum", "q"]) if (state[k]) p.set(k, state[k]);
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

  function render() {
    renderChips();
    const list = jobs.filter((j) => matches(j));
    $("rows").innerHTML = list.map((j) => `
      <tr>
        <td class="c-title"><div class="title">${esc(j.titel)}</div><div class="company">${esc(j.firma)}</div></td>
        <td data-l="Art"><span class="badge">${esc(j.art)}</span></td>
        <td data-l="Fachbereich">${val(j.fachbereich)}</td>
        <td data-l="Standort">${val(j.standort)}</td>
        <td data-l="Modell">${val(j.arbeitsmodell)}</td>
        <td data-l="Start">${val(j.start)}</td>
        <td data-l="Umfang">${val(j.umfang)}</td>
        <td class="c-date" data-l="Veröffentlicht" title="${j.datum_geschaetzt ? "Zuerst erfasst am" : "Veröffentlicht am"}">${j.datum_geschaetzt ? "≈ " : ""}${fmtDate(j.veroeffentlicht)}</td>
        <td class="c-link"><a class="go" href="${esc(j.link)}" target="_blank" rel="noopener noreferrer">Zur Stelle ↗</a></td>
      </tr>`).join("");
    $("count").textContent = `${list.length} von ${jobs.length} Stellen`;
    $("empty").hidden = list.length > 0;
    document.querySelector(".table-wrap").hidden = list.length === 0;
    writeUrl();
  }

  function renderSources(data) {
    const items = data.firmen.map((f) =>
      `<li><a href="${esc(f.career_url)}" target="_blank" rel="noopener noreferrer">${esc(f.name)}</a> (${f.stellen})` +
      (f.ok ? "" : ` <span class="warn" title="${esc(f.note)}">· Abruf fehlgeschlagen</span>`) + "</li>").join("");
    $("sources").innerHTML = `<h2>Berücksichtigte Unternehmen</h2><ul>${items}</ul>`;
  }

  function init(data) {
    jobs = data.stellen;
    readUrl();
    const uniq = (arr) => [...new Set(arr)].sort((a, b) => a.localeCompare(b, "de"));
    fillSelect($("f-ort"), uniq(jobs.flatMap(orte).filter((o) => o !== "k. A.")), "Alle Orte", state.ort);
    fillSelect($("f-firma"), uniq(jobs.map((j) => j.firma)), "Alle Firmen", state.firma);
    fillSelect($("f-fach"), uniq(jobs.map((j) => j.fachbereich)), "Alle Fachbereiche", state.fach);
    $("f-datum").value = state.datum;
    $("q").value = state.q;
    const upd = new Date(data.aktualisiert);
    $("meta").textContent = `${jobs.length} Stellen · zuletzt aktualisiert am ${upd.toLocaleDateString("de-DE", { day: "2-digit", month: "long", year: "numeric" })}`;
    renderSources(data);

    $("f-art").addEventListener("click", (e) => {
      const b = e.target.closest(".chip");
      if (!b) return;
      const a = b.dataset.art;
      state.art.has(a) ? state.art.delete(a) : state.art.add(a);
      render();
    });
    const bind = (id, key) => $(id).addEventListener("input", (e) => { state[key] = e.target.value; render(); });
    bind("f-ort", "ort"); bind("f-firma", "firma"); bind("f-fach", "fach"); bind("f-datum", "datum"); bind("q", "q");
    $("reset").addEventListener("click", () => {
      state.art.clear();
      for (const k of ["ort", "firma", "fach", "datum", "q"]) state[k] = "";
      for (const id of ["f-ort", "f-firma", "f-fach", "f-datum", "q"]) $(id).value = "";
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
