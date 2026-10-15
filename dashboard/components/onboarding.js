// Only the guide preference is accessed. Never enumerate storage or read auth.
const sent = new WeakMap();
export default function({parentElement, data, setStateValue}) {
  const dismiss = data?.dismiss === true;
  const key = 'sdl_onboarding_dismissed';
  let value;
  try {
    if (dismiss) localStorage.setItem(key, JSON.stringify('true'));
    let raw = localStorage.getItem(key);
    try { raw = JSON.parse(raw); } catch {}
    value = {ok:true, dismissed:raw === true || raw === 'true', write_ack:dismiss};
  } catch {
    value = {ok:false, dismissed:dismiss, write_ack:dismiss};
  }
  const encoded = JSON.stringify(value);
  if (sent.get(parentElement) !== encoded) {
    sent.set(parentElement, encoded);
    setStateValue('preference', value);
  }
}
