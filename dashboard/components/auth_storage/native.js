// Transport adapter only. AUTH_CORE is the unchanged, tested auth.js source.
// No credentials are placed in HTML, URLs, diagnostics or window properties.
const instances = new WeakMap();
function createBridge(deliver) {
  const events = {};
  const parent = {
    location: window.location, history: window.history,
    postMessage(message) {
      if (message.type === 'streamlit:setComponentValue') deliver(message.value);
    }
  };
  const addEventListener = (name, handler) => { events[name] = handler; };
  /* AUTH_CORE */
  return {
    render(args) {
      latestArgs = args;
      running = running.then(() => process(args));
      return running;
    },
    storage(event) { if (events.storage) events.storage(event); },
    resend() { lastSent = undefined; },
  };
}
export default function(component) {
  const {parentElement, data, setStateValue} = component;
  let instance = instances.get(parentElement);
  if (!instance) {
    instance = {active:false, setter:null};
    instance.bridge = createBridge(value => {
      if (instance.active) instance.setter('ack', value);
      else instance.missedAck = true;
    });
    instances.set(parentElement, instance);
  }
  instance.active = true;
  instance.setter = setStateValue;
  // Keep operation deduplication and the serialized queue across UI rerenders.
  // Re-acknowledge if an operation completed while temporarily unmounted.
  if (instance.missedAck) { instance.bridge.resend(); instance.missedAck = false; }
  instance.bridge.render(data || {});
  const storage = event => instance.bridge.storage(event);
  window.addEventListener('storage', storage);
  return () => {
    instance.active = false;
    window.removeEventListener('storage', storage);
  };
}
