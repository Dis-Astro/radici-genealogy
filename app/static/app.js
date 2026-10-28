/* Radici 0.1 · GPL-2.0-or-later. No third party requests or browser data storage. */
'use strict';
const $ = id => document.getElementById(id);
const escapeXML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
let state, csrf, selected = null, step = 1, busy = false, activeFamily = null;
let view = {x:40,y:40,scale:0.7}, drag = null, toastTimer;
let visual=null, viewMode="family", presentationDirection="vertical", viewSerial=0;
let portableAccess=false,desktopAccess=false;
function showAccess(message=''){
  $('application').hidden=true;$('login').hidden=portableAccess;$('portable-access').hidden=!portableAccess;
  if(desktopAccess&&window.chrome?.webview){$('portable-error').textContent='Ricollegamento all’archivio sul PC…';window.chrome.webview.postMessage('reconnect');}
  else if(portableAccess){$('portable-error').textContent=message;$('portable-retry').focus();}
  else{$('login-error').textContent=message;$('password').focus();}
}
function currentView(){return visual||state;}
const editButton=document.createElement('button');editButton.id='edit-person';editButton.className='quiet';editButton.textContent='Modifica nome';$('more-person').before(editButton);
const deleteButton=document.createElement('button');deleteButton.id='delete-person';deleteButton.className='danger-quiet';deleteButton.textContent='Elimina persona';$('more-person').after(deleteButton);
const treeChooser=document.createElement('div');treeChooser.className='tree-chooser';treeChooser.innerHTML='<label for="tree-picker">Albero aperto</label><select id="tree-picker" aria-label="Albero aperto"></select><button id="new-tree-open" class="secondary">+ Nuovo albero</button>';document.querySelector('.workspace-head').before(treeChooser);
const roleLabel=document.createElement('label');roleLabel.id='role-label';roleLabel.innerHTML='<span id="role-description"></span><select id="parent-slot"><option value="father">Padre / primo genitore</option><option value="mother">Madre / secondo genitore</option></select><small>Scelta esplicita per conservare il ruolo nel registro, anche per genitori dello stesso sesso.</small>';$('child-type-label').after(roleLabel);
const layoutControls=document.createElement('div');layoutControls.className='layout-controls';layoutControls.innerHTML='<span class="layout-caption">Sviluppo dell’albero</span><div class="direction-switch" role="group" aria-label="Direzione dell’albero"><button id="direction-vertical" aria-pressed="true">↓ Verticale</button><button id="direction-horizontal" aria-pressed="false">→ Orizzontale</button></div><button id="layout-open" class="quiet">Composizione…</button>';document.querySelector('.canvas-toolbar').after(layoutControls);
document.querySelector('.canvas-footer').innerHTML='<div id="family-legend" aria-label="Evidenzia una famiglia"></div>';
const optimizePaper=document.createElement('button');optimizePaper.id='optimize-paper';optimizePaper.type='button';optimizePaper.className='secondary';optimizePaper.textContent='Ricomponi per questo foglio';$('preview-button').after(optimizePaper);
const readingControls=document.createElement('div');readingControls.className='reading-controls';readingControls.innerHTML='<div class="reading-switch" role="group" aria-label="Come guardare l’albero"><button id="view-family" aria-pressed="true">La famiglia</button><button id="view-overview" aria-pressed="false">Tutto l’albero</button><button id="view-manual" aria-pressed="false">Sposta le schede</button></div><span id="view-caption" aria-live="polite"></span>';
const readingUndo=document.createElement('button');readingUndo.id='reading-undo';readingUndo.className='quiet';readingUndo.textContent='↶ Annulla';readingUndo.onclick=()=>$('undo').click();readingControls.append(readingUndo);
readingControls.insertBefore(document.querySelector('.direction-switch'),$('view-caption'));
treeChooser.insertBefore($('print-open'),$('new-tree-open'));
document.querySelector('.sidebar-note').replaceChildren($('add-independent'));
document.querySelector('.canvas-toolbar').after(readingControls);
const readingLegend=document.createElement('p');readingLegend.className='reading-legend';readingLegend.textContent='Ponte corto: coppia · Pallino: diramazione · Archetto: incrocio senza legame · Puntini: da confermare · Trattini: adottiva';document.querySelector('.canvas-footer').after(readingLegend);
async function refreshView(frame=true){
  if(!state)return;
  if(!state.people.some(p=>p.id===selected))selected=state.people[0]?.id||null;
  const serial=++viewSerial,tree=state.tree_id;
  if(viewMode==='manual'){visual=null;render();if(frame)initialFrame();return;}
  try{
    const viewport=$('canvas').getBoundingClientRect();
    const result=await api('/api/view',{mode:viewMode,id:selected,direction:presentationDirection,siblings:innerWidth<=720?2:viewMode==='family'?4:3,font_size:22,viewport_width:Math.max(100,viewport.width),viewport_height:Math.max(100,viewport.height)});
    if(serial!==viewSerial||tree!==state.tree_id)return;
    visual=result;render();if(frame)initialFrame();
  }catch(e){if(serial!==viewSerial)return;toast(e.message);}
}
async function selectPerson(id,fromList=false){
  selected=id;activeFamily=null;
  if(viewMode==='family')await refreshView();
  else{render();if(fromList)focusPerson(id,true);}
}
for(const mode of ['family','overview','manual'])$('view-'+mode).onclick=async()=>{viewMode=mode;activeFamily=null;await refreshView();};


function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 6000);
}
async function api(path, data, blob = false) {
  const response = await fetch(path, data === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json', 'X-CSRF-Token':csrf || ''}, body:JSON.stringify({tree_id:state?.tree_id,...data})
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({error:'Il servizio non risponde.'}));
    if (response.status === 401 && path !== '/api/login') showAccess();
    throw new Error(err.error || 'Operazione non riuscita.');
  }
  return blob ? response.blob() : response.json();
}
async function act(action, data = {}) {
  if (busy) return;
  busy = true; $('save-status').textContent = 'Salvataggio…';
  try {
    const existing = new Set(state.people.map(p=>p.id));
    state = await api('/api/command',{...data,action,revision:state.revision});
    if(action==='add') selected=data.existing_id || state.people.find(p=>!existing.has(p.id))?.id || selected;
    await refreshView(false); $('save-status').textContent = 'Tutto salvato';
    return true;
  } catch (e) { toast(e.message); $('save-status').textContent = 'Azione non salvata'; return false; }
  finally { busy = false; }
}
function person() { return state.people.find(p => p.id === selected); }
function fullName(p) { return [p.first,p.surname].filter(Boolean).join(' '); }
function transform() { $('world').setAttribute('transform',`translate(${view.x} ${view.y}) scale(${view.scale})`); $('zoom-label').textContent = Math.round(view.scale*100)+'%'; }
function fit() {
  const pos = Object.values(currentView().positions); if (!pos.length) return;
  const left = Math.min(...pos.map(p=>p.x)), top = Math.min(...pos.map(p=>p.y));
  const width = Math.max(...pos.map(p=>p.x+(p.w||224)))-left+64, height = Math.max(...pos.map(p=>p.y+(p.h||96)))-top+64;
  const box = $('canvas').getBoundingClientRect();
  view.scale = Math.min(1.15,(box.width-24)/width,(box.height-52)/height);
  view.scale = Math.max(.06,view.scale);
  view.x = (box.width-width*view.scale)/2-(left-32)*view.scale;
  view.y = (box.height-46-height*view.scale)/2-(top-32)*view.scale;
  transform();
}
function zoom(factor) {
  const box = $('canvas').getBoundingClientRect(), x = box.width/2, y = box.height/2;
  const next = Math.max(.06,Math.min(3,view.scale*factor));
  view.x = x-(x-view.x)*next/view.scale; view.y = y-(y-view.y)*next/view.scale; view.scale = next; transform();
}
function renderList() {
  const query = $('search').value.trim().toLocaleLowerCase('it');
  const people = state.people.filter(p=>fullName(p).toLocaleLowerCase('it').includes(query));
  $('people-list').replaceChildren();
  for (const p of people) {
    const button = document.createElement('button'); button.className = 'person-row'+(p.id===selected?' selected':'');
    const avatar = document.createElement('span'); avatar.className = 'avatar'; avatar.textContent = (p.first[0]||'?')+(p.surname[0]||'');
    const text = document.createElement('span'), name = document.createElement('strong'), year = document.createElement('small');
    name.textContent = fullName(p); year.textContent = p.years; text.append(name,year); button.append(avatar,text);
    button.onclick = () => selectPerson(p.id,true); $('people-list').append(button);
  }
  if (!people.length) { const p = document.createElement('p'); p.textContent = 'Nessuna persona trovata.'; $('people-list').append(p); }
}
function focusPerson(id,readable=false) {
  const p = currentView().positions[id];if(!p)return;if(readable)view.scale=Math.max(.8,view.scale);const box = $('canvas').getBoundingClientRect();
  view.x = box.width/2-(p.x+(p.w||224)/2)*view.scale; view.y = (box.height-40)/2-(p.y+(p.h||96)/2)*view.scale; transform();
}
function render() {
  if (!state.people.some(p=>p.id===selected)) selected = state.people[0]?.id || null;
  const graph=currentView();
  $('count').textContent=state.people.length;$('tree-count').textContent=graph.people.length===state.people.length?state.people.length+' persone':graph.people.length+' di '+state.people.length+' persone';
  for(const mode of ['family','overview','manual'])$('view-'+mode).setAttribute('aria-pressed',String(mode===viewMode));
  document.body.dataset.treeView=viewMode;
  document.querySelector('.workspace-head h1').textContent=state.trees?.find(t=>t.id===state.tree_id)?.name||'La storia della tua famiglia';
  $('view-caption').textContent=viewMode==='family'?(selected?'La famiglia di '+fullName(person())+' · '+graph.people.length+' di '+state.people.length:'La prima persona della tua storia'):viewMode==='overview'?'Tutte le '+state.people.length+' persone':'Le tue posizioni salvate · trascina dalla maniglia';
  document.querySelector('.canvas-hint').textContent=viewMode==='manual'?'Trascina la maniglia per spostare una scheda · Maiusc per non agganciare':'Tocca una persona per seguirne la famiglia · trascina lo sfondo per muoverti';
  $('empty').hidden = state.people.length > 0;
  $('demo-banner').hidden = !state.demo&&!state.portable;
  if(state.portable){$('demo-banner').textContent=state.desktop?'RADICI SUL PC · Le modifiche si salvano qui. Usa «Chiudi e salva» per uscire.':'RADICI PORTATILE · Archivio, stampe e backup sulla chiavetta. Prima di estrarla usa «Chiudi e salva» nel pannello Radici.';$('logout').hidden=true;}
  $('undo').disabled = !state.undo; $('redo').disabled = !state.redo;
  $('reading-undo').disabled=!state.undo;
  $('import-button').disabled = state.people.length > 0 || state.demo;
  $('export-gramps').disabled = state.demo; $('backup').disabled = state.demo;
  for (const id of ['add-parent','add-partner','add-child','more-person','edit-person','delete-person']) $(id).disabled = !selected;
  $('tree-picker').replaceChildren();
  for(const t of state.trees || []){const option=document.createElement('option');option.value=t.id;option.textContent=t.name;$('tree-picker').append(option);}
  if(state.tree_id)$('tree-picker').value=state.tree_id;
  const p = person();
  $('selected-name').textContent = p ? fullName(p) : 'Scegli una persona nell’albero';
  $('selected-years').textContent = p ? p.years : 'Poi aggiungi qualcuno della sua famiglia.';
  $('selected-avatar').textContent = p ? (p.first[0]||'?')+(p.surname[0]||'') : '♧';
  renderList();
  const out = [graph.connections_svg || ''];
  for (const p of graph.people) {
    const pos = graph.positions[p.id]; if (!pos) continue;
    out.push(`<g class="node ${p.id===selected?'selected':''}" data-person="${escapeXML(p.id)}" transform="translate(${pos.x} ${pos.y})" tabindex="0" role="button" aria-label="${escapeXML(fullName(p))}, ${escapeXML(p.years)}${pos.locked?', posizione bloccata':''}"><title>${escapeXML(fullName(p))} · ${escapeXML(p.years)}</title><rect class="card" width="${pos.w}" height="${pos.h}" rx="12"/>${graph.card_text[p.id]}<g class="drag-handle" data-drag="${escapeXML(p.id)}" ${viewMode!=='manual'?'visibility="hidden"':''}><rect x="${pos.w-32}" y="${pos.h-33}" width="30" height="30" fill="transparent"/><text x="${pos.w-16}" y="${pos.h-9}" font-size="22" text-anchor="middle">⠿</text></g>${viewMode==='manual'&&pos.locked?`<circle cx="${pos.w-12}" cy="12" r="4" fill="#ab8451"/>`:''}</g>`);
  }
  $('world').innerHTML = out.join(''); transform();
  renderFamilies();
  for(const direction of ['vertical','horizontal'])$('direction-'+direction).setAttribute('aria-pressed',String(graph.layout.direction===direction));
  if (state.backup_error) toast(state.backup_error);
  if (viewMode==='manual'&&state.layout_warning) toast(state.layout_warning);
}
function openDialog(id) { $(id).showModal(); }
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
$('search').oninput = renderList;
$('fit').onclick=async()=>{if(viewMode==='family'){viewMode='overview';await refreshView();}else fit();}; $('zoom-in').onclick = ()=>zoom(1.2); $('zoom-out').onclick = ()=>zoom(1/1.2);
$('undo').onclick = async()=>{if(await act('undo')) toast('Ultima azione annullata.');};
$('redo').onclick = ()=>act('redo');
$('auto-layout').onclick = async()=>{if(viewMode!=='manual'){await refreshView();toast('Vista riordinata. Le tue posizioni salvate restano conservate.');return;}if(state.locked_count){$('layout-open').click();$('layout-release').checked=true;return;}if(await act('layout')){fit();toast('Coppie e rami ricomposti. Puoi annullare.');}};
for(const direction of ['vertical','horizontal'])$('direction-'+direction).onclick=async()=>{if(viewMode!=='manual'){presentationDirection=direction;await refreshView();}else if(await act('layout',{layout:{direction}})){fit();toast('Direzione aggiornata. Puoi annullare.');}};
$('layout-open').onclick=()=>{$('layout-direction').value=state.layout.direction;$('layout-siblings').value=state.layout.siblings;$('layout-stagger').checked=state.layout.stagger;$('layout-font').value=state.layout.font_size||22;$('layout-release').checked=false;openDialog('layout-dialog');};
$('layout-form').onsubmit=async event=>{event.preventDefault();viewMode='manual';visual=null;if(await act('layout',{layout:{direction:$('layout-direction').value,siblings:Number($('layout-siblings').value),stagger:$('layout-stagger').checked,font_size:Number($('layout-font').value)},release_locked:$('layout-release').checked})){$('layout-dialog').close();fit();toast('Composizione aggiornata: puoi annullare per tornare alla precedente.');}};
function renderFamilies(){
  if(!state.families.some(f=>f.id===activeFamily))activeFamily=null;
  const legend=$('family-legend');legend.replaceChildren();
  const all=document.createElement('button');all.textContent='Tutti i rami';all.setAttribute('aria-pressed',String(!activeFamily));all.onclick=()=>{activeFamily=null;render();};legend.append(all);
  for(const f of currentView().families.filter(f=>f.parents.length>1||f.children.length)){
    const b=document.createElement('button');const parents=f.parents.map(id=>state.people.find(p=>p.id===id)).filter(Boolean);const count=f.partial?f.total_children:f.children.length;b.textContent=(parents.map(p=>p.first).join(' e ')||'Famiglia')+' · '+(f.partial?f.visible_children+' di '+f.total_children:f.children.length)+(count===1?' figlio':' figli')+(f.partial?' visibili':'');b.style.setProperty('--family-color',state.family_colors[f.id]);b.className='family-key';b.setAttribute('aria-pressed',String(activeFamily===f.id));b.title=f.parents.map(id=>state.people.find(p=>p.id===id)).filter(Boolean).map(fullName).join(' e ');b.onclick=()=>{activeFamily=activeFamily===f.id?null:f.id;render();};legend.append(b);
  }
  const focus=state.families.find(f=>f.id===activeFamily);
  document.querySelector('.family-details')?.remove();
  if(focus){
    const details=document.createElement('div');details.className='family-details';
    const heading=document.createElement('strong');heading.textContent=focus.parents.map(id=>state.people.find(p=>p.id===id)).filter(Boolean).map(fullName).join(' e ');details.append(heading);
    const types={0:'nessuna',1:'biologica',2:'adottiva',3:'figliastro/a',4:'sponsorizzata',5:'affidamento',6:'da confermare'};
    details.append(document.createTextNode(focus.children.map(id=>{const p=state.people.find(p=>p.id===id),r=focus.relations?.[id]||[6,6];return (p?fullName(p):id)+' (primo genitore: '+(types[r[0]]||'tipo Gramps '+r[0])+', secondo: '+(types[r[1]]||'tipo Gramps '+r[1])+')';}).join(' · ')||'Nessun figlio registrato.'));
    legend.after(details);
  }
  const visible=new Set(focus?[...focus.parents,...focus.children]:[]);
  $('world').querySelectorAll('[data-family]').forEach(g=>{g.classList.toggle('family-muted',!!focus&&g.dataset.family!==activeFamily);g.classList.toggle('family-active',g.dataset.family===activeFamily);});
  $('world').querySelectorAll('[data-person]').forEach(g=>g.classList.toggle('person-muted',!!focus&&!visible.has(g.dataset.person)));
}
$('tree-tab').onclick = ()=>{fit();$('canvas').scrollIntoView({block:'center',behavior:'smooth'});};
$('help-open').onclick = ()=>openDialog('help-dialog'); $('archive-open').onclick = ()=>openDialog('archive-dialog');
$('tree').addEventListener('click',event=>{
  const family=event.target.closest('[data-family]');
  if(family){activeFamily=activeFamily===family.dataset.family?null:family.dataset.family;render();return;}
  const node = event.target.closest('[data-person]');
  if(node&&!drag)selectPerson(node.dataset.person);
});
$('tree').addEventListener('keydown',event=>{
  const node = event.target.closest('[data-person]');
  if (node && (event.key==='Enter'||event.key===' ')) {event.preventDefault();selectPerson(node.dataset.person);$('add-child').focus();}
});
$('tree').addEventListener('pointerdown',event=>{
  if(event.button!==0) return;
  const handle=event.target.closest('[data-drag]'), node=event.target.closest('[data-person]');
  if((node&&!handle)||event.target.closest('[data-family]'))return;
  if(handle&&viewMode!=='manual')return;
  event.preventDefault(); $('tree').setPointerCapture(event.pointerId);
  const id=handle?.dataset.drag;
  drag={id,startX:event.clientX,startY:event.clientY,x:id?state.positions[id].x:view.x,y:id?state.positions[id].y:view.y,moved:false,pointer:event.pointerId};
});
function snapped(id,x,y,free=false){
  const p=state.positions[id];if(free)return {x,y};
  const result={x,y};
  for(const [axis,dim] of [['x','w'],['y','h']]){
    const targets=Object.entries(state.positions).filter(([i])=>i!==id).flatMap(([,q])=>[q[axis],q[axis]+(q[dim]-p[dim])/2]);
    const priority=[];
    if((state.layout.direction==='horizontal'?'y':'x')===axis){
      for(const f of state.families.filter(f=>f.children.includes(id))){
        const parents=f.parents.map(i=>state.positions[i]).filter(Boolean);
        if(parents.length)priority.push(parents.reduce((sum,q)=>sum+q[axis]+q[dim]/2,0)/parents.length-p[dim]/2);
      }
    }
    targets.sort((a,b)=>Math.abs(a-result[axis])-Math.abs(b-result[axis]));
    priority.sort((a,b)=>Math.abs(a-result[axis])-Math.abs(b-result[axis]));
    if(priority.length&&Math.abs(priority[0]-result[axis])<=18)targets.unshift(priority[0]);
    if(targets.length&&Math.abs(targets[0]-result[axis])<=18)result[axis]=targets[0];
  }
  return result;
}
$('tree').addEventListener('pointermove',event=>{
  if(!drag || drag.pointer!==event.pointerId) return;
  const dx=event.clientX-drag.startX,dy=event.clientY-drag.startY;
  if(Math.abs(dx)+Math.abs(dy)>5) drag.moved=true;
  if(drag.id){
    const node=Array.from($('world').querySelectorAll('[data-person]')).find(n=>n.dataset.person===drag.id);
    const target=snapped(drag.id,drag.x+dx/view.scale,drag.y+dy/view.scale,event.shiftKey);
    node?.setAttribute('transform',`translate(${target.x} ${target.y})`);node?.classList.add('dragging');
  }else{view.x=drag.x+dx;view.y=drag.y+dy;transform();}
});
async function endDrag(event) {
  if(!drag || drag.pointer!==event.pointerId) return;
  const d=drag; drag=null;
  if(d.id&&d.moved){selected=d.id;const saved=await act('move',{id:d.id,...snapped(d.id,d.x+(event.clientX-d.startX)/view.scale,d.y+(event.clientY-d.startY)/view.scale,event.shiftKey),snap:!event.shiftKey});render();if(saved)toast('Posizione salvata. Allineamento automatico attivo; puoi annullare.');}
}
$('tree').addEventListener('pointerup',endDrag);
$('tree').addEventListener('pointercancel',()=>{drag=null;render();});
$('tree').addEventListener('wheel',event=>{event.preventDefault();zoom(event.deltaY<0?1.08:1/1.08);},{passive:false});
document.addEventListener('keydown',event=>{
  if(event.ctrlKey&&event.key.toLowerCase()==='z'&&!['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName)&&!document.querySelector('dialog[open]')) {event.preventDefault();act(event.shiftKey?'redo':'undo');}
});
function initialFrame(){fit();}
new ResizeObserver(()=>{if(state&&!drag)initialFrame();}).observe($('canvas'));

function updateFamilies() {
  const rel=$('relation').value;
  const families=state.families.filter(f=>rel==='parent'?f.children.includes(selected)&&f.parents.length<2:f.parents.includes(selected)&&(rel!=='partner'||f.parents.length<2));
  $('family').replaceChildren();
  if(families.length>1&&rel!=='partner') {const choose=document.createElement('option');choose.value='__choose';choose.textContent='Scegli la famiglia…';$('family').append(choose);}
  const fresh=document.createElement('option');fresh.value='';fresh.textContent=rel==='partner'?'Crea una nuova unione':'Crea una nuova famiglia';$('family').append(fresh);
  for(const f of families){const option=document.createElement('option');option.value=f.id;option.textContent=(f.parents.map(id=>state.people.find(p=>p.id===id)).filter(Boolean).map(fullName).join(' e ')||'Genitori da aggiungere')+' · '+f.children.length+' figli';$('family').append(option);}
  if(families.length===1&&rel!=='partner')$('family').value=families[0].id;
  $('family-label').hidden=rel==='independent';
  $('child-type-label').hidden=!['parent','child'].includes(rel);
  $('relation-context').textContent=selected?'Persona di riferimento: '+fullName(person()):'La prima persona del tuo albero.';
  $('relation').querySelectorAll('option').forEach(o=>o.disabled=!selected&&o.value!=='independent');
  const existingOption=$('person-source').querySelector('option[value=existing]');existingOption.disabled=rel==='independent';
  if(rel==='independent')$('person-source').value='new';
  updateSource();updateRole();
}
function updateSource(){
  const existing=$('person-source').value==='existing';
  $('new-person-fields').hidden=existing;$('existing-person-label').hidden=!existing;
  $('first').required=step===2&&!existing;
  $('person-save').textContent=existing?'Collega questa persona':'Aggiungi all’albero';
}
$('person-source').onchange=updateSource;
function updateRole(){
  const rel=$('relation').value,f=state.families.find(f=>f.id===$('family').value);
  $('role-label').hidden=rel==='independent'||(rel==='child'&&!!f);
  $('role-description').textContent=rel==='parent'?'La nuova persona sarà:':'Ruolo di '+(person()?fullName(person()):'chi è già nell’albero')+':';
  const options=$('parent-slot').options;
  if(rel==='partner'&&f){$('parent-slot').value=(f.parent_roles?.[selected]??f.parents.indexOf(selected))===1?'mother':'father';}
  for(const option of options){const slot=option.value==='father'?0:1;option.disabled=rel==='parent'&&!!f&&f.parents.some((id,index)=>(f.parent_roles?.[id]??index)===slot);}
  if(options[$('parent-slot').selectedIndex].disabled)$('parent-slot').value=Array.from(options).find(o=>!o.disabled)?.value||'father';
}
$('family').onchange=updateRole;
function wizard(value) {
  step=value;$('wizard-one').hidden=step!==1;$('wizard-two').hidden=step!==2;
  $('wizard-next').hidden=step!==1;$('wizard-back').hidden=step!==2;$('person-save').hidden=step!==2;$('save-another-child').hidden=step!==2||$('relation').value!=='child';
  $('wizard-progress').textContent=`PASSO ${step} DI 2`;
  $('first').required=step===2&&$('person-source').value!=='existing';
  if(step===2){
    const labels={parent:'Genitore',child:'Figlio/a',partner:'Compagno/a',independent:'Persona senza legami'};
    $('person-summary').textContent=labels[$('relation').value]+(selected&&$('relation').value!=='independent'?' di '+fullName(person()):'')+'. Potrai annullare dopo il salvataggio.';
    updateSource();setTimeout(()=>($('person-source').value==='existing'?$('existing-person'):$('first')).focus(),0);
  }
}
function addPerson(relation) {$('person-form').reset();$('existing-person').replaceChildren();const choose=document.createElement('option');choose.value='';choose.textContent='Scegli la persona…';choose.disabled=true;choose.selected=true;$('existing-person').append(choose);for(const p of state.people.filter(p=>p.id!==selected)){const o=document.createElement('option');o.value=p.id;o.textContent=fullName(p)+(p.years?' · '+p.years:'');$('existing-person').append(o);}$('person-error').textContent='';$('relation').value=relation;$('parent-slot').value=person()?.gender===0?'mother':'father';if(relation==='child'&&person())$('surname').value=person().primary_surname??person().surname;updateFamilies();wizard(1);openDialog('person-dialog');}
$('add-parent').onclick=()=>addPerson('parent');$('add-partner').onclick=()=>addPerson('partner');$('add-child').onclick=()=>addPerson('child');
$('add-independent').onclick=$('empty-add').onclick=()=>addPerson('independent');
$('relation').onchange=updateFamilies;$('wizard-next').onclick=()=>{if($('family').value==='__choose'){$('person-error').textContent='Scegli la coppia o la famiglia a cui appartiene il legame.';return;}$('person-error').textContent='';wizard(2);};$('wizard-back').onclick=()=>wizard(1);
$('person-form').onsubmit=async event=>{
  event.preventDefault();if(step===1){wizard(2);return;}
  const data={first:$('first').value.trim(),surname:$('surname').value.trim(),birth:$('birth').value,gender:Number($('gender').value),relation:$('relation').value,target:selected,family:$('family').value||null,child_type:$('child-type').value,slot:$('parent-slot').value};
  if($('person-source').value==='existing'){data.existing_id=$('existing-person').value;if(!data.existing_id){$('person-error').textContent='Scegli la persona già presente da collegare.';return;}}
  if(data.family==='__choose'){$('person-error').textContent='Scegli prima una famiglia.';return;}
  if(!data.family&&data.relation!=='independent')data.new_family=true;
  if(!data.first&&!data.existing_id){$('person-error').textContent='Come si chiama questa persona? Inserisci almeno il nome.';return;}
  $('person-save').disabled=$('save-another-child').disabled=true;
  const repeat=event.submitter?.id==='save-another-child';
  if(await act('add',data)){
    if(repeat){
      const added=selected;selected=data.target;render();
      const family=state.families.find(f=>f.parents.includes(data.target)&&f.children.includes(added));
      updateFamilies();if(family)$('family').value=family.id;
      $('first').value='';$('birth').value='';$('gender').value='2';$('person-source').value='new';updateSource();
      wizard(2);toast('Salvato. Ora scrivi il nome del prossimo figlio: la famiglia resta la stessa.');
    }else{$('person-dialog').close();initialFrame();toast(data.existing_id?'Legame salvato. La persona già presente è stata conservata.':'Una nuova persona nella tua storia.');}
  }
  $('person-save').disabled=$('save-another-child').disabled=false;
};
$('more-person').onclick=()=>{const p=state.positions[selected];$('pos-x').value=p.x;$('pos-y').value=p.y;$('locked').checked=p.locked;$('move-branch').checked=false;openDialog('position-dialog');};
$('position-save').onclick=async()=>{
  const p=state.positions[selected],x=Number($('pos-x').value),y=Number($('pos-y').value);
  if($('move-branch').checked){if(await act('branch',{id:selected,dx:x-p.x,dy:y-p.y})){$('position-dialog').close();fit();}}
  else{
    if(x!==p.x||y!==p.y){if(!await act('move',{id:selected,x,y}))return;}
    if(state.positions[selected].locked!==$('locked').checked){if(!await act('lock',{id:selected,locked:$('locked').checked}))return;}
    $('position-dialog').close();fit();
  }
};
$('edit-person').onclick=()=>{const p=person();$('edit-first').value=p.first;$('edit-surname').value=p.primary_surname??p.surname;$('edit-gender').value=p.gender;openDialog('edit-dialog');};
$('edit-form').onsubmit=async event=>{event.preventDefault();if(await act('edit',{id:selected,first:$('edit-first').value,surname:$('edit-surname').value,gender:Number($('edit-gender').value)})){$('edit-dialog').close();toast('Nome aggiornato. Puoi annullare la modifica.');}};
$('delete-person').onclick=()=>{
  $('delete-person-name').textContent=fullName(person());
  const count=state.families.filter(f=>f.parents.includes(selected)||f.children.includes(selected)).length;
  $('delete-impact').textContent='Questa persona è collegata a '+count+(count===1?' famiglia.':' famiglie.');
  $('delete-backup-note').textContent=state.demo?'Nella demo puoi recuperarla con Annulla. Non vengono creati backup reali.':'Prima viene creato un backup completo. Se il backup fallisce, la persona rimane. Puoi recuperarla con Annulla fino al riavvio del servizio.';
  openDialog('delete-dialog');
};
$('delete-form').onsubmit=async event=>{event.preventDefault();$('delete-confirm').disabled=true;if(await act('delete',{id:selected,confirm:true})){$('delete-dialog').close();initialFrame();toast('Persona eliminata. Premi Annulla se vuoi recuperarla.');}$('delete-confirm').disabled=false;};
$('new-tree-open').onclick=()=>{$('new-tree-form').reset();$('new-tree-error').textContent='';openDialog('new-tree-dialog');$('new-tree-name').focus();};
async function openTree(id){
  try{state=await api('/api/trees/open',{id});selected=null;activeFamily=null;visual=null;await refreshView();toast('Albero aperto. Gli altri alberi sono conservati.');}catch(e){toast(e.message);render();}
}
$('tree-picker').onchange=()=>openTree($('tree-picker').value);
$('new-tree-form').onsubmit=async event=>{
  event.preventDefault();$('new-tree-confirm').disabled=true;$('new-tree-error').textContent='';
  try{state=await api('/api/trees/new',{name:$('new-tree-name').value});selected=null;activeFamily=null;visual=null;await refreshView();$('new-tree-dialog').close();toast('Nuovo albero creato. Aggiungi la prima persona o importa un archivio Gramps.');}
  catch(e){$('new-tree-error').textContent=e.message;}
  finally{$('new-tree-confirm').disabled=false;}
};

const singlePrintControls=document.createElement('div');singlePrintControls.id='single-print-controls';
while($('print-form').firstChild)singlePrintControls.append($('print-form').firstChild);
$('print-form').append(singlePrintControls);
const documentChoice=document.createElement('label');documentChoice.innerHTML='Tipo di stampa<select name="document" id="print-document"><option value="album" selected>Album 15 × 10 cm · schede di famiglia</option><option value="single">Albero su un solo foglio</option></select>';$('print-form').prepend(documentChoice);
const albumOptions=document.createElement('div');albumOptions.id='album-options';albumOptions.innerHTML='<p class="info-box">Ogni pagina misura 150 × 100 mm orizzontali. Mappa iniziale, indice e schede con rimandi. Le famiglie numerose continuano su più pagine.</p><label>Titolo dell’album<input name="album_title" id="album-title" maxlength="120" placeholder="La storia della nostra famiglia"></label><label>Grandezza dei nomi nelle schede (punti)<input name="album_text_pt" type="number" min="12" max="72" step="1" value="12"><small>Almeno 12 punti reali. I nomi completi vanno a capo; il programma aggiunge pagine invece di rimpicciolirli.</small></label><button type="submit" class="secondary">Aggiorna l’album</button><p class="layout-note">Stampa il PDF a Dimensioni effettive / 100%, una pagina per ogni spazio dell’album.</p>';documentChoice.after(albumOptions);
const albumNavigation=document.createElement('div');albumNavigation.id='album-navigation';albumNavigation.innerHTML='<button type="button" class="secondary" id="album-previous" aria-label="Pagina precedente">←</button><label>Pagina dell’album<select id="album-page" aria-label="Pagina dell’album"><option value="1">1 · Mappa d’insieme</option></select></label><button type="button" class="secondary" id="album-next" aria-label="Pagina successiva">→</button>';$('paper-preview').before(albumNavigation);
function documentMode(){const album=$('print-document').value==='album';singlePrintControls.hidden=album;albumOptions.hidden=!album;albumNavigation.hidden=!album;$('suitable-paper').disabled=album;$('download-svg').textContent=album?'Scarica tutte le pagine SVG':'Scarica SVG';$('download-pdf').textContent=album?'Crea PDF dell’album':'Scarica PDF per stampare';document.querySelector('#print-dialog h2').textContent=album?'Il tuo album 15 × 10 cm':'Il tuo albero, su carta.';document.querySelector('.preview-legend').textContent=album?'Il PDF contiene tutte le pagine. Le schede mantengono la grandezza dei nomi indicata.':'Le guide di margine e sicurezza compaiono solo nell’anteprima.';}
function printConfig(){const config={...Object.fromEntries(new FormData($('print-form'))),root_id:$('print-scope').value==='branch'?selected:null};if(config.document==='album'){config.album_page=Number($('album-page').value||1);config.root_id=null;}return config;}
let previewSerial=0, lastSheet=null, previewDelay;
async function preview(){
  clearTimeout(previewDelay);
  const serial=++previewSerial;lastSheet=null;$('print-error').textContent='';
  try{const data=await api('/api/print',{...printConfig(),output:'preview'});if(serial!==previewSerial)return;
    $('paper-preview').innerHTML=data.svg;
    const s=data.sheet;lastSheet=s;
    if(s.album){$('album-page').replaceChildren(...data.pages.map(p=>{const option=document.createElement('option');option.value=p.number;option.textContent=p.number+' · '+p.title;return option;}));$('album-page').value=s.page;$('album-previous').disabled=s.page<=1;$('album-next').disabled=s.page>=s.total_pages;}
    $('print-info').textContent=s.album?`150 × 100 mm · Pagina ${s.page} di ${s.total_pages} · `+(s.overview?'Mappa di orientamento: i nomi leggibili sono nelle schede successive':s.page_kind==='index'?'Indice delle famiglie':`Nomi ${s.font_pt.toFixed(0)} punti reali · ${s.page_people} persone`):`${Number(s.width.toFixed(1))} × ${Number(s.height.toFixed(1))} mm · Nomi ${s.font_pt.toFixed(1)} punti su carta · ${s.people} persone · ${s.direction==='vertical'?'↓ Verticale':'→ Orizzontale'}`;
    if(s.overflow)$('print-error').textContent='Il foglio è troppo piccolo per mantenere questi caratteri. Scegli un solo ramo oppure usa «Scegli un foglio che mantenga i caratteri».';
    else if(!s.album&&s.font_pt<Math.max(10,Number(printConfig().text_pt)||0))$('print-error').textContent='L’albero è adattato al foglio. I nomi risultano più piccoli della dimensione consigliata: puoi esportare oppure scegliere un solo ramo o un foglio più grande.';
    if(s.routing_warning)$('print-error').textContent+=' Alcuni collegamenti richiedono una ricomposizione: scegli «Ricomponi famiglie e coppie» oppure un solo ramo.';
    $('download-pdf').disabled=$('download-svg').disabled=s.overflow;
  }catch(e){if(serial!==previewSerial)return;$('print-error').textContent=e.message;$('download-pdf').disabled=$('download-svg').disabled=true;}
}
$('print-open').onclick=()=>{$('print-scope').querySelector('option[value=branch]').disabled=!selected;if(!selected)$('print-scope').value='all';if(!$('album-title').value)$('album-title').value=state.trees?.find(t=>t.id===state.tree_id)?.name||'';documentMode();openDialog('print-dialog');preview();};
$('album-page').onchange=()=>preview();
for(const [button,delta] of [['album-previous',-1],['album-next',1]])$(button).onclick=()=>{const next=Number($('album-page').value)+delta;if(next>=1&&next<=$('album-page').options.length){$('album-page').value=next;preview();}};
$('suitable-paper').onclick=()=>{
  if(!lastSheet)return;
  const f=$('print-form').elements,ratio=f.unit.value==='cm'?.1:1;
  if(lastSheet.recommended_width>5000||lastSheet.recommended_height>5000){$('print-error').textContent='Il foglio necessario supera 5 metri. Scegli un ramo o caratteri più piccoli.';return;}
  const standard=[['A4','portrait',210,297],['A4','landscape',297,210],['A3','portrait',297,420],['A3','landscape',420,297]].find(([, ,w,h])=>w>=lastSheet.recommended_width&&h>=lastSheet.recommended_height);
  if(standard){f.format.value=standard[0];f.orientation.value=standard[1];}
  else{f.format.value='custom';f.orientation.value='portrait';
    f.width.value=Math.max(25,lastSheet.recommended_width)*ratio;
    f.height.value=Math.max(25,lastSheet.recommended_height)*ratio;}
  $('print-form').querySelector('.custom-size').hidden=f.format.value!=='custom';preview();
};
$('print-form').onsubmit=e=>{e.preventDefault();preview();};
$('optimize-paper').onclick=async()=>{$('print-form').elements.composition.value='compact';await preview();toast('Famiglie ricomposte solo per la stampa. Le posizioni nell’albero sono conservate.');};
let previousUnit='mm';
$('print-form').addEventListener('change',event=>{
  if(event.target.id==='print-document'||event.target.name?.startsWith('album_')){$('album-page').innerHTML='<option value="1">1 · Mappa d’insieme</option>';documentMode();preview();return;}
  $('print-form').querySelector('.custom-size').hidden=$('paper-format').value!=='custom';
  $('scale-label').hidden=$('print-form').elements.mode.value!=='scale';
  $('print-form').elements.direction.disabled=$('print-form').elements.composition.value==='as_seen';
  if(event.target.name==='unit'){
    const current=event.target.value, ratio=current===previousUnit?1:current==='cm'?.1:10;
    for(const name of ['width','height','margin','safety']){$('print-form').elements[name].value=Number((Number($('print-form').elements[name].value)*ratio).toFixed(3));}
    previousUnit=current;
  }
  if(event.target.name==='text_pt')$('print-form').elements.mode.value='readable';
  clearTimeout(previewDelay);previewDelay=setTimeout(preview,180);
});
function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
async function exportPrint(output){const config=printConfig(),album=config.document==='album';if(album&&output==='svg')output='svgzip';$('download-pdf').disabled=$('download-svg').disabled=true;try{if(state.portable){const result=await api('/api/print',{...config,output,save_local:true});toast('Salvato nella cartella Stampe '+(state.desktop?'del PC: ':'della chiavetta: ')+result.saved);}else download(await api('/api/print',{...config,output},true),(album?'album':'albero')+'.'+(output==='svgzip'?'zip':output));}catch(e){$('print-error').textContent=e.message;}finally{$('download-pdf').disabled=$('download-svg').disabled=false;}}
$('download-svg').onclick=()=>exportPrint('svg');$('download-pdf').onclick=()=>exportPrint('pdf');
$('export-gramps').onclick=async()=>{try{if(state.portable){const result=await api('/api/export');$('archive-message').textContent='Archivio salvato nella cartella Stampe '+(state.desktop?'del PC: ':'della chiavetta: ')+result.saved;}else download(await api('/api/export',undefined,true),'albero.gramps');}catch(e){toast(e.message);}};
$('backup').onclick=async()=>{const b=$('backup');b.disabled=true;try{const result=await api('/api/backup',{});$('archive-message').textContent='Copia di sicurezza creata: '+result.name;}catch(e){$('archive-message').textContent=e.message;}finally{b.disabled=false;}};
$('import-button').onclick=async()=>{
  const file=$('import-file').files[0];if(!file){$('archive-message').textContent='Scegli prima un file .gramps o .xml.';return;}
  if(file.size>8*1024*1024){$('archive-message').textContent='Il file supera 8 MB.';return;}
  $('import-button').disabled=true;
  try{const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));state=await api('/api/import',{file:btoa(binary),revision:state.revision});visual=null;await refreshView();$('archive-message').textContent='Albero importato. Tutti gli oggetti originali sono conservati.';}catch(e){$('archive-message').textContent=e.message;}finally{$('import-button').disabled=state.people.length>0;}
};
$('login-form').onsubmit=async event=>{event.preventDefault();$('login-error').textContent='';try{const login=await api('/api/login',{password:$('password').value});csrf=login.csrf;$('password').value='';await load();}catch(e){$('login-error').textContent=e.message;}};
$('logout').onclick=async()=>{try{await api('/api/logout',{});csrf=null;state=null;$('application').hidden=true;$('login').hidden=false;$('password').focus();}catch(e){toast(e.message);}};
async function load(){state=await api('/api/state');portableAccess=!!state.portable||portableAccess;visual=null;$('login').hidden=true;$('portable-access').hidden=true;$('application').hidden=false;await refreshView();}
async function start(){try{const session=await api('/api/session');portableAccess=!!session.portable;desktopAccess=!!session.desktop;csrf=session.csrf;$('demo-login').hidden=!session.demo;if(session.authenticated)await load();else showAccess();}catch(e){showAccess(desktopAccess?'Radici non risponde. Chiudi e riapri il programma.':portableAccess?'Radici non risponde. Riaprilo dalla chiavetta e usa la nuova pagina.':e.message);}}
$('portable-retry').onclick=()=>start();
start();

// Correct a mistaken relationship without deleting either person's record.
const linksButton=document.createElement('button');linksButton.id='correct-links';linksButton.className='quiet';linksButton.textContent='Correggi legami';$('more-person').after(linksButton);
const linksDialog=document.createElement('dialog');linksDialog.id='links-dialog';linksDialog.innerHTML='<div class="dialog-heading"><h2>Legami della persona</h2><button class="close" type="button" aria-label="Chiudi">×</button></div><p id="links-name"></p><div id="links-list"></div><p id="unlink-note" class="info-box" hidden></p><p id="links-error" class="error" role="alert"></p><div class="dialog-actions"><button id="unlink-confirm" class="danger" hidden>Conferma: rimuovi solo il legame</button></div><p class="layout-note">Per aggiungere il legame corretto, usa Genitore, Compagno o Figlio e scegli «Sì, scelgo una persona già presente». Non devi ricreare la persona.</p>';document.body.append(linksDialog);
linksDialog.querySelector('.close').onclick=()=>linksDialog.close();let unlinkFamily=null;
linksButton.onclick=()=>{
  if(!selected){toast('Scegli prima una persona.');return;}
  unlinkFamily=null;$('unlink-confirm').hidden=true;$('unlink-note').hidden=true;$('links-error').textContent='';$('links-name').textContent=fullName(person());$('links-list').replaceChildren();
  const families=state.families.filter(f=>f.parents.includes(selected)||f.children.includes(selected));
  for(const f of families){const row=document.createElement('div');row.className='archive-option';const p=document.createElement('p');p.textContent=(f.parents.includes(selected)?'Genitore / compagno nella famiglia di ':'Figlio/a nella famiglia di ')+f.parents.map(id=>state.people.find(p=>p.id===id)).filter(Boolean).map(fullName).join(' e ');const b=document.createElement('button');b.className='secondary';b.textContent='Rimuovi questo legame';b.onclick=()=>{unlinkFamily=f.id;$('unlink-note').hidden=false;$('unlink-note').textContent='La persona e i suoi dati resteranno nell’albero. Sarà tolto solo il suo ruolo in questa famiglia. Puoi annullare durante questa sessione.';$('unlink-confirm').hidden=false;};row.append(p,b);$('links-list').append(row);}
  if(!families.length)$('links-list').textContent='Per ora questa persona non ha legami. Puoi collegarla a chi è già nell’albero.';
  linksDialog.showModal();
};
$('unlink-confirm').onclick=async()=>{if(!unlinkFamily)return;$('unlink-confirm').disabled=true;if(await act('unlink',{id:selected,family:unlinkFamily,confirm:true})){linksDialog.close();toast('Legame rimosso. La persona è conservata. Puoi annullare.');}$('unlink-confirm').disabled=false;};


// Secondary operations stay one level away from the three everyday actions.
const moreActions=document.createElement('details');moreActions.className='person-more';const moreSummary=document.createElement('summary');moreSummary.textContent='Altre azioni';moreActions.append(moreSummary);const moreMenu=document.createElement('div');moreMenu.className='person-more-menu';moreActions.append(moreMenu);document.querySelector('.selection-actions').append(moreActions);
for(const id of ['edit-person','more-person','correct-links','delete-person'])moreMenu.append($(id));
document.addEventListener('click',event=>{if(!moreActions.contains(event.target))moreActions.open=false;});
