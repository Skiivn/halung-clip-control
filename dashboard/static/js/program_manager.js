// Program Manager UI — talks to /api/programs and /api/stations (see routes/program_manager.py)
(function () {
  'use strict';
  const MAX = 23;
  const $ = (id) => document.getElementById(id);
  let programs = [];
  let stations = [];

  async function api(method, url, body) {
    const r = await fetch(url, {
      method, headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({ ok: false, error: 'bad response' }));
    if (!r.ok || !data.ok) throw new Error(data.error || r.statusText);
    return data;
  }
  function say(text, bad) { $('msg').textContent = text; $('msg').style.color = bad ? '#c0392b' : '#27ae60'; }
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---- points grid -------------------------------------------------------
  function buildPoints() {
    $('points').innerHTML = Array.from({ length: MAX }, (_, i) =>
      `<label class="pt"><input type="checkbox" data-n="${i + 1}"> SW${i + 1}</label>`).join('');
    $('points').addEventListener('change', updateCount);
  }
  const checked = () => [...document.querySelectorAll('#points input:checked')].map((e) => +e.dataset.n);
  function setChecked(list) {
    document.querySelectorAll('#points input').forEach((e) => { e.checked = list.includes(+e.dataset.n); });
    updateCount();
  }
  function updateCount() { $('count').textContent = `(${checked().length}/${MAX} required)`; }

  // ---- programs ----------------------------------------------------------
  async function loadPrograms() {
    programs = (await api('GET', '/api/programs')).programs;
    $('programs-table').querySelector('tbody').innerHTML = programs.map((p) =>
      `<tr data-id="${p.id}" style="${p.active ? '' : 'opacity:.5'}">
        <td>${esc(p.name)}${p.active ? '' : ' (disabled)'}</td><td>${esc(p.layout)}</td><td>${esc(p.variant)}</td>
        <td>${p.required_switches.length}</td><td>${p.version}</td>
        <td><button class="btn" data-edit="${p.id}">Edit</button></td></tr>`).join('');
    renderStations();
  }
  function fill(p) {
    $('f-id').value = p ? p.id : '';
    $('editor-title').textContent = p ? `Edit: ${p.name} (v${p.version})` : 'New program';
    $('f-name').value = p ? p.name : '';
    $('f-layout').value = p ? p.layout || '' : '';
    $('f-variant').value = p ? p.variant || '' : '';
    $('f-target').value = p ? p.cycle_time_target : 30;
    $('f-swlock').checked = p ? !!p.swlock_required : true;
    $('f-butok').checked = p ? !!p.butok_required : true;
    $('btn-toggle').textContent = p && !p.active ? 'Enable' : 'Disable';
    setChecked(p ? p.required_switches : []);
    if (p) api('GET', `/api/programs/${p.id}/history`).then((h) => {
      $('history').innerHTML = h.history.map((x) =>
        `<li>v${x.version} ${esc(x.action)} — ${esc(x.changed_at)} (${esc(x.changed_by)})</li>`).join('');
    }); else $('history').innerHTML = '';
  }
  function form() {
    return {
      name: $('f-name').value, layout: $('f-layout').value, variant: $('f-variant').value,
      cycle_time_target: parseFloat($('f-target').value), required_switches: checked(),
      swlock_required: $('f-swlock').checked, butok_required: $('f-butok').checked,
    };
  }
  async function guarded(fn) { try { await fn(); } catch (e) { say(e.message, true); } }

  async function save() {
    const id = $('f-id').value;
    const r = id ? await api('PUT', `/api/programs/${id}`, form()) : await api('POST', '/api/programs', form());
    await loadPrograms(); fill(r.program); say(`Saved ${r.program.name} v${r.program.version}`);
  }
  async function duplicate() {
    const id = $('f-id').value; if (!id) return say('Select a program first', true);
    const r = await api('POST', `/api/programs/${id}/duplicate`, {});
    await loadPrograms(); fill(r.program); say(`Created ${r.program.name}`);
  }
  async function toggle() {
    const id = $('f-id').value; if (!id) return say('Select a program first', true);
    const cur = programs.find((p) => p.id == id);
    const r = await api('POST', `/api/programs/${id}/active`, { active: !cur.active });
    await loadPrograms(); fill(r.program); say(r.program.active ? 'Enabled' : 'Disabled');
  }

  // ---- stations ----------------------------------------------------------
  async function loadStations() { stations = (await api('GET', '/api/stations')).stations; renderStations(); }
  function renderStations() {
    const active = programs.filter((p) => p.active);
    const name = (id) => (programs.find((p) => p.id == id) || {}).name || '—';
    $('stations-table').querySelector('tbody').innerHTML = stations.map((s) => {
      const opts = active.map((p) => `<option value="${p.id}" ${p.id == s.manual_program_id ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
      const verified = s.program_verified ? '✔ verified' : (s.manual_program_id ? '… pending' : '—');
      return `<tr><td>${esc(s.code)}</td><td>${esc(s.hardware_profile)}</td>
        <td><span class="badge badge-${s.status.toLowerCase()}">${s.status}</span></td>
        <td>${esc(s.hardware_status)}</td>
        <td><select data-sel="${esc(s.code)}"><option value="">—</option>${opts}</select> v${s.assigned_version ?? '—'}</td>
        <td>${esc(name(s.active_program_id))} v${s.active_version ?? '—'} ${verified}</td>
        <td><button class="btn" data-send="${esc(s.code)}">Send</button></td></tr>`;
    }).join('');
  }
  async function send(code) {
    const pid = document.querySelector(`[data-sel="${code}"]`).value;
    if (!pid) return say('Choose a program', true);
    const r = await api('POST', `/api/stations/${code}/assign-program`, { program_id: +pid });
    await loadStations(); say(`${code}: v${r.version} queued — waiting for Raspberry acknowledgement`);
  }
  async function addStation() {
    await api('POST', '/api/stations', { code: $('s-code').value, hardware_profile: $('s-profile').value, expected_ip: $('s-ip').value });
    $('s-code').value = ''; await loadStations(); say('Station added');
  }

  // ---- wiring ------------------------------------------------------------
  buildPoints(); updateCount();
  $('btn-new').onclick = () => fill(null);
  $('btn-save').onclick = () => guarded(save);
  $('btn-dup').onclick = () => guarded(duplicate);
  $('btn-toggle').onclick = () => guarded(toggle);
  $('btn-all').onclick = () => setChecked(Array.from({ length: MAX }, (_, i) => i + 1));
  $('btn-none').onclick = () => setChecked([]);
  $('btn-add-station').onclick = () => guarded(addStation);
  $('programs-table').addEventListener('click', (e) => {
    const id = e.target.dataset.edit; if (id) fill(programs.find((p) => p.id == id));
  });
  $('stations-table').addEventListener('click', (e) => {
    const code = e.target.dataset.send; if (code) guarded(() => send(code));
  });
  guarded(async () => { await loadPrograms(); await loadStations(); });
  setInterval(() => guarded(loadStations), 5000); // live verification of Pi acknowledgements
})();
