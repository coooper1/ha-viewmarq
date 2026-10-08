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
        this.preview(); this.live=display; this.draw('#live-sign',display.displayed_text,display.colors,display.geometry,display.settings.alignment);
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
    const s=d.settings; this.original=structuredClone(s); this.dirty=false; this.catalog=null;
    const states=Object.values(this._hass.states);
    this.teamMap=new Map([...this.data.favorites,...s.teams].map(t=>[`${t.league}:${t.id}`,t]));
    const sensorIds=new Set([...states.filter(x=>x.entity_id.startsWith('binary_sensor.')).map(x=>x.entity_id),...s.binary_sensors]);
    const sensorRows=[...sensorIds].map(id=>({id,name:this._hass.states[id]?.attributes.friendly_name||id})).sort((a,b)=>a.name.localeCompare(b.name));
    const fonts=[{value:'standard',label:'Standard — two-row friendly'},{value:'compact',label:'Compact'}];
    if(d.geometry.pixel_height>=14) fonts.push({value:'large',label:'Large'},{value:'tall',label:'Tall'});
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;background:var(--primary-background-color,#f5f7fa);color:var(--primary-text-color,#18252d);height:100%;overflow:auto;font:15px system-ui}
      *{box-sizing:border-box}[hidden]{display:none!important}header{padding:18px 24px;border-bottom:1px solid var(--divider-color,#ddd);display:flex;align-items:center;gap:14px;background:var(--card-background-color,white)}h1{font-size:23px;margin:0}header img{width:38px;height:38px;image-rendering:auto}header a{margin-left:auto}a{color:var(--primary-color,#007c91)}main{max-width:1200px;margin:auto;padding:24px}.row{display:flex;gap:16px;align-items:center;flex-wrap:wrap}.row>*{flex:1}.meta{color:var(--secondary-text-color,#637581);font-size:13px}.grid{display:grid;grid-template-columns:minmax(320px,1.2fr) minmax(280px,1fr);gap:22px;margin-top:20px}.card{background:var(--card-background-color,white);border:1px solid var(--divider-color,#dce3e7);border-radius:14px;padding:20px;margin-bottom:18px}h2{font-size:17px;margin:0 0 15px}label{display:block;margin:12px 0;font-weight:550}input,select,textarea,button{font:inherit}select,input[type=text],input[type=number],input[type=search],textarea{width:100%;display:block;margin-top:7px;border:1px solid var(--divider-color,#b6c5cf);border-radius:7px;padding:10px;color:inherit;background:var(--card-background-color,white)}textarea{resize:vertical;min-height:86px}button{cursor:pointer;border:1px solid var(--divider-color,#b6c5cf);border-radius:7px;padding:9px 14px;background:var(--card-background-color,white);color:inherit}button.primary{background:#087e8b;color:white;border-color:#087e8b}button:disabled{opacity:.5;cursor:default}.check{display:flex;align-items:center;gap:10px;font-weight:400;margin:8px 0}.check input{width:18px;height:18px;accent-color:#087e8b}.sensor-list{max-height:250px;overflow:auto;border-top:1px solid var(--divider-color,#ddd);margin-top:10px;padding-top:7px}.sensor-list small{display:block;font-weight:400;color:var(--secondary-text-color,#637581)}details summary{cursor:pointer;font-weight:600}.sign{background:#090d0a;border:9px solid #303635;border-radius:9px;box-shadow:0 5px 12px #0003;margin:14px 0;min-height:72px;display:flex;align-items:center}.sign svg{width:100%;display:block}.notice{min-height:24px;padding:8px 0;color:var(--primary-color,#007c91)}.toolbar{display:flex;gap:10px;align-items:center;margin-top:12px}.toolbar span{flex:1}.sticky{position:sticky;top:16px;align-self:start}.muted{font-size:13px;line-height:1.5;color:var(--secondary-text-color,#637581)}fieldset{border:0;padding:0;margin:0}#teams-list label{font-size:14px}@media(max-width:850px){.grid{grid-template-columns:1fr}.sticky{position:static;grid-row:1}main{padding:14px}header{padding:14px}}
      </style><header><ha-menu-button></ha-menu-button><img src="/viewmarq-assets/icon.png" alt="ViewMarq"><h1>ViewMarq</h1><a href="/config/integrations/integration/viewmarq">Add / manage displays</a></header>
      <main><div class="row"><label>Display<select id="display">${this.data.displays.map(x=>`<option value="${esc(x.id)}" ${x.id===d.id?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label><div class="meta">${esc(d.model)} · ${d.geometry.pixel_width} × ${d.geometry.pixel_height} pixels<br>${esc(d.host)}</div></div>
      <div class="grid"><form id="editor"><section class="card"><h2>What to show</h2><label class="check"><input name="enabled" type="checkbox" ${s.enabled?'checked':''}>Display enabled</label><label>Quick message<input name="quick_message" type="text" maxlength="190" value="${esc(s.quick_message)}" placeholder="Type something for this sign"></label><label>More messages<textarea name="messages">${esc(s.messages)}</textarea></label><p class="muted">One message per line. Long messages become additional pages.</p><label class="check"><input name="show_clock" type="checkbox" ${s.show_clock?'checked':''}>Show clock and date</label><div class="row">${this.select('time_format','Clock',[{value:'12-hour',label:'12-hour (AM/PM)'},{value:'24-hour',label:'24-hour'}],s.time_format)}${this.select('date_style','Date',[{value:'weekday-year',label:'Thu 10/08/2026'},{value:'full-date',label:'Oct 08, 2026'},{value:'date-only',label:'10/08/2026'},{value:'iso-date',label:'2026-10-08'},{value:'weekday-date',label:'Thu 10/08'},{value:'time-only',label:'Time only'}],s.date_style)}</div>${this.select('weather_entity','Weather',[{value:'',label:'No weather'},...states.filter(x=>x.entity_id.startsWith('weather.')).map(x=>({value:x.entity_id,label:x.attributes.friendly_name||x.entity_id}))],s.weather_entity)}</section>
      <section class="card"><h2>Door and sensor alerts</h2><p class="muted">Select sensors. Their names and meanings become the messages. Routine alerts use the bottom row; smoke, gas, CO, unsafe and wet alerts use the whole sign. Alerts clear automatically.</p><input id="sensor-search" type="search" aria-label="Find alert sensors" placeholder="Find a door or sensor"><div class="sensor-list">${sensorRows.map(x=>`<label class="check sensor-row" data-name="${esc(x.name.toLowerCase())}"><input type="checkbox" name="binary_sensor" value="${esc(x.id)}" ${s.binary_sensors.includes(x.id)?'checked':''}><span>${esc(x.name)}</span></label>`).join('')}</div><p class="muted"><a href="/config/integrations/integration/viewmarq#config_entry=${esc(d.id)}">Optional alert wording, priority and advanced rules</a></p></section>
      <section class="card"><h2>Live sports</h2><p class="muted">ESPN scores appear automatically during games. No game means no sports page.</p><div id="teams-list">${[...this.teamMap].map(([key,t])=>this.teamCheck(key,t,s.teams.some(x=>x.league===t.league&&x.id===t.id))).join('')}</div><details id="team-details"><summary>Add another team</summary><label>League<select id="league">${this.options(this.data.leagues,'NFL')}</select></label><button type="button" id="load-teams">Find teams</button><div id="team-picker-wrap" hidden><label>Search teams<input id="team-search" type="search" placeholder="Search any part of a name, e.g. Thunder"></label><p id="team-count" class="muted"></p><label>Team<select id="team-picker"></select></label></div><button type="button" id="add-team" hidden>Add team to display</button></details><label>Hide scores after minutes without an update<input name="sports_max_age" type="number" min="1" max="15" value="${s.sports_max_age}"></label></section>
      <section class="card"><h2>Appearance</h2><div class="row">${this.select('font','Text size',fonts,s.font)}${this.select('alignment','Alignment',['left','center','right'],s.alignment)}</div><div class="row">${this.select('color','Normal color',['green','amber','red'],s.color)}${this.select('alert_color','Alert color',['red','amber','green'],s.alert_color)}</div>${this.select('sports_color','Sports color',['amber','green','red'],s.sports_color)}<label>Seconds per page<input name="dwell" type="number" min="3" max="300" value="${s.dwell}"></label><details><summary>Motion options</summary>${this.select('scroll','Text motion',[{value:'static',label:'Stationary pages'},{value:'left',label:'Scroll left'}],s.scroll)}${this.select('speed','Scroll speed',['slow','medium','fast'],s.speed)}<p class="muted">Mixed normal/alert rows stay stationary. Large fonts on a two-row sign leave room for one line; routine alerts then join the page rotation.</p></details></section></form>
      <aside class="sticky"><section class="card"><h2>Layout preview</h2><div id="draft-sign" class="sign"></div><div class="toolbar"><button id="previous" aria-label="Previous preview page">←</button><span id="page-label"></span><button id="next" aria-label="Next preview page">→</button></div><p class="muted">Uses the sign's detected size and the same text wrapping and colors as the sender. Typeface is an approximation; this is not a camera view. Live sensor states are used.</p><div class="toolbar"><button class="primary" id="save">Save to display</button><button id="discard">Discard edits</button></div><div id="notice" class="notice" role="status">Settings changes do not restart Home Assistant.</div></section><section class="card"><h2>Last accepted by the real sign</h2><div id="live-sign" class="sign"></div><p id="live-status" class="muted">${esc(d.status)}</p><p class="muted">Updates automatically after the sign acknowledges a command. Physical appearance still needs a glance at the sign.</p></section></aside></div></main>`;
    this.shadowRoot.querySelector('ha-menu-button').hass=this._hass;
    this.shadowRoot.querySelector('#display').onchange=async event=>{if(this.dirty&&!confirm('Discard unsaved changes for this display?')){event.target.value=this.selected.id;return;}this.selected=this.data.displays.find(x=>x.id===event.target.value);this.page=0;this.render();await this.preview();};
    this.shadowRoot.querySelector('#editor').oninput=event=>{if(event.target.id==='sensor-search'){const q=event.target.value.toLowerCase();this.shadowRoot.querySelectorAll('.sensor-row').forEach(x=>x.hidden=!x.dataset.name.includes(q));return;}if(['league','team-picker','team-search'].includes(event.target.id))return;this.dirty=true;this.message('Unsaved changes');clearTimeout(this.previewTimer);this.previewTimer=setTimeout(()=>this.preview(),250);};
    this.shadowRoot.querySelector('#editor').onsubmit=e=>e.preventDefault();
    this.shadowRoot.querySelector('#previous').onclick=()=>{this.page=Math.max(0,this.page-1);this.showPreview();};
    this.shadowRoot.querySelector('#next').onclick=()=>{this.page=Math.min((this.previews?.pages.length||1)-1,this.page+1);this.showPreview();};
    this.shadowRoot.querySelector('#save').onclick=()=>this.save();
    this.shadowRoot.querySelector('#discard').onclick=()=>{this.render();this.preview();};
    this.shadowRoot.querySelector('#load-teams').onclick=()=>this.findTeams();
    this.shadowRoot.querySelector('#league').onchange=()=>this.findTeams();
    this.shadowRoot.querySelector('#team-search').oninput=()=>this.filterTeams();
    this.shadowRoot.querySelector('#team-details').ontoggle=event=>{if(event.target.open&&!this.catalog)this.findTeams();};
    this.shadowRoot.querySelector('#add-team').onclick=()=>this.addTeam();
    this.draw('#live-sign',d.displayed_text,d.colors,d.geometry,s.alignment);
  }
  teamCheck(key,t,checked) {return `<label class="check"><input type="checkbox" name="team" value="${esc(key)}" ${checked?'checked':''}>${esc(t.name)} (${esc(t.league)})</label>`;}
  values() {
    const form=this.shadowRoot.querySelector('#editor'); const result={};
    for(const name of ['enabled','show_clock']) result[name]=form.elements[name].checked;
    for(const name of ['quick_message','messages','time_format','date_style','weather_entity','font','alignment','color','alert_color','sports_color','scroll','speed']) result[name]=form.elements[name].value;
    for(const name of ['dwell','sports_max_age']) result[name]=Number(form.elements[name].value);
    result.binary_sensors=[...form.querySelectorAll('[name=binary_sensor]:checked')].map(x=>x.value);
    result.teams=[...form.querySelectorAll('[name=team]:checked')].map(x=>this.teamMap.get(x.value));
    return result;
  }
  async preview() {
    const seq=this.previewSeq=(this.previewSeq||0)+1;
    try { const result=await this.call('preview',{entry_id:this.selected.id,settings:this.values()});if(seq!==this.previewSeq)return;this.previews=result;this.page=Math.min(this.page,Math.max(0,result.pages.length-1));this.showPreview(); }
    catch(error) {this.message(error.message||String(error));}
  }
  showPreview() {
    const p=this.previews?.pages[this.page]||{text:' ',color:this.values().color,kind:'Blank'};
    this.draw('#draft-sign',p.text,p.color,this.previews?.geometry||this.selected.geometry,this.values().alignment);
    this.shadowRoot.querySelector('#page-label').textContent=`${this.page+1} / ${Math.max(1,this.previews?.pages.length||0)} · ${p.kind}`;
    this.shadowRoot.querySelector('#previous').disabled=this.page===0;
    this.shadowRoot.querySelector('#next').disabled=this.page>=(this.previews?.pages.length||1)-1;
  }
  draw(target,text,color,g,alignment) {
    const lines=(text||' ').split('\n'); const first=Math.max(0,Math.floor((g.rows-lines.length)/2));
    const svg=lines.map((line,i)=>{const width=line.length*g.cell_width;const spare=Math.max(0,g.pixel_width-width);const x=alignment==='left'?0:alignment==='right'?spare:Math.floor(spare/2);const y=(first+i)*g.cell_height+g.cell_height*.83;return `<text x="${x}" y="${y}" font-family="monospace" font-size="${g.cell_height*.9}" ${width?`textLength="${width}" lengthAdjust="spacingAndGlyphs"`:''} fill="${colors[Array.isArray(color)?color[i]:color]||colors.green}">${esc(line)}</text>`;}).join('');
    this.shadowRoot.querySelector(target).innerHTML=`<svg viewBox="0 0 ${g.pixel_width} ${g.pixel_height}" role="img" aria-label="${esc(text)}"><defs><pattern id="dots" width="1" height="1" patternUnits="userSpaceOnUse"><circle cx=".5" cy=".5" r=".18" fill="#193120"/></pattern></defs><rect width="100%" height="100%" fill="url(#dots)"/>${svg}</svg>`;
  }
  async save() {
    const button=this.shadowRoot.querySelector('#save');button.disabled=true;
    try {const current=this.values();const settings=Object.fromEntries(Object.entries(current).filter(([k,v])=>JSON.stringify(v)!==JSON.stringify(this.original[k])));await this.call('save',{entry_id:this.selected.id,settings});this.original=structuredClone(current);this.selected.settings={...this.selected.settings,...current};this.dirty=false;this.message('Saved. The display is applying your settings.');}
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
