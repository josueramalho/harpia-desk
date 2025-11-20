import { socket } from '../socket.js';

export function initStatus() {
    document.addEventListener('status-update', (e) => {
        const { service, connected, message } = e.detail;
        renderStatus(service, connected, message);
    });
}

function renderStatus(service, connected, message) {
    const targets = service === 'obs' 
        ? ['obs-status-message', 'obs-status-message-config'] 
        : ['vts-status-msg-main', 'vts-status-msg-config'];

    targets.forEach(id => {
        let el = document.getElementById(id);
        if (!el) el = createStatusElement(id, service);
        if (el) updateElementState(el, service, connected, message);
    });
}

function createStatusElement(id, service) {
    const isConfig = id.includes('config');
    
    // Seleciona o elemento de referência onde queremos inserir o alerta ANTES ou DEPOIS
    let referenceEl = null;
    let parentContainer = null;

    if (isConfig) {
        // Na aba config, queremos inserir antes do <hr> que está DENTRO do .panel
        const configTab = document.getElementById('config-tab-pane');
        if (configTab) {
            // Procura o painel interno
            const panel = configTab.querySelector('.panel');
            if (panel) {
                parentContainer = panel;
                referenceEl = panel.querySelector('hr'); // Insere antes da linha
            }
        }
    } else {
        // Na aba principal, queremos inserir antes do grid no painel do streamdeck
        parentContainer = document.getElementById('streamdeck-panel');
        if (parentContainer) {
            referenceEl = parentContainer.querySelector('.streamdeck-grid');
        }
    }

    if (!parentContainer) return null;

    const el = document.createElement('div');
    el.id = id;
    el.className = 'alert mt-2 d-flex justify-content-between align-items-center';
    
    if (referenceEl && referenceEl.parentNode === parentContainer) {
        parentContainer.insertBefore(el, referenceEl);
    } else {
        // Fallback: se não achar o elemento de referência, joga no topo
        parentContainer.prepend(el);
    }
    
    return el;
}

function updateElementState(el, service, connected, message) {
    el.className = `alert ${connected ? 'alert-success' : 'alert-danger'} mt-2 d-flex justify-content-between align-items-center`;
    el.innerHTML = '';

    const span = document.createElement('span');
    span.innerHTML = `<strong>${service.toUpperCase()}:</strong> ${message}`;
    el.appendChild(span);

    if (!connected) {
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-outline-light ms-2';
        btn.innerHTML = '<i class="fa-solid fa-rotate"></i> Reconectar';
        
        btn.onclick = () => {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spin fa-spinner"></i> Tentando...';
            socket.emit(`reconnect_${service}`);
            setTimeout(() => {
                if(btn && btn.isConnected) {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-rotate"></i> Reconectar';
                }
            }, 5000);
        };
        
        el.appendChild(btn);
    }
}