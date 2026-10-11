// Isolated QA only. Native event-to-paint measurements; no provider or controller calls.
(() => {
 const w=parent,d=w.document,key='sdl_qa_visible_timings_v1';
 if(w.__sdlQaTiming)return;
 const clock=()=>w.performance.timeOrigin+w.performance.now();
 let saved;try{saved=JSON.parse(w.sessionStorage.getItem(key)||'{}');}catch{saved={};}
 let receipts=Array.isArray(saved.receipts)?saved.receipts.slice(-100):[],active=saved.active||null,armed=null,lastMarker=null,timer=null,painting=false;
 const panel=d.createElement('details');panel.id='sdl-qa-timing';
 panel.style.cssText='position:fixed;bottom:4px;left:4px;z-index:999999;background:#fff;color:#111;border:1px solid #333;padding:6px;max-width:350px;font:12px sans-serif';
 panel.innerHTML='<summary>QA timing receipts</summary><label>Next measured action <select aria-label="Next measured action"><option value="command-center">Command Center</option><option value="comparison">Full comparison</option><option value="save">Save acknowledgment</option><option value="scoring">Scoring</option><option value="search">Search</option><option value="logs">Game logs</option></select></label><button type="button">Arm next action</button><p role="status"></p><pre aria-label="QA timing receipts" style="max-height:160px;overflow:auto;white-space:pre-wrap"></pre>';
 d.body.appendChild(panel);
 const status=panel.querySelector('[role=status]'),output=panel.querySelector('pre'),select=panel.querySelector('select');
 function persist(){try{w.sessionStorage.setItem(key,JSON.stringify({receipts,active}));}catch{status.textContent='Receipt storage unavailable';}}
 function display(){output.textContent=JSON.stringify(receipts);status.textContent=active?'Measuring '+active.kind:armed?'Armed '+armed:'Idle; '+receipts.length+' receipts';}
 function finish(result){if(!active)return;const a=active;active=null;painting=false;w.clearTimeout(timer);receipts.push({kind:a.kind,candidate:a.candidate,started_epoch_ms:a.start,elapsed_ms:Math.round((clock()-a.start)*10)/10,status:result,viewport:a.viewport});receipts=receipts.slice(-100);persist();display();}
 function deadline(){w.clearTimeout(timer);if(active)timer=w.setTimeout(()=>finish('timeout_incomplete'),Math.max(0,15000-(clock()-active.start)));}
 function visible(e){if(!e)return false;const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<w.innerHeight;}
 function observe(){
  if(!active||painting)return;
  const toast=Array.from(d.querySelectorAll('[data-testid="stToast"]')).find(e=>e.textContent.includes('Lineup saved')&&visible(e));
  if(active.kind==='save'&&!toast)return;
  if(active.kind!=='save'){
   if(!lastMarker||lastMarker.run===active.priorRun)return;
   const expected=active.kind==='command-center'?'Sunday Command Center':active.kind==='comparison'?'Decision Room':null;
   if(expected&&lastMarker.view!==expected)return;
   if(d.querySelector('[data-testid="stStatusWidget"]'))return;
  }
  painting=true;
  w.requestAnimationFrame(()=>w.requestAnimationFrame(()=>finish('complete')));
 }
 panel.querySelector('button').addEventListener('click',()=>{
  if(active){status.textContent='Already measuring; wait for receipt';return;}
  if(select.value==='save'&&Array.from(d.querySelectorAll('[data-testid="stToast"]')).some(e=>e.textContent.includes('Lineup saved')&&visible(e))){status.textContent='Wait for the previous save toast to disappear';return;}
  armed=select.value;display();
 });
 function start(e){
  if(!armed||active||panel.contains(e.target))return;
  if(e.type==='keydown'&&e.key!=='Enter')return;
  if(e.type==='click'&&!e.target.closest('button,a,label,[role="button"],[role="tab"],input[type="radio"]'))return;
  active={kind:armed,start:clock(),candidate:lastMarker?.candidate||'',priorRun:lastMarker?.run||'',viewport:[w.innerWidth,w.innerHeight]};armed=null;persist();display();deadline();
 }
 d.addEventListener('click',start,true);d.addEventListener('keydown',start,true);
 new w.MutationObserver(observe).observe(d.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['style','class','data-testid']});
 w.__sdlQaTiming={marker(value){if(active&&active.candidate!==value.candidate)finish('candidate_changed_incomplete');lastMarker=value;observe();}};
 display();deadline();
})();
