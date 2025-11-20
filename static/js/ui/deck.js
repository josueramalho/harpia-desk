import { store } from '../store.js';
import { executeAction } from '../actions.js';
import { openEditModal } from './editor.js';
import { fetchApi } from '../utils.js';

let gridElement = null;

export function initDeck() {
    // Busca o elemento APENAS quando a função inicia (garante que o HTML já existe)
    gridElement = document.getElementById('streamdeck-grid');
    
    if (!gridElement) {
        console.error("Elemento 'streamdeck-grid' não encontrado no HTML!");
        return;
    }

    // Re-renderiza sempre que a config ou o deck atual mudar
    store.subscribe('deckConfig', renderDeck);
    store.subscribe('currentDeckId', renderDeck);
    store.subscribe('isEditMode', renderDeck);
    store.subscribe('buttonStates', renderDeck); // Atualiza visual quando estado muda

    // Inicializa Drag and Drop com verificação de segurança
    if (typeof Sortable !== 'undefined') {
        new Sortable(gridElement, {
            animation: 150,
            ghostClass: 'sortable-ghost',
            onStart: () => {
                // Bloqueia drag se não estiver em edição
                if (!store.get('isEditMode')) return false; 
            },
            onEnd: handleReorder
        });
    } else {
        console.warn("Aviso: Biblioteca SortableJS não carregou. Reorganização desativada.");
    }
}

function renderDeck() {
    if (!gridElement) return;
    
    gridElement.innerHTML = '';
    const currentDeckId = store.get('currentDeckId');
    const fullConfig = store.get('deckConfig');
    const isEditMode = store.get('isEditMode');
    const buttonStates = store.get('buttonStates');

    // Proteção se a config ainda não carregou
    if (!fullConfig || !fullConfig.decks) return;

    const buttons = fullConfig.decks[currentDeckId] || {};

    for (let i = 0; i < 16; i++) { // 16 Slots fixos
        const slotId = `slot-${i}`;
        const config = buttons[slotId];
        const btn = document.createElement('div');
        
        btn.dataset.slotId = slotId;
        
        if (config) {
            btn.className = `deck-button ${getActionClass(config)}`;
            btn.innerHTML = generateButtonContent(config);
            
            if (config.is_stateful && buttonStates[slotId]) {
                btn.classList.add('is-active');
            }

            btn.onclick = () => {
                if (isEditMode) openEditModal(slotId, config);
                else executeAction(config, btn);
            };
        } else {
            btn.className = 'deck-button empty';
            btn.innerHTML = `<i class="fa-solid fa-plus"></i>`;
            btn.onclick = () => { if (isEditMode) openEditModal(slotId, null); };
        }
        
        gridElement.appendChild(btn);
    }
}

async function handleReorder(evt) {
    if (evt.oldIndex === evt.newIndex) return;

    const deckId = store.get('currentDeckId');
    const buttonsInOrder = gridElement.querySelectorAll('.deck-button');
    const newLayout = {};

    // Reconstrói o objeto de config baseado na nova ordem do DOM
    buttonsInOrder.forEach((el, index) => {
        const oldSlotId = el.dataset.slotId;
        const config = store.get('deckConfig').decks[deckId][oldSlotId];
        if (config) {
            newLayout[`slot-${index}`] = config;
        }
    });

    // Atualiza store localmente para evitar flicker
    const fullConfig = store.get('deckConfig');
    fullConfig.decks[deckId] = newLayout;
    store.updateDeckConfig(fullConfig);

    // Salva no backend
    try {
        await fetchApi('/api/save_deck_layout', {
            method: 'POST',
            body: JSON.stringify({ deck_id: deckId, buttons: newLayout })
        });
    } catch (e) {
        console.error("Falha ao salvar ordem", e);
    }
}

function getActionClass(config) {
    if (!config.actions_on || !config.actions_on.length) return '';
    const type = config.actions_on[0].type;
    if (type === 'sound') return 'sound';
    if (type === 'hotkey' || type === 'open_deck') return 'hotkey';
    if (type.includes('obs')) return 'obs';
    if (type.includes('vts')) return 'vts';
    return '';
}

function generateButtonContent(config) {
    let iconHtml = '';
    if (config.icon && (config.icon.startsWith('http') || config.icon.startsWith('/uploads'))) {
        iconHtml = `<img src="${config.icon}">`;
    } else {
        iconHtml = `<i class="${config.icon || 'fa-solid fa-question'}"></i>`;
    }
    return `${iconHtml}<span>${config.label}</span>`;
}