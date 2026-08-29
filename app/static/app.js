const state = {
  imageFile: null,
  preset: 'standard',
  field_filter: 'all',
  xw_angle: 35,
  yz_angle: 20,
  density: 0.5,
  stroke_thickness: 2,
  glow_strength: 0.45,
  floor_shear: 0.18,
  domains_enabled: {}
};

const presets = {
  standard: { density: 0.5, stroke_thickness: 2, glow_strength: 0.45, floor_shear: 0.18 },
  maximum: { density: 0.9, stroke_thickness: 4, glow_strength: 0.8, floor_shear: 0.22 },
  draft: { density: 0.3, stroke_thickness: 1, glow_strength: 0.25, floor_shear: 0.12 }
};

const statusEl = document.getElementById('status');
const renderedImage = document.getElementById('renderedImage');
const controlMap = {
  xwAngle: ['xw_angle', 'xwVal'],
  yzAngle: ['yz_angle', 'yzVal'],
  density: ['density', 'densityVal'],
  stroke: ['stroke_thickness', 'strokeVal'],
  glow: ['glow_strength', 'glowVal'],
  shear: ['floor_shear', 'shearVal']
};

function setStatus(msg) {
  statusEl.textContent = msg;
}

function updateDisplayValues() {
  Object.entries(controlMap).forEach(([id, [key, outId]]) => {
    const value = state[key];
    document.getElementById(outId).textContent = typeof value === 'number' ? Number(value.toFixed(2)) : value;
    const input = document.getElementById(id);
    if (id === 'stroke') {
      input.value = parseInt(value, 10);
    } else {
      input.value = value;
    }
  });
}

function applyPreset(name) {
  const preset = presets[name];
  if (!preset) return;
  state.preset = name;
  Object.assign(state, preset);
  updateDisplayValues();
}

async function render(highRes = false) {
  try {
    setStatus(highRes ? 'Exporting...' : 'Rendering...');
    const endpoint = highRes ? '/api/export' : '/api/render';
    const formData = new FormData();
    formData.append('config', JSON.stringify(state));
    if (state.imageFile) {
      formData.append('image', state.imageFile);
    }

    const response = await fetch(endpoint, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: 'Request failed' }));
      throw new Error(err.error || 'Render failed');
    }

    const ms = parseFloat(response.headers.get('X-Render-Time-Ms') || '0');
    const target = parseFloat(response.headers.get('X-Frame-Target-Ms') || '33');

    const blob = await response.blob();
    if (highRes) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'higdimetric-render.png';
      a.click();
      URL.revokeObjectURL(url);
      setStatus(`High-res export downloaded (${ms.toFixed(1)}ms)`);
      return;
    }

    renderedImage.src = URL.createObjectURL(blob);
    setStatus(`Ready (${ms.toFixed(1)}ms, target ${target.toFixed(0)}ms)`);
  } catch (err) {
    setStatus(err.message);
  }
}

let timer = null;
function scheduleRender() {
  clearTimeout(timer);
  timer = setTimeout(() => render(false), 120);
}

function init() {
  document.querySelectorAll('.domain-toggle').forEach((el) => {
    state.domains_enabled[el.dataset.domain] = true;
    el.addEventListener('change', () => {
      state.domains_enabled[el.dataset.domain] = el.checked;
      scheduleRender();
    });
  });

  document.getElementById('fieldFilter').addEventListener('change', (e) => {
    state.field_filter = e.target.value;
    scheduleRender();
  });

  document.getElementById('presetSelect').addEventListener('change', (e) => {
    applyPreset(e.target.value);
    scheduleRender();
  });

  Object.entries(controlMap).forEach(([id, [key]]) => {
    document.getElementById(id).addEventListener('input', (e) => {
      const raw = e.target.value;
      state[key] = key === 'stroke_thickness' ? parseInt(raw, 10) : parseFloat(raw);
      updateDisplayValues();
      scheduleRender();
    });
  });

  document.getElementById('imageUpload').addEventListener('change', (e) => {
    state.imageFile = e.target.files[0] || null;
    scheduleRender();
  });

  document.getElementById('loadDefault').addEventListener('click', () => {
    state.imageFile = null;
    document.getElementById('imageUpload').value = '';
    scheduleRender();
  });

  document.getElementById('exportBtn').addEventListener('click', () => render(true));

  applyPreset(state.preset);
  render(false);
}

init();
