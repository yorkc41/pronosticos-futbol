// Goleo - página pública. Lee data/index.json, data/<fecha>.json y config.json
(function(){
const $ = id => document.getElementById(id);
const P = v => Math.round((v || 0) * 100);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bust = () => '?v=' + Math.floor(Date.now() / 600000); // refresca cada 10 min
const LIVE = new Set(['1H','HT','2H','ET','BT','P','LIVE','INT']);
const FINISHED = new Set(['FT','AET','PEN']);
let config = {}, index = null, day = 'hoy', data = null, open = null;

async function getJSON(url){ const r = await fetch(url + bust()); if(!r.ok) throw new Error(url); return r.json(); }

// Inserta el código de un anuncio (ej. AdSense) y ejecuta sus <script>
function injectHTML(el, html){
  el.innerHTML = html;
  el.querySelectorAll('script').forEach(old => {
    const s = document.createElement('script');
    [...old.attributes].forEach(a => s.setAttribute(a.name, a.value));
    s.textContent = old.textContent;
    old.replaceWith(s);
  });
}
function setupAds(){
  const ads = config.ads || {};
  if (ads.head) { const box = document.createElement('div'); injectHTML(box, ads.head); [...box.childNodes].forEach(n => document.head.appendChild(n)); }
  document.querySelectorAll('.ad[data-slot]').forEach(el => fillAd(el, el.dataset.slot));
}
function fillAd(el, slot){
  const code = (config.ads || {})[slot];
  if (code) { el.classList.remove('ph'); injectHTML(el, code); }
  else if (config.showAdPlaceholders) { el.classList.add('ph'); el.innerHTML = `<small>Publicidad</small>${{top:'728 × 90',side1:'300 × 250',side2:'300 × 250',inline:'Banner en la lista'}[slot]||''}`; }
  else el.innerHTML = '';
}

const pc = (v, th = .6) => `<span class="pct ${v >= th ? 'hi' : (v < .35 ? 'lo' : '')}">${P(v)}</span>`;
const form = s => `<div class="form">${[...(s||'')].map(c => `<b class="${c}">${c==='W'?'G':c==='D'?'E':'P'}</b>`).join('')}</div>`;
const pickName = c => ({'1':'Gana local','2':'Gana visitante','+2.5':'Más de 2.5 goles','-2.5':'Menos de 2.5 goles','AM':'Ambos marcan'}[c] || c);
const logo = t => t.logo ? `<img src="${esc(t.logo)}" alt="" loading="lazy">` : '';

function timeCell(m){
  if (LIVE.has(m.status)) return `<span class="live">${m.status === 'HT' ? 'Desc.' : 'En vivo'}</span>`;
  if (FINISHED.has(m.status)) return 'Final';
  if (['PST','CANC','ABD'].includes(m.status)) return 'Aplaz.';
  return esc(m.time);
}

function render(){
  const hidden = new Set((config.hidden || []).map(String));
  const all = (data?.matches || []).filter(m => !hidden.has(String(m.id)));
  const leagues = [...new Set(all.map(m => m.league.name))];
  const sel = $('f-league'), cur = sel.value;
  sel.innerHTML = '<option value="">Todas</option>' + leagues.map(l => `<option${l===cur?' selected':''}>${esc(l)}</option>`).join('');

  const d = data ? new Date(data.date + 'T12:00:00') : new Date();
  $('title').textContent = {ayer:'Partidos de ayer', hoy:'Partidos de hoy', manana:'Partidos de mañana'}[day];
  const upd = data?.updated ? ' · actualizado ' + new Date(data.updated).toLocaleString('es-CO', {hour:'numeric', minute:'2-digit', day:'numeric', month:'short'}) : '';
  $('subtitle').textContent = d.toLocaleDateString('es-CO', {weekday:'long', day:'numeric', month:'long'}) + ` · ${all.length} partidos · hora Colombia` + upd;

  // pick destacado (el administrador lo elige en el panel)
  const feat = all.filter(m => (config.featured || []).map(String).includes(String(m.id)) && m.pick);
  $('featured').innerHTML = feat.map(m => `<div class="feat"><span class="lbl">Pick del día</span>
    <div class="who">${esc(m.home.name)} vs ${esc(m.away.name)}<small>${esc(m.league.name)} · ${esc(m.time)}</small></div>
    <div><div class="big">${esc(m.pick.code)}</div><small>${pickName(m.pick.code)} · ${P(m.pick.prob)} %</small></div></div>`).join('');

  // récord de aciertos (días ya jugados)
  const graded = all.filter(m => typeof m.hit === 'boolean');
  $('record').hidden = !graded.length;
  if (graded.length) {
    const w = graded.filter(m => m.hit).length;
    const strong = graded.filter(m => m.cons >= 2), sw = strong.filter(m => m.hit).length;
    $('record').innerHTML = `<span>Aciertos del día <b>${w}/${graded.length}</b> (${P(w/graded.length)} %)</span>` +
      (strong.length ? `<span>Con 2 o más fuentes de acuerdo <b>${sw}/${strong.length}</b></span>` : '');
  }

  let list = all.filter(m => (!sel.value || m.league.name === sel.value) && (!$('f-over').checked || (m.p && m.p.o25 >= .6)));
  const s = $('f-sort').value;
  const key = {time: m => m.league.name + m.time, o25: m => -(m.p?.o25 || 0), btts: m => -(m.p?.btts || 0), cards: m => -(m.cards || 0), cons: m => -(m.cons || 0) - (m.pick?.prob || 0)}[s];
  list.sort((a, b) => key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0);

  if (!data) { $('list').innerHTML = '<div class="empty">No hay datos para este día todavía. Se actualizan cada madrugada.</div>'; return; }
  if (!list.length) { $('list').innerHTML = `<div class="empty">${all.length ? 'Ningún partido cumple el filtro. Quita "Solo Over 2.5 ≥ 60 %" o cambia de liga.' : 'No hay partidos de las ligas que seguimos en este día.'}</div>`; return; }

  const groups = s === 'time' ? leagues.map(l => [l, list.filter(m => m.league.name === l)]).filter(g => g[1].length)
                              : [['Ordenados: ' + $('f-sort').selectedOptions[0].text.toLowerCase(), list]];
  let html = '';
  groups.forEach(([name, items], gi) => {
    const country = items[0].league.country && s === 'time' ? items[0].league.country : '';
    html += `<section class="league"><div class="league-h">${esc(name)} <span>${esc(country)}</span></div><div class="tbl-wrap"><table>
    <thead><tr><th>Hora</th><th style="text-align:left">Partido</th>
    <th class="grp">1</th><th>X</th><th>2</th>
    <th class="grp">+1.5</th><th>+2.5</th><th>+3.5</th><th>AM</th><th>xG</th>
    <th class="grp">Tarj. esp.</th><th>+3.5 T</th><th>+4.5 T</th>
    <th class="grp">Pick</th><th>Fuentes</th></tr></thead><tbody>`;
    items.forEach(m => {
      const id = String(m.id), isOpen = open === id, p = m.p || {};
      const sc = m.score || [];
      const pickCls = m.hit === true ? 'win' : m.hit === false ? 'loss' : '';
      html += `<tr class="m" tabindex="0" data-id="${id}" aria-expanded="${isOpen}">
        <td class="time">${timeCell(m)}</td>
        <td class="teams"><span class="t ${p['1'] > p['2'] ? 'fav' : ''}">${logo(m.home)}${esc(m.home.name)}${sc.length ? `<span class="g">${sc[0]}</span>` : ''}</span>
          <span class="t ${p['2'] > p['1'] ? 'fav' : ''}">${logo(m.away)}${esc(m.away.name)}${sc.length ? `<span class="g">${sc[1]}</span>` : ''}</span></td>` +
        (m.p ? `<td class="grp">${pc(p['1'], .55)}</td><td>${pc(p.x, .4)}</td><td>${pc(p['2'], .55)}</td>
        <td class="grp">${pc(p.o15, .75)}</td><td>${pc(p.o25)}</td><td>${pc(p.o35, .45)}</td><td>${pc(p.btts)}</td>
        <td>${(m.xg[0] + m.xg[1]).toFixed(2)}</td>
        <td class="grp"><span class="card"></span>${m.cards.toFixed(1)}</td><td>${pc(p.c35, .7)}</td><td>${pc(p.c45)}</td>
        <td class="grp"><span class="pick ${pickCls}" title="${pickName(m.pick.code)}">${esc(m.pick.code)}</span> <small>${P(m.pick.prob)}%</small></td>
        <td><span class="cons" title="${m.cons} de 3 fuentes apoyan el pick">${[0,1,2].map(i => `<i class="${i < m.cons ? 'on' : ''}"></i>`).join('')}</span></td>`
        : `<td class="grp" colspan="13" style="color:var(--muted)">Sin estadísticas suficientes para este partido</td>`) + `</tr>`;
      if (isOpen && m.p) {
        const ch = m.checks || {};
        html += `<tr class="det"><td colspan="15"><div class="det-grid">
          <div><h4>Resultado</h4>
            <div class="kv"><span>${esc(m.home.name)}</span><em>${P(p['1'])} %</em></div>
            <div class="kv"><span>Empate</span><em>${P(p.x)} %</em></div>
            <div class="kv"><span>${esc(m.away.name)}</span><em>${P(p['2'])} %</em></div>
            <div class="bar"><span style="width:${P(p['1'])}%"></span><span style="width:${P(p.x)}%"></span><span style="width:${P(p['2'])}%"></span></div>
            <div class="kv" style="margin-top:8px"><span>Marcador más probable</span><em>${m.likely[0]} – ${m.likely[1]}</em></div>
          </div>
          <div><h4>Goles</h4>
            <div class="kv"><span>xG ${esc(m.home.name)}</span><em>${m.xg[0].toFixed(2)}</em></div>
            <div class="kv"><span>xG ${esc(m.away.name)}</span><em>${m.xg[1].toFixed(2)}</em></div>
            <div class="kv"><span>Menos de 2.5</span><em>${P(1 - p.o25)} %</em></div>
            <div class="kv"><span>Ambos NO marcan</span><em>${P(1 - p.btts)} %</em></div>
          </div>
          <div><h4>Tarjetas</h4>
            <div class="kv"><span>Esperadas</span><em>${m.cards.toFixed(1)}</em></div>
            <div class="kv"><span>Más de 3.5</span><em>${P(p.c35)} %</em></div>
            <div class="kv"><span>Menos de 4.5</span><em>${P(1 - p.c45)} %</em></div>
            ${m.referee ? `<div class="kv"><span>Árbitro</span><em>${esc(m.referee)}</em></div>` : ''}
          </div>
          <div><h4>Fuentes del pick: ${pickName(m.pick.code)}</h4>
            <div class="kv"><span>Modelo Goleo</span><em>${ch.modelo ? 'Sí' : 'No'}</em></div>
            <div class="kv"><span>Predicción externa</span><em>${m.api ? (ch.api ? 'Sí' : 'No') : 'Sin dato'}</em></div>
            <div class="kv"><span>Historial reciente</span><em>${ch.historial ? 'Sí' : 'No'}</em></div>
          </div>
          <div><h4>Forma (últimos 5)</h4>
            <div class="kv"><span>${esc(m.home.name)}</span>${form(m.home.form)}</div>
            <div class="kv"><span>${esc(m.away.name)}</span>${form(m.away.form)}</div>
          </div>
        </div></td></tr>`;
      }
    });
    html += `</tbody></table></div></section>`;
    if (gi === 0 && groups.length > 1) html += `<div class="ad inline" data-slot="inline"></div>`;
  });
  $('list').innerHTML = html;
  const inl = $('list').querySelector('.ad.inline'); if (inl) fillAd(inl, 'inline');
}

async function loadDay(){
  open = null;
  const date = index?.days?.[day];
  try { data = date ? await getJSON(`data/${date}.json`) : null; } catch { data = null; }
  render();
}

$('list').addEventListener('click', e => { const tr = e.target.closest('tr.m'); if (!tr) return; open = open === tr.dataset.id ? null : tr.dataset.id; render(); });
$('list').addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr.m')) { e.preventDefault(); e.target.click(); } });
['f-league', 'f-sort', 'f-over'].forEach(id => $(id).addEventListener('change', render));
document.querySelectorAll('.days button').forEach(b => b.addEventListener('click', () => {
  day = b.dataset.d; $('f-league').value = '';
  document.querySelectorAll('.days button').forEach(x => x.setAttribute('aria-pressed', x === b));
  loadDay();
}));
$('year').textContent = new Date().getFullYear();

(async () => {
  try { config = await getJSON('config.json'); } catch { config = {}; }
  if (config.notice) { $('notice').textContent = config.notice; $('notice').hidden = false; }
  setupAds();
  try { index = await getJSON('data/index.json'); } catch { index = null; }
  await loadDay();
  if (data?.demo) { $('notice').textContent = 'Datos de ejemplo: la página todavía no está conectada a la API.' + (config.notice ? ' ' + config.notice : ''); $('notice').hidden = false; }
})();
})();
