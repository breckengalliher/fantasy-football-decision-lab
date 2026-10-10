// No third-party scripts. Provider credentials are publishable only; never passwords.
const RECORD = 'sdl_auth_session_v2';
const keys = [RECORD,'sdl_auth_refresh_token','sdl_auth_persistence','sdl_auth_persistence_expires_at'];
const send = (type,extra={}) => parent.postMessage({isStreamlitMessage:true,type,...extra},location.origin);
let recovery, latestArgs, lastSent, running = Promise.resolve();
const completed = new Map();
function read(key) { const raw=localStorage.getItem(key); if(raw===null)return null; try{return JSON.parse(raw);}catch{return raw;} }
function values() { const result={}; for(const key of keys){const value=read(key);if(value!==null)result[key]=value;}return result; }
function publish(record) {
  // The single canonical record is committed before compatibility mirrors.
  localStorage.setItem(RECORD,JSON.stringify(record));
  localStorage.setItem('sdl_auth_refresh_token',JSON.stringify(record.session.refresh_token));
  localStorage.setItem('sdl_auth_persistence',JSON.stringify(record.mode));
  if(record.expires_at)localStorage.setItem('sdl_auth_persistence_expires_at',JSON.stringify(record.expires_at));
  else localStorage.removeItem('sdl_auth_persistence_expires_at');
}
function clear() { for(const key of keys)localStorage.removeItem(key); }
function sessionId(session) {try{return JSON.parse(atob(session.access_token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).session_id;}catch{return null;}}
function publicKey(key) {if(key.startsWith('sb_publishable_'))return true;try{return JSON.parse(atob(key.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).role==='anon';}catch{return false;}}
function fresh(session) {
  // Expiry is only a refresh hint. Python verifies identity with Supabase /user.
  try { const part=session.access_token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'); const exp=JSON.parse(atob(part)).exp;return typeof exp==='number'&&Number.isFinite(exp)&&exp>Date.now()/1000+60;}catch{return false;}
}
async function rotate(args) {
  let record=read(RECORD);
  if(!record) {
    const token=read('sdl_auth_refresh_token');
    if(!token)return {status:'missing'};
    record={mode:read('sdl_auth_persistence')||'always',expires_at:read('sdl_auth_persistence_expires_at'),session:{refresh_token:token}};
  }
  if(record.mode==='remember'&&(!record.expires_at||!Number.isFinite(Date.parse(record.expires_at))||Date.parse(record.expires_at)<=Date.now())) {clear();return {status:'expired'};}
  if(fresh(record.session)&&(!args.force_revision||record.revision!==args.force_revision))return {status:'ready'};
  const url=new URL(args.auth_url);
  if(url.protocol!=='https:'||url.username||url.password||!publicKey(args.publishable_key))return {status:'unsupported'};
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),10000);
  try {
    const response=await fetch(url.origin+'/auth/v1/token?grant_type=refresh_token',{
      method:'POST',headers:{apikey:args.publishable_key,'Content-Type':'application/json'},
      body:JSON.stringify({refresh_token:record.session.refresh_token}),signal:controller.signal});
    if(!response.ok){if(response.status===429||response.status>=500)return {status:'retryable'};clear();return {status:'rejected'};}
    const payload=await response.json();
    if(!payload.access_token||!payload.refresh_token||!payload.user?.id)return {status:'retryable'};
    const session={access_token:payload.access_token,refresh_token:payload.refresh_token,expires_in:payload.expires_in||3600,user_id:payload.user.id,email:payload.user.email||''};
    const updated={version:2,revision:crypto.randomUUID(),mode:record.mode,expires_at:record.expires_at||null,session};
    // No await between the successful response and canonical publication.
    publish(updated);
    return {status:'ready'};
  } catch { return {status:'retryable'}; } finally {clearTimeout(timer);}
}
function emit(args,auth_result) {
  let value;try{value={values:values(),recovery,auth_result,operation_id:args.operation_id||'',ok:true};}
  catch{value={values:{},recovery,operation_id:args.operation_id||'',ok:false};}
  const serialized=JSON.stringify(value);
  if(serialized!==lastSent){lastSent=serialized;send('streamlit:setComponentValue',{value});}
}
async function process(args) {
  if(args.clear_recovery)recovery=undefined;
  const id=args.operation_id||'';
  if(id&&completed.has(id)){emit(args,completed.get(id));return;}
  let result;
  const work=async()=>{
    if(args.clear){const current=read(RECORD);if(current ? (current.revision===args.clear_revision||(args.clear_session_id&&sessionId(current.session)===args.clear_session_id)) : read('sdl_auth_refresh_token')===args.clear_token)clear();}
    for(const [key,value] of Object.entries(args.changes||{})){
      if(!keys.includes(key))continue;
      if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,JSON.stringify(value));
    }
    if(args.refresh)result=await rotate(args);
  };
  try{
    if(navigator.locks)await navigator.locks.request('sdl-auth-session-v2',work);
    else if(args.refresh)result={status:'unsupported'}; // Never use a racy localStorage spinlock.
    else await work();
    if(id){completed.set(id,result);if(completed.size>32)completed.delete(completed.keys().next().value);}
    emit(args,result);
  }catch{send('streamlit:setComponentValue',{value:{values:{},recovery,operation_id:id,ok:false}});}
  send('streamlit:setFrameHeight',{height:0});
}
try {
  const params=new URLSearchParams(parent.location.hash.slice(1));
  if(['recovery','invite'].includes(params.get('type'))&&params.get('refresh_token')){
    recovery={type:params.get('type'),refresh_token:params.get('refresh_token')};
    parent.history.replaceState(null,'',parent.location.pathname+parent.location.search);
  }else if(params.get('error')&&new URLSearchParams(parent.location.search).get('recovery')==='1'){
    recovery={error:true};parent.history.replaceState(null,'',parent.location.pathname+parent.location.search);
  }
}catch{}
addEventListener('message',event=>{
  if(event.source!==parent||event.origin!==location.origin||event.data.type!=='streamlit:render')return;
  latestArgs=event.data.args||{};
  const args=latestArgs;running=running.then(()=>process(args));
});
addEventListener('storage',event=>{if(keys.includes(event.key)&&latestArgs)running=running.then(()=>emit(latestArgs,undefined));});
send('streamlit:componentReady',{apiVersion:1});send('streamlit:setFrameHeight',{height:0});
