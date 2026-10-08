const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const colors = {green:'#67ff72', amber:'#ffbb35', red:'#ff524c'};
class ViewMarqPanel extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:'open'}); this.page=0; this.dirty=false; }
  set hass(value) { this._hass=value; if (!this.started && this.isConnected) this.start(); }
  connectedCallback() { if(this._hass && !this.started) this.start(); }
  disconnectedCallback() { clearInterval(this.timer); clearTimeout(this.previewTimer); this.started=false; }
  async call(action, extra={}) { return this._hass.callWS({type:'viewmarq/panel',action,...extra}); }
  async start() { this.started=true; await this.load(); this.timer=setInterval(()=>this.refreshLive(),2000); }
  async load() {
    try {
      this.data=await this.call('read');
      this.selected=this.data.displays.find(x=>x.id===this.selected?.id)||this.data.displays[0];
      this.render(); if(this.selected) await this.preview();
    } catch(error) { this.shadowRoot.innerHTML=`<p>${esc(error.message||error)}</p>`; }
  }
  message(text) { const box=this.shadowRoot.querySelector('#notice'); if(box) box.textContent=text; }
  async refreshLive() {
    if(this.polling || document.hidden) return;
    this.polling=true;
    try {
      const data=await this.call('read'); const display=data.displays.find(x=>x.id===this.selected?.id);
      if(display) {
        this.preview(); this.live=display; this.draw('#live-sign',display.displayed_text,display.colors,display.geometry,display.alignment);
        this.shadowRoot.querySelector('#live-status').textContent=`${display.status} · ${Object.entries(display.sports).map(([k,v])=>`${k}: ${v}`).join(' · ')}`;
      }
    } catch(error) { this.message(error.message||String(error)); }
    finally { this.polling=false; }
  }
  options(values, selected) { return values.map(v=>{const a=typeof v==='string'?{value:v,label:v}:v;return `<option value="${esc(a.value)}" ${a.value===selected?'selected':''}>${esc(a.label)}</option>`;}).join(''); }
  select(name,label,values,value) { return `<label>${label}<select name="${name}">${this.options(values,value)}</select></label>`; }
  render() {
    const d=this.selected;
    if(!d) {this.shadowRoot.innerHTML='<p>No displays are loaded. <a href="/config/integrations/integration/viewmarq">Add a ViewMarq display</a>.</p>';return;}
    const s=d.settings; this.pageDraft=structuredClone(d.pages); this.editIndex=0; this.original=structuredClone({...s,pages:d.pages}); this.dirty=false; this.catalog=null;
    const states=Object.values(this._hass.states);
    this.teamMap=new Map([...this.data.favorites,...s.teams].map(t=>[`${t.league}:${t.id}`,t]));
    const sensorIds=new Set([...states.filter(x=>x.entity_id.startsWith('binary_sensor.')).map(x=>x.entity_id),...s.binary_sensors]);
    const sensorRows=[...sensorIds].map(id=>({id,name:this._hass.states[id]?.attributes.friendly_name||id})).sort((a,b)=>a.name.localeCompare(b.name));
    const fonts=[{value:'standard',label:'Standard — two-row friendly'},{value:'compact',label:'Compact'}];
    if(d.geometry.pixel_height>=14) fonts.push({value:'large',label:'Large'},{value:'tall',label:'Tall'});
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;background:var(--primary-background-color,#f5f7fa);color:var(--primary-text-color,#18252d);min-height:100dvh;overflow:visible;font:15px system-ui}
      *{box-sizing:border-box}[hidden]{display:none!important}header{padding:18px 24px;border-bottom:1px solid var(--divider-color,#ddd);display:flex;align-items:center;gap:14px;background:var(--card-background-color,white)}h1{font-size:23px;margin:0}header img{width:38px;height:38px;image-rendering:auto}header a{margin-left:auto}a{color:var(--primary-color,#007c91)}main{max-width:1200px;margin:auto;padding:24px}.row{display:flex;gap:16px;align-items:center;flex-wrap:wrap}.row>*{flex:1}.meta{color:var(--secondary-text-color,#637581);font-size:13px}.grid{display:grid;grid-template-columns:minmax(320px,1.2fr) minmax(280px,1fr);gap:22px;margin-top:20px}.card{background:var(--card-background-color,white);border:1px solid var(--divider-color,#dce3e7);border-radius:14px;padding:20px;margin-bottom:18px}h2{font-size:17px;margin:0 0 15px}label{display:block;margin:12px 0;font-weight:550}input,select,textarea,button{font:inherit}select,input[type=text],input[type=number],input[type=search],textarea{width:100%;display:block;margin-top:7px;border:1px solid var(--divider-color,#b6c5cf);border-radius:7px;padding:10px;color:inherit;background:var(--card-background-color,white)}textarea{resize:vertical;min-height:86px}button{cursor:pointer;border:1px solid var(--divider-color,#b6c5cf);border-radius:7px;padding:9px 14px;background:var(--card-background-color,white);color:inherit}button.primary{background:#087e8b;color:white;border-color:#087e8b}button:disabled{opacity:.5;cursor:default}.check{display:flex;align-items:center;gap:10px;font-weight:400;margin:8px 0}.check input{width:18px;height:18px;accent-color:#087e8b}.sensor-list{max-height:250px;overflow:auto;border-top:1px solid var(--divider-color,#ddd);margin-top:10px;padding-top:7px}.sensor-list small{display:block;font-weight:400;color:var(--secondary-text-color,#637581)}details summary{cursor:pointer;font-weight:600}.sign{background:#090d0a;border:9px solid #303635;border-radius:9px;box-shadow:0 5px 12px #0003;margin:14px 0;min-height:72px;display:flex;align-items:center}.sign svg{width:100%;display:block}.notice{min-height:24px;padding:8px 0;color:var(--primary-color,#007c91)}.toolbar{display:flex;gap:10px;align-items:center;margin-top:12px}.toolbar span{flex:1}.sticky{position:sticky;top:16px;align-self:start;max-height:calc(100dvh - 32px);overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin}.muted{font-size:13px;line-height:1.5;color:var(--secondary-text-color,#637581)}.page-item{display:flex;gap:6px;margin:8px 0;align-items:center}.page-item button:first-child{flex:1;text-align:left}.page-item.selected{outline:2px solid #087e8b;border-radius:7px}.field-card{border:1px solid var(--divider-color,#ddd);padding:12px;margin:12px 0;border-radius:8px}.small-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 12px}fieldset{border:0;padding:0;margin:0}#teams-list label{font-size:14px}@media(max-width:850px){.grid{grid-template-columns:1fr}.sticky{grid-row:1;top:8px;max-height:45dvh;z-index:2;background:var(--primary-background-color,#f5f7fa)}main{padding:14px}header{padding:14px}}
      </style><header><ha-menu-button></ha-menu-button><img src="/viewmarq-assets/icon.png" alt="ViewMarq"><h1>ViewMarq</h1><a href="/config/integrations/integration/viewmarq">Add / manage displays</a></header>
      <main><div class="row"><label>Display<select id="display">${this.data.displays.map(x=>`<option value="${esc(x.id)}" ${x.id===d.id?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label><div class="meta">${esc(d.model)} · ${d.geometry.pixel_width} × ${d.geometry.pixel_height} pixels<br>${esc(d.host)}</div></div>
      <div class="grid"><form id="editor"><section class="card"><h2>Pages</h2><p class="muted">Build this display's rotation. Each page has its own fields, layout, style and duration. Changes stay as a draft until you save.</p><label class="check"><input name="enabled" type="checkbox" ${s.enabled?'checked':''}>Display enabled</label><div class="row"><label>New page type<select id="new-page-type">${this.options(Object.entries(this.data.page_types).map(([value,label])=>({value,label})),'text')}</select></label><button type="button" id="add-page">Add page</button></div><div id="page-list"></div><div id="page-editor"></div></section>
      <section class="card"><h2>Door and sensor alerts</h2><p class="muted">Select sensors. Their names and meanings become the messages. Routine alerts use the bottom row; smoke, gas, CO, unsafe and wet alerts use the whole sign. Alerts clear automatically.</p><input id="sensor-search" type="search" aria-label="Find alert sensors" placeholder="Find a door or sensor"><div class="sensor-list">${sensorRows.map(x=>`<label class="check sensor-row" data-name="${esc(x.name.toLowerCase())}"><input type="checkbox" name="binary_sensor" value="${esc(x.id)}" ${s.binary_sensors.includes(x.id)?'checked':''}><span>${esc(x.name)}</span></label>`).join('')}</div><p class="muted"><a href="/config/integrations/integration/viewmarq#config_entry=${esc(d.id)}">Optional alert wording, priority and advanced rules</a></p></section>
      <section class="card"><h2>Live sports</h2><p class="muted">ESPN scores appear automatically during games. No game means no sports page.</p><div id="teams-list">${[...this.teamMap].map(([key,t])=>this.teamCheck(key,t,s.teams.some(x=>x.league===t.league&&x.id===t.id))).join('')}</div><details id="team-details"><summary>Add another team</summary><label>League<select id="league">${this.options(this.data.leagues,'NFL')}</select></label><button type="button" id="load-teams">Find teams</button><div id="team-picker-wrap" hidden><label>Search teams<input id="team-search" type="search" placeholder="Search any part of a name, e.g. Thunder"></label><p id="team-count" class="muted"></p><label>Team<select id="team-picker"></select></label></div><button type="button" id="add-team" hidden>Add team to display</button></details><label>Hide scores after minutes without an update<input name="sports_max_age" type="number" min="1" max="15" value="${s.sports_max_age}"></label></section>
      <section class="card"><h2>Display defaults</h2><div class="row">${this.select('font','Text size',fonts,s.font)}${this.select('alignment','Alignment',['left','center','right'],s.alignment)}</div><div class="row">${this.select('color','Normal color',['green','amber','red'],s.color)}${this.select('alert_color','Alert color',['red','amber','green'],s.alert_color)}</div>${this.select('sports_color','Sports color',['amber','green','red'],s.sports_color)}${this.select('sports_mode','During live games',[{value:'interleave',label:'Interleave with all pages'},{value:'only',label:'Show sports pages only'},{value:'hide_clock',label:'Hide clock pages'}],s.sports_mode)}<label>Seconds per page<input name="dwell" type="number" min="3" max="300" value="${s.dwell}"></label><details><summary>Motion options</summary>${this.select('scroll','Text motion',[{value:'static',label:'Stationary pages'},{value:'left',label:'Scroll left'}],s.scroll)}${this.select('speed','Scroll speed',['slow','medium','fast'],s.speed)}<p class="muted">Mixed normal/alert rows stay stationary. Large fonts on a two-row sign leave room for one line; routine alerts then join the page rotation.</p></details></section></form>
      <aside class="sticky"><section class="card"><h2>Layout preview</h2><label class="check"><input id="sample-preview" type="checkbox">Sample selected page (preview only)</label><div id="draft-sign" class="sign"></div><div class="toolbar"><button id="previous" aria-label="Previous preview page">←</button><span id="page-label"></span><button id="next" aria-label="Next preview page">→</button></div><p class="muted">Uses the sign's detected size and the same text wrapping and colors as the sender. Typeface is an approximation; this is not a camera view. Live sensor states are used.</p><div class="toolbar"><button class="primary" id="save">Save to display</button><button id="discard">Discard edits</button></div><p id="preview-note" class="muted"></p><div id="notice" class="notice" role="status">Settings changes do not restart Home Assistant.</div></section><section class="card"><h2>Last accepted by the real sign</h2><div id="live-sign" class="sign"></div><p id="live-status" class="muted">${esc(d.status)}</p><p class="muted">Updates automatically after the sign acknowledges a command. Physical appearance still needs a glance at the sign.</p></section></aside></div></main>`;
    this.shadowRoot.querySelector('ha-menu-button').hass=this._hass;
    this.shadowRoot.querySelector('#display').onchange=async event=>{if(this.dirty&&!confirm('Discard unsaved changes for this display?')){event.target.value=this.selected.id;return;}this.selected=this.data.displays.find(x=>x.id===event.target.value);this.page=0;this.render();await this.preview();};
    this.shadowRoot.querySelector('#editor').oninput=event=>{if(event.target.id==='sensor-search'){const q=event.target.value.toLowerCase();this.shadowRoot.querySelectorAll('.sensor-row').forEach(x=>x.hidden=!x.dataset.name.includes(q));return;}if(['league','team-picker','team-search','new-page-type'].includes(event.target.id)||event.target.closest('#page-editor'))return;this.dirty=true;this.message('Unsaved changes');clearTimeout(this.previewTimer);this.previewTimer=setTimeout(()=>this.preview(),250);};
    this.shadowRoot.querySelector('#editor').onsubmit=e=>e.preventDefault();
    this.shadowRoot.querySelector('#previous').onclick=()=>{this.page=Math.max(0,this.page-1);this.showPreview();};
    this.shadowRoot.querySelector('#next').onclick=()=>{this.page=Math.min((this.previews?.pages.length||1)-1,this.page+1);this.showPreview();};
    this.shadowRoot.querySelector('#sample-preview').onchange=()=>{this.page=0;this.preview();};
    this.shadowRoot.querySelector('#save').onclick=()=>this.save();
    this.shadowRoot.querySelector('#discard').onclick=()=>{this.render();this.preview();};
    this.shadowRoot.querySelector('#load-teams').onclick=()=>this.findTeams();
    this.shadowRoot.querySelector('#league').onchange=()=>this.findTeams();
    this.shadowRoot.querySelector('#team-search').oninput=()=>this.filterTeams();
    this.shadowRoot.querySelector('#team-details').ontoggle=event=>{if(event.target.open&&!this.catalog)this.findTeams();};
    this.shadowRoot.querySelector('#add-team').onclick=()=>this.addTeam();
    this.shadowRoot.querySelector('#add-page').onclick=()=>this.addPage();
    this.renderPages();
    this.draw('#live-sign',d.displayed_text,d.colors,d.geometry,d.alignment);
  }
  teamCheck(key,t,checked) {return `<label class="check"><input type="checkbox" name="team" value="${esc(key)}" ${checked?'checked':''}>${esc(t.name)} (${esc(t.league)})</label>`;}
  changed() {this.followSelection=true;this.dirty=true;this.message('Unsaved changes');clearTimeout(this.previewTimer);this.previewTimer=setTimeout(()=>this.preview(),250);}
  addPage() {
    const kind=this.shadowRoot.querySelector('#new-page-type').value;
    const page=structuredClone(this.selected.templates[kind]);page.id=this.newId();
    this.pageDraft.push(page);this.editIndex=this.pageDraft.length-1;this.renderPages();this.changed();
  }
  newId() {return `page-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,10)}`;}
  renderPages() {
    this.editIndex=Math.max(0,Math.min(this.editIndex,this.pageDraft.length-1));
    const root=this.shadowRoot;
    root.querySelector('#page-list').innerHTML=this.pageDraft.map((p,i)=>`<div class="page-item ${i===this.editIndex?'selected':''}"><button type="button" data-edit="${i}">${i+1}. ${esc(p.name)}${p.enabled?'':' (disabled)'}</button><button type="button" data-up="${i}" aria-label="Move ${esc(p.name)} up" ${i===0?'disabled':''}>↑</button><button type="button" data-down="${i}" aria-label="Move ${esc(p.name)} down" ${i===this.pageDraft.length-1?'disabled':''}>↓</button></div>`).join('')||'<p>No pages. Add one above. Automatic alerts still work.</p>';
    root.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>{this.editIndex=Number(b.dataset.edit);this.renderPages();const i=this.previews?.pages.findIndex(x=>x.page_id===this.pageDraft[this.editIndex].id);if(i>=0){this.page=i;this.showPreview();}if(this.shadowRoot.querySelector('#sample-preview').checked){this.page=0;this.preview();}});
    for(const action of ['up','down'])root.querySelectorAll(`[data-${action}]`).forEach(b=>b.onclick=()=>{const i=Number(b.dataset[action]),j=i+(action==='up'?-1:1);[this.pageDraft[i],this.pageDraft[j]]=[this.pageDraft[j],this.pageDraft[i]];this.editIndex=j;this.renderPages();this.changed();});
    const p=this.pageDraft[this.editIndex];const box=root.querySelector('#page-editor');
    if(!p){box.innerHTML='';return;}
    const states=Object.values(this._hass.states).sort((a,b)=>(a.attributes.friendly_name||a.entity_id).localeCompare(b.attributes.friendly_name||b.entity_id));
    const entities=domain=>[{value:'',label:'Choose an entity'},...states.filter(x=>!domain||x.entity_id.startsWith(domain+'.')).map(x=>({value:x.entity_id,label:`${x.attributes.friendly_name||x.entity_id} (${x.entity_id})`}))];
    const sel=(key,label,choices,value)=>`<label>${label}<select data-page="${key}">${this.options(choices,value??'')}</select></label>`;
    const input=(key,label,value,type='text')=>`<label>${label}<input data-page="${key}" type="${type}" value="${esc(value??'')}"></label>`;
    const inherit=values=>[{value:'',label:'Display default'},...values];
    const v=p.visibility||{mode:'always'};
    box.innerHTML=`<hr><h2>Edit page ${this.editIndex+1}</h2><label class="check"><input type="checkbox" data-page="enabled" ${p.enabled?'checked':''}>Page enabled</label>${input('name','Page name',p.name)}<p class="muted">${esc(this.data.page_types[p.type])}</p><div class="row"><button type="button" id="duplicate-page">Duplicate page</button><button type="button" id="delete-page">Delete page</button></div>
    ${['entity','media','custom'].includes(p.type)?sel('entity',p.type==='media'?'Media player (read only)':'Page entity',entities(p.type==='media'?'media_player':null),p.entity):''}
    ${p.type==='weather'||p.type==='custom'?sel('weather_entity','Weather source',entities('weather'),p.weather_entity):''}
    ${p.type==='media'?`<label class="check"><input type="checkbox" data-page="hide_idle" ${p.hide_idle!==false?'checked':''}>Hide when idle or off</label><label class="check"><input type="checkbox" data-page="hide_paused" ${p.hide_paused?'checked':''}>Hide when paused</label><p class="muted">Unavailable players are hidden. Missing metadata stays blank.</p>`:''}
    ${p.type==='sports'?`<label>Teams on this page<select id="page-teams" multiple size="4">${this.options(this.values().teams.map(t=>({value:`${t.league}:${t.id}`,label:`${t.name} (${t.league})`})))}</select></label><p class="muted">No selection means all saved teams. Hold Ctrl to select multiple teams. Fields not supplied by ESPN remain blank.</p>`:''}
    <details open><summary>Fields and layout</summary><p class="muted">Rows and columns start at 1. Width 0 fills the remaining row; height 0 fills the remaining screen. Long content continues on additional frames. Rows beyond the screen become another frame.</p><div id="fields"></div><button type="button" id="add-field">Add field</button></details>
    <details><summary>Page style and timing</summary><div class="small-grid">${sel('font','Font / size',inherit([{value:'standard',label:'Standard 5 × 8'},{value:'compact',label:'Compact 5 × 7'},...(this.selected.geometry.pixel_height>=14?[{value:'large',label:'Large 10 × 14'},{value:'tall',label:'Tall 10 × 16'}]:[])]),p.font)}${sel('color','Color',inherit(['green','amber','red']),p.color)}${input('dwell','Seconds (blank = default)',p.dwell,'number')}${sel('motion','Motion',inherit(['static','left']),p.motion)}${sel('speed','Scroll speed',inherit(['slow','medium','fast']),p.speed)}${sel('time_format','Clock format',['12-hour','24-hour'],p.time_format)}${sel('date_style','Date format',[{value:'weekday-year',label:'Thu 10/08/2026'},{value:'full-date',label:'Oct 08, 2026'},{value:'date-only',label:'10/08/2026'},{value:'iso-date',label:'2026-10-08'},{value:'weekday-date',label:'Thu 10/08'},{value:'time-only',label:'No date'}],p.date_style)}</div><p class="muted">Stationary layouts preserve the grid. Scrolling reads fields in row order on one line.</p></details>
    <details><summary>Visibility condition</summary>${sel('visibility.mode','Show page',[{value:'always',label:'Always (when content is available)'},{value:'live_games',label:'During selected teams’ live games'},{value:'no_live_games',label:'When there are no live games'},{value:'sensor_active',label:'When a binary sensor is active'},{value:'sensor_inactive',label:'When a binary sensor is inactive'},{value:'entity_state',label:'When entity state matches'}],v.mode)}${sel('visibility.entity','Condition entity',entities(),v.entity)}${input('visibility.value','Matching raw state',v.value)}</details>`;
    box.querySelectorAll('[data-page]').forEach(el=>{el.oninput=()=>{const key=el.dataset.page;let value=el.type==='checkbox'?el.checked:el.value;if(['font','color','motion','speed'].includes(key))value=value||null;if(key==='dwell')value=value===''?null:Number(value);if(key.startsWith('visibility.')){p.visibility={...p.visibility,[key.split('.')[1]]:value};}else p[key]=value;this.changed();};el.onchange=()=>{el.oninput();if(['name','enabled'].includes(el.dataset.page))this.renderPages();};});
    if(p.type==='sports'){const picker=box.querySelector('#page-teams');[...picker.options].forEach(o=>o.selected=p.teams.includes(o.value));picker.onchange=()=>{p.teams=[...picker.selectedOptions].map(o=>o.value);this.changed();};}
    box.querySelector('#duplicate-page').onclick=()=>{const copy=structuredClone(p);copy.id=this.newId();copy.name=(copy.name+' copy').slice(0,100);this.pageDraft.splice(this.editIndex+1,0,copy);this.editIndex++;this.renderPages();this.changed();};
    box.querySelector('#delete-page').onclick=()=>{this.pageDraft.splice(this.editIndex,1);this.renderPages();this.changed();};
    box.querySelector('#add-field').onclick=()=>{const row=p.fields.reduce((n,f)=>Math.max(n,f.row+(f.height||1)),0);p.fields.push({source:'text',text:'Your text',row,column:0,width:0,height:1,align:'center'});this.renderFields();this.changed();};
    this.renderFields();
  }
  renderFields() {
    const p=this.pageDraft[this.editIndex], box=this.shadowRoot.querySelector('#fields');
    box.innerHTML=p.fields.map((f,i)=>`<div class="field-card"><label>Field ${i+1}<select data-field="${i}" data-key="source">${this.options(Object.entries(this.data.fields).map(([value,label])=>({value,label})),f.source)}</select></label>${f.source==='text'?`<label>Text<textarea data-field="${i}" data-key="text">${esc(f.text)}</textarea></label>`:''}<label>Prefix / label<input type="text" data-field="${i}" data-key="label" value="${esc(f.label)}" placeholder="Optional, e.g. Yards:"></label>${f.source.startsWith('entity_')||f.source.startsWith('media_')?`<label>Override entity (optional)<input type="text" list="entity-ids" data-field="${i}" data-key="entity" value="${esc(f.entity)}"></label>`:''}${f.source==='entity_attribute'?`<label>Attribute name<input type="text" data-field="${i}" data-key="attribute" value="${esc(f.attribute)}"></label>`:''}<details><summary>Position and alignment</summary><div class="small-grid">${['row','column','width','height'].map(k=>`<label>${{row:'Row',column:'Column',width:'Width (0 = auto)',height:'Height (0 = auto)'}[k]}<input type="number" min="${['row','column'].includes(k)?1:0}" data-field="${i}" data-key="${k}" value="${(f[k]??0)+(['row','column'].includes(k)?1:0)}"></label>`).join('')}<label>Alignment<select data-field="${i}" data-key="align">${this.options([{value:'',label:'Display default'},'left','center','right'],f.align||'')}</select></label></div></details><button type="button" data-remove-field="${i}">Remove field ${i+1}</button></div>`).join('')+`<datalist id="entity-ids">${Object.values(this._hass.states).map(s=>`<option value="${esc(s.entity_id)}">${esc(s.attributes.friendly_name)}</option>`).join('')}</datalist>`;
    box.querySelectorAll('[data-field]').forEach(el=>{el.oninput=()=>{const key=el.dataset.key;let value=el.value;if(['row','column','width','height'].includes(key))value=Number(value)-(['row','column'].includes(key)?1:0);if(key==='align')value=value||null;p.fields[Number(el.dataset.field)][key]=value;this.changed();};el.onchange=()=>{el.oninput();if(el.dataset.key==='source')this.renderFields();};});
    box.querySelectorAll('[data-remove-field]').forEach(b=>b.onclick=()=>{p.fields.splice(Number(b.dataset.removeField),1);this.renderFields();this.changed();});
  }
  values() {
    const form=this.shadowRoot.querySelector('#editor'); const result={};
    for(const name of ['enabled']) result[name]=form.elements[name].checked;
    for(const name of ['font','alignment','color','alert_color','sports_color','sports_mode','scroll','speed']) result[name]=form.elements[name].value;
    for(const name of ['dwell','sports_max_age']) result[name]=Number(form.elements[name].value);
    result.pages=structuredClone(this.pageDraft);
    result.binary_sensors=[...form.querySelectorAll('[name=binary_sensor]:checked')].map(x=>x.value);
    result.teams=[...form.querySelectorAll('[name=team]:checked')].map(x=>this.teamMap.get(x.value));
    return result;
  }
  async preview() {
    const seq=this.previewSeq=(this.previewSeq||0)+1;
    try { const result=await this.call('preview',{entry_id:this.selected.id,settings:this.values(),...(this.shadowRoot.querySelector('#sample-preview').checked?{sample_page:this.pageDraft[this.editIndex]?.id}: {})});if(seq!==this.previewSeq)return;this.previews=result;if(this.followSelection){const found=result.pages.findIndex(x=>x.page_id===this.pageDraft[this.editIndex]?.id);if(found>=0)this.page=found;this.followSelection=false;}this.page=Math.min(this.page,Math.max(0,result.pages.length-1));this.showPreview(); }
    catch(error) {this.message(error.message||String(error));}
  }
  showPreview() {
    const p=this.previews?.pages[this.page]||{text:' ',color:this.values().color,kind:'Blank'};
    this.draw('#draft-sign',p.text,p.color,p.geometry||this.previews?.geometry||this.selected.geometry,p.alignment||'left');
    const selectedPage=this.pageDraft[this.editIndex];this.shadowRoot.querySelector('#preview-note').textContent=selectedPage&&!this.previews?.pages.some(x=>x.page_id===selectedPage.id)?`No active content for ${selectedPage.name}. Sample preview can show its layout; it never sends sample data to the sign.`:'';
    this.shadowRoot.querySelector('#page-label').textContent=`${this.page+1} / ${Math.max(1,this.previews?.pages.length||0)} · ${p.kind}`;
    this.shadowRoot.querySelector('#previous').disabled=this.page===0;
    this.shadowRoot.querySelector('#next').disabled=this.page>=(this.previews?.pages.length||1)-1;
  }
  draw(target,text,color,g,alignment) {
    const lines=(text||' ').split('\n'); const first=Math.max(0,Math.floor((g.rows-lines.length)/2));
    const svg=lines.map((line,i)=>{const width=line.length*g.cell_width;const spare=Math.max(0,g.pixel_width-width);const x=alignment==='left'?0:alignment==='right'?spare:Math.floor(spare/2);const y=(first+i)*g.cell_height+g.cell_height*.83;return `<text x="${x}" y="${y}" xml:space="preserve" font-family="monospace" font-size="${g.cell_height*.9}" ${width?`textLength="${width}" lengthAdjust="spacingAndGlyphs"`:''} fill="${colors[Array.isArray(color)?color[i]:color]||colors.green}">${esc(line)}</text>`;}).join('');
    this.shadowRoot.querySelector(target).innerHTML=`<svg viewBox="0 0 ${g.pixel_width} ${g.pixel_height}" role="img" aria-label="${esc(text)}"><defs><pattern id="dots" width="1" height="1" patternUnits="userSpaceOnUse"><circle cx=".5" cy=".5" r=".18" fill="#193120"/></pattern></defs><rect width="100%" height="100%" fill="url(#dots)"/>${svg}</svg>`;
  }
  async save() {
    const button=this.shadowRoot.querySelector('#save');button.disabled=true;
    try {const current=this.values();const settings=Object.fromEntries(Object.entries(current).filter(([k,v])=>JSON.stringify(v)!==JSON.stringify(this.original[k])));await this.call('save',{entry_id:this.selected.id,settings});this.original=structuredClone(current);this.selected.settings={...this.selected.settings,...current};this.selected.pages=structuredClone(current.pages);this.dirty=false;this.message('Saved. The display is applying your settings.');}
    catch(error) {this.message(error.message||String(error));}finally{button.disabled=false;}
  }
  async findTeams() {
    const button=this.shadowRoot.querySelector('#load-teams');button.disabled=true;
    const league=this.shadowRoot.querySelector('#league').value;
    const request=this.catalogRequest=(this.catalogRequest||0)+1;
    this.catalog=null; this.catalogLeague=league;
    this.shadowRoot.querySelector('#team-picker-wrap').hidden=true;
    this.shadowRoot.querySelector('#add-team').hidden=true;
    this.message(`Loading ${league} teams…`);
    try {
      const catalog=await this.call('teams',{league});
      if(request!==this.catalogRequest)return;
      this.catalog=catalog;this.shadowRoot.querySelector('#team-search').value='';
      this.shadowRoot.querySelector('#team-picker-wrap').hidden=false;
      this.shadowRoot.querySelector('#add-team').hidden=false;
      this.filterTeams();this.message(`${league}: ${catalog.length} teams loaded. Search by name.`);
    } catch(error){if(request===this.catalogRequest)this.message(error.message||String(error));}
    finally{if(request===this.catalogRequest)button.disabled=false;}
  }
  filterTeams() {
    const query=this.shadowRoot.querySelector('#team-search').value.trim().toLowerCase();
    const matches=(this.catalog||[]).filter(t=>t.label.toLowerCase().includes(query));
    this.shadowRoot.querySelector('#team-picker').innerHTML=this.options(matches,'');
    this.shadowRoot.querySelector('#team-count').textContent=`${this.catalogLeague}: ${matches.length} of ${this.catalog?.length||0} teams`;
    this.shadowRoot.querySelector('#add-team').disabled=!matches.length;
  }
  async addTeam() {
    if(this.catalogLeague!==this.shadowRoot.querySelector('#league').value)return;
    const id=this.shadowRoot.querySelector('#team-picker').value;
    const found=this.catalog?.find(x=>x.value===id);if(!found)return;
    const entryId=this.selected.id;
    const team={id,league:this.catalogLeague,name:found.label};
    const key=`${team.league}:${team.id}`;
    const button=this.shadowRoot.querySelector('#add-team');button.disabled=true;
    try {
      const latest=await this.call('read');
      const display=latest.displays.find(x=>x.id===entryId);
      if(!display)throw new Error('Display is reloading. Try again in a moment.');
      const teams=new Map(display.settings.teams.map(t=>[`${t.league}:${t.id}`,t]));
      teams.set(key,team);const savedTeams=[...teams.values()];
      await this.call('save',{entry_id:entryId,settings:{teams:savedTeams}});
      if(this.selected.id!==entryId)return;
      if(!this.teamMap.has(key)){
        this.teamMap.set(key,team);
        this.shadowRoot.querySelector('#teams-list').insertAdjacentHTML('beforeend',this.teamCheck(key,team,true));
      } else [...this.shadowRoot.querySelectorAll('[name=team]')].find(x=>x.value===key).checked=true;
      this.original.teams=structuredClone(savedTeams);this.selected.settings.teams=structuredClone(savedTeams);
      this.dirty=Object.entries(this.values()).some(([k,v])=>JSON.stringify(v)!==JSON.stringify(this.original[k]));
      this.message(`${team.name} added and saved to ${this.selected.name}.${this.dirty?' Other edits remain unsaved.':''}`);
      this.preview();
    } catch(error){this.message(error.message||String(error));}
    finally{button.disabled=false;}
  }

}
if(!customElements.get('viewmarq-panel')) customElements.define('viewmarq-panel',ViewMarqPanel);
