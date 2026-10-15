const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const folder=path.join(__dirname,'../dashboard/components/auth_storage');
const source=fs.readFileSync(path.join(folder,'native.js'),'utf8').replace('/* AUTH_CORE */',fs.readFileSync(path.join(folder,'auth.js'),'utf8')).replace('export default function(component)','function mount(component)');
function setup() {
 const store=new Map(),listeners=new Set(),values=[],timers=[]; let writes=0,requests=0,tail=Promise.resolve();
 const context=vm.createContext({window:{location:{hash:'',search:'',pathname:'/'},history:{replaceState(){}},addEventListener:(_n,fn)=>listeners.add(fn),removeEventListener:(_n,fn)=>listeners.delete(fn)},location:{origin:'https://qa.example.test'},navigator:{locks:{request:(_n,fn)=>{let next=tail.then(fn);tail=next.catch(()=>{});return next;}}},localStorage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>{writes++;store.set(k,v);},removeItem:k=>store.delete(k)},URL,URLSearchParams,AbortController,setTimeout,clearTimeout,Date,Map,WeakMap,JSON,Number,Promise,Object,crypto:require('node:crypto').webcrypto,atob:x=>Buffer.from(x,'base64').toString(),fetch:async()=>{requests++;throw Error('No provider calls expected');}});
 vm.runInContext(source,context);
 const element={};
 const render=data=>{context.component={parentElement:element,data,setStateValue:(name,value)=>values.push({name,value})};return vm.runInContext('mount(component)',context);};
 const flush=()=>new Promise(resolve=>setImmediate(resolve));
 return {store,listeners,values,render,flush,writes:()=>writes,requests:()=>requests};
}
test('native first load acknowledges without iframe messages or provider requests',async()=>{const e=setup();e.render({});await e.flush();assert.equal(e.values.length,1);assert.equal(e.values[0].value.ok,true);assert.equal(e.requests(),0);});
test('identical native rerender does not cause an acknowledgment loop',async()=>{const e=setup();const cleanup=e.render({});await e.flush();cleanup();e.render({});await e.flush();assert.equal(e.values.length,1);assert.equal(e.listeners.size,1);});
test('native operation dedup survives cleanup and rerender',async()=>{const e=setup(),data={operation_id:'save',changes:{sdl_auth_persistence:'remember'}};const cleanup=e.render(data);await e.flush();cleanup();e.render(data);await e.flush();assert.equal(e.writes(),1);assert.equal(e.requests(),0);});
test('pending write completes once while unmounted and is acknowledged after remount',async()=>{const e=setup(),data={operation_id:'save',changes:{sdl_auth_persistence:'remember'}};const cleanup=e.render(data);cleanup();await e.flush();assert.equal(e.values.length,0);assert.equal(e.writes(),1);e.render(data);await e.flush();assert.equal(e.values.length,1);assert.equal(e.writes(),1);});
test('storage listener cleans up without clearing persisted state',async()=>{const e=setup();e.store.set('sdl_auth_persistence','"remember"');const cleanup=e.render({});await e.flush();assert.equal(e.listeners.size,1);cleanup();assert.equal(e.listeners.size,0);assert.equal(e.store.get('sdl_auth_persistence'),'"remember"');});
