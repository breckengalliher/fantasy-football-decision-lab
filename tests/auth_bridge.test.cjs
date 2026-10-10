// Deterministic JavaScript unit tests; not substitutes for hosted browser receipts.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../dashboard/components/auth_storage/auth.js'),'utf8');
const token=(exp,id='family-a')=>'test.'+Buffer.from(JSON.stringify({exp,session_id:id})).toString('base64url')+'.unsigned';
const session=(exp=1,id='family-a',user='a')=>({access_token:token(exp,id),refresh_token:'fake-refresh-'+id,expires_in:3600,user_id:user,email:user+'@example.test'});
const record=(exp=1,id='family-a',user='a')=>({version:2,revision:'revision-'+id,mode:'always',expires_at:null,session:session(exp,id,user)});
function env(initial=record(),fetchImpl){
 const store=new Map(initial?[['sdl_auth_session_v2',JSON.stringify(initial)]]:[]); let requests=0,lockTail=Promise.resolve();
 const locks={request:(_name,work)=>{let next=lockTail.then(work);lockTail=next.catch(()=>{});return next;}};
 const create=(supported=true)=>{
  const messages=[],events={},parent={postMessage:message=>messages.push(message),location:{hash:'',search:'',pathname:'/'},history:{replaceState(){}}};
  const context=vm.createContext({parent,location:{origin:'https://qa.example.test'},navigator:supported?{locks}:{},URL,URLSearchParams,AbortController,setTimeout,clearTimeout,Date,Map,JSON,Number,Promise,Object,
   crypto:{randomUUID:()=>require('node:crypto').randomUUID()},atob:x=>Buffer.from(x,'base64').toString(),
   addEventListener:(kind,handler)=>events[kind]=handler,
   localStorage:{getItem:key=>store.get(key)??null,setItem:(key,value)=>store.set(key,value),removeItem:key=>store.delete(key)},
   fetch:async(...args)=>{requests++;if(fetchImpl)return fetchImpl(...args);return {ok:true,status:200,json:async()=>({access_token:token(Date.now()/1000+3600),refresh_token:'rotated-once',expires_in:3600,user:{id:'a',email:'a@example.test'}})};}});
  vm.runInContext(source,context);return {context,messages,events,process:args=>{context.args=args;return vm.runInContext('process(args)',context);}};
 };
 return {store,create,requests:()=>requests,read:()=>JSON.parse(store.get('sdl_auth_session_v2')||'null')};
}
const args=id=>({operation_id:id,auth_url:'https://qa.supabase.co',publishable_key:'sb_publishable_unit_test',refresh:true});
test('two tabs expire together: one provider rotation, both acknowledge newest record',async()=>{
 const e=env(),a=e.create(),b=e.create();await Promise.all([a.process(args('a')),b.process(args('b'))]);assert.equal(e.requests(),1);assert.equal(e.read().session.refresh_token,'rotated-once');assert.equal(a.messages.at(-2).value.values.sdl_auth_session_v2.session.refresh_token,'rotated-once');
});
test('reload/new iframe uses fresh shared access without rotating',async()=>{const e=env(record(Date.now()/1000+3600));await e.create().process(args('reload'));await e.create().process(args('reopen'));assert.equal(e.requests(),0);});
test('replayed acknowledgement never rotates twice',async()=>{const e=env(),tab=e.create();await tab.process(args('one'));await tab.process(args('one'));assert.equal(e.requests(),1);});
test('legacy token migration is serialized and retains remember deadline',async()=>{const e=env(null);const deadline=new Date(Date.now()+86400000).toISOString();e.store.set('sdl_auth_refresh_token',JSON.stringify('legacy'));e.store.set('sdl_auth_persistence',JSON.stringify('remember'));e.store.set('sdl_auth_persistence_expires_at',JSON.stringify(deadline));await Promise.all([e.create().process(args('a')),e.create().process(args('b'))]);assert.equal(e.requests(),1);assert.equal(e.read().expires_at,deadline);});
test('expired remember deadline clears without provider request',async()=>{const r=record();r.mode='remember';r.expires_at='2000-01-01T00:00:00Z';const e=env(r);await e.create().process(args('expire'));assert.equal(e.requests(),0);assert.equal(e.read(),null);});
test('no Web Locks: do not issue unsafe refresh',async()=>{const e=env(),tab=e.create(false);await tab.process(args('unsupported'));assert.equal(e.requests(),0);assert.ok(e.read());assert.equal(tab.messages.findLast(x=>x.value).value.auth_result.status,'unsupported');});
test('timeout/provider outage preserves last credential and revision',async()=>{const e=env(record(),async()=>{throw Error('controlled timeout');});await e.create().process(args('outage'));assert.equal(e.read().revision,'revision-family-a');});
test('rejected refresh clears remembered credentials',async()=>{const e=env(record(),async()=>({ok:false,status:400}));await e.create().process(args('rejected'));assert.equal(e.read(),null);});
test('stale logout cannot delete a newer login or different account',async()=>{const e=env(record(Date.now()/1000+3600,'family-b','b'));await e.create().process({operation_id:'logout-a',clear:true,clear_revision:'revision-family-a',clear_session_id:'family-a'});assert.equal(e.read().session.user_id,'b');});
test('logout clears same auth family even after refresh changes revision',async()=>{const e=env(record(Date.now()/1000+3600));await e.create().process({operation_id:'logout',clear:true,clear_revision:'older-revision',clear_session_id:'family-a'});assert.equal(e.read(),null);});
test('server secret cannot be transmitted to browser provider request',async()=>{const e=env();await e.create().process({...args('secret'),publishable_key:'sb_secret_not_allowed'});assert.equal(e.requests(),0);});
test('storage change informs another tab without timer or provider request',async()=>{const e=env(record(Date.now()/1000+3600)),tab=e.create();tab.events.message({source:tab.context.parent,origin:'https://qa.example.test',data:{type:'streamlit:render',args:{}}});await vm.runInContext('running',tab.context);e.store.clear();tab.events.storage({key:'sdl_auth_session_v2'});await vm.runInContext('running',tab.context);assert.equal(Object.keys(tab.messages.findLast(x=>x.value).value.values).length,0);assert.equal(e.requests(),0);});
