const list = document.getElementById("list");

async function api(path, method = "GET") {
  const res = await fetch("/api" + path, { method });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function render(services) {
  list.innerHTML = "";
  for (const s of services) {
    const link = s.url_port
      ? `<a href="http://${location.hostname}:${s.url_port}" target="_blank" style="color:#8ab4f8">apri</a>`
      : "";
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = `
      <div class="row">
        <div><strong>${s.name}</strong> <span class="badge ${s.status}">${s.status}</span><br>
          <small>${s.description}</small></div>
        <div>${link}
          <button data-a="start">Start</button>
          <button data-a="stop">Stop</button>
          <button data-a="restart">Restart</button>
        </div>
      </div>`;
    el.querySelectorAll("button").forEach((b) => {
      b.onclick = async () => {
        b.disabled = true;
        try { await api(`/services/${s.id}/${b.dataset.a}`, "POST"); }
        catch (e) { alert(e.message); }
        load();
      };
    });
    list.appendChild(el);
  }
}

async function load() {
  try { render(await api("/services")); }
  catch (e) { list.textContent = "Errore: " + e.message; }
}

load();
setInterval(load, 10000);
