const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let Panel;
vm.runInNewContext(fs.readFileSync('custom_components/viewmarq/frontend/panel.js', 'utf8'), {
  HTMLElement: class {}, customElements: {get: () => false, define: (_, cls) => {Panel = cls;}},
  structuredClone, clearTimeout, setTimeout,
});
function editor() {
  const p = Object.create(Panel.prototype);
  Object.assign(p, {selected: {id: 'office', settings: {}, pages: []}, original: {pages: ['old']},
    draft: {pages: ['new']}, dirty: true, editSession: 1,
    shadowRoot: {querySelector: () => ({disabled: false})},
    values() {return structuredClone(this.draft);}, message(text) {this.notice = text;},
    queueSave() {this.queued = true;}});
  return p;
}
(async () => {
  const p = editor(); let finish;
  p.call = () => new Promise(resolve => {finish = resolve;});
  const saving = p.save();
  p.draft.pages = ['newer']; finish(); await saving;
  assert.equal(p.dirty, true); assert.equal(p.queued, true);
  assert.equal(JSON.stringify(p.original.pages), '["new"]');
  p.call = async () => {}; await p.save();
  assert.equal(p.dirty, false); assert.equal(p.notice, 'All changes saved');
  const bad = editor(); bad.call = async () => {throw Error('Fields overlap');};
  await bad.save(); assert.equal(bad.dirty, true); assert.match(bad.notice, /Not saved: Fields overlap/);
  assert.equal(JSON.stringify(bad.original.pages), '["old"]'); assert.equal(bad.queued, undefined);
  const switched = editor(); switched.call = () => new Promise(resolve => {finish = resolve;});
  const pending = switched.save(); switched.editSession++; finish(); await pending;
  assert.equal(JSON.stringify(switched.original.pages), '["old"]');
  console.log('Autosave: edits during saving, validation failures and stale editor responses passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
