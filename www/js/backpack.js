'use strict';
async function refreshBackpack() {
  const power = document.getElementById('power');
  try {
    const response = await fetch('/api/backpack/status', { cache: 'no-store' });
    if (response.redirected) { window.location.href = '/login.html'; return; }
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || 'Status unavailable');
    power.textContent = data.power ? `Current power mode: ${data.power.name}` : 'Power mode unavailable';
    document.getElementById('audio').textContent = data.audio_ready
      ? 'Headset connected. Spoken confirmations are enabled.'
      : 'Headset disconnected. Completed requests will be announced when it reconnects.';
    const list = document.getElementById('actions');
    list.replaceChildren();
    for (const action of data.actions) {
      const item = document.createElement('li');
      item.textContent = `${action.message} (${action.state})`;
      list.append(item);
    }
    if (!data.actions.length) list.textContent = 'No power-change requests yet.';
  } catch (error) {
    power.textContent = error.message || 'Status unavailable';
  }
}
refreshBackpack();
setInterval(refreshBackpack, 5000);
