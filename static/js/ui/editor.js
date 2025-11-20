import { store } from '../store.js';
import { fetchApi } from '../utils.js';

const modalElement = document.getElementById('edit-modal');
const modal = new bootstrap.Modal(modalElement);
let currentSlotId = null;
let cropper = null;

export function initEditor() {
    // Toggle Edit Mode
    document.querySelectorAll('#edit-deck-button-main, #edit-deck-button-config').forEach(btn => {
        btn.addEventListener('click', () => {
            const isEdit = !store.get('isEditMode');
            store.set('isEditMode', isEdit);
            document.body.classList.toggle('edit-mode', isEdit);
            
            const html = isEdit ? '<i class="fa-solid fa-check"></i> Concluir' : '<i class="fa-solid fa-pen-to-square"></i> Editar';
            document.querySelectorAll('#edit-deck-button-main, #edit-deck-button-config').forEach(b => b.innerHTML = html);
        });
    });

    // Form Listeners
    document.getElementById('save-button').onclick = saveButtonConfig;
    document.getElementById('delete-button').onclick = deleteButtonConfig;
    
    // Image Upload
    document.getElementById('button-image-upload').addEventListener('change', handleImageUpload);
    
    // Action Buttons
    document.querySelector('.add-action-button[data-action-list="on"]').onclick = () => createActionCard('on');
    document.querySelector('.add-action-button[data-action-list="off"]').onclick = () => createActionCard('off');
}

export function openEditModal(slotId, config) {
    currentSlotId = slotId;
    document.getElementById('edit-button-form').reset();
    document.getElementById('action-list-on').innerHTML = '';
    document.getElementById('action-list-off').innerHTML = '';
    
    // Reset imagem e cropper
    document.getElementById('cropper-container').style.display = 'none';
    if(cropper) { cropper.destroy(); cropper = null; }

    if (config) {
        document.getElementById('modal-title').textContent = "Editar Botão";
        document.getElementById('button-label').value = config.label || '';
        document.getElementById('button-is-stateful').checked = config.is_stateful || false;
        
        // Se tiver ícone
        if (config.icon) {
            if (config.icon.startsWith('http') || config.icon.startsWith('/uploads')) {
                document.querySelector('.tab-button[data-tab="link"]').click();
                document.getElementById('button-image-link').value = config.icon;
            } else {
                document.querySelector('.tab-button[data-tab="icon"]').click();
                document.getElementById('button-icon').value = config.icon;
            }
        }
        
        (config.actions_on || []).forEach(a => createActionCard('on', a));
        if(config.is_stateful) (config.actions_off || []).forEach(a => createActionCard('off', a));
    } else {
        document.getElementById('modal-title').textContent = "Novo Botão";
        createActionCard('on'); 
    }
    
    modal.show();
}

function createActionCard(listType, actionConfig = null) {
    const listId = listType === 'on' ? 'action-list-on' : 'action-list-off';
    const container = document.getElementById(listId);
    
    const template = document.getElementById('action-template').content.cloneNode(true);
    const card = template.querySelector('.action-card');
    const select = card.querySelector('.action-type-select');
    const paramsContainer = card.querySelector('.action-params-template');

    populateActionTypes(select);

    select.addEventListener('change', () => {
        paramsContainer.querySelectorAll('.action-params').forEach(p => p.style.display = 'none');
        const activeParams = paramsContainer.querySelector(`.action-params[data-param-for="${select.value}"]`);
        
        if (activeParams) {
            activeParams.style.display = 'block';
            // Se mudou o tipo manualmente, limpa params. Se veio do config, popula.
            const currentParams = (actionConfig && actionConfig.type === select.value) ? actionConfig.params : {};
            hydrateParams(select.value, activeParams, currentParams);
        }
    });

    card.querySelector('.remove-action-button').onclick = () => card.remove();
    container.appendChild(card);

    if (actionConfig) {
        select.value = actionConfig.type;
        select.dispatchEvent(new Event('change'));
    }
}

function populateActionTypes(select) {
    select.innerHTML = `
        <option value="">-- Selecione --</option>
        <optgroup label="OBS">
            <option value="obs_scene">Mudar Cena</option>
            <option value="obs_source">Alternar Fonte</option>
            <option value="obs_set_mute_on">Mutar</option>
            <option value="obs_set_mute_off">Desmutar</option>
            <option value="obs_stream_toggle">Alternar Live</option>
            <option value="obs_record_toggle">Alternar Gravação</option>
        </optgroup>
        <optgroup label="Sistema">
            <option value="sound">Tocar Som</option>
            <option value="hotkey">Atalho de Teclado</option>
            <option value="open_deck">Abrir Pasta</option>
        </optgroup>
        <optgroup label="VTube Studio">
            <option value="vts_hotkey">Disparar Hotkey</option>
        </optgroup>
    `;
}

function hydrateParams(type, container, params = {}) {
    // --- OBS SCENES ---
    if (type === 'obs_scene' || type === 'obs_source') {
        const sceneSelect = container.querySelector('.param-scene-name') || container.querySelector('.param-source-scene');
        const sceneList = store.get('obsScenes') || [];
        
        // Popula Cenas
        populateSelect(sceneSelect, sceneList.map(s => ({ value: s.name, label: s.name })), params?.scene_name);

        // Lógica especial para Fontes (dependente da cena)
        if (type === 'obs_source') {
            const sourceSelect = container.querySelector('.param-source-name');
            
            const updateSources = (sceneName) => {
                const sceneData = sceneList.find(s => s.name === sceneName);
                const sources = sceneData ? sceneData.sources : [];
                // Passamos o params.source_name apenas se for a cena salva, senão reseta
                const valToSelect = (sceneName === params?.scene_name) ? params?.source_name : '';
                
                populateSelect(sourceSelect, sources.map(s => ({ value: s.name, label: s.name })), valToSelect);
            };

            // Listener para mudar fontes quando mudar cena
            sceneSelect.onchange = () => updateSources(sceneSelect.value);
            
            // Inicializa
            updateSources(params?.scene_name);
        }
    }
    
    // --- OBS AUDIO ---
    if (type === 'obs_set_mute_on' || type === 'obs_set_mute_off') {
        const audioSelect = container.querySelector('.param-audio-input-name');
        const audioList = store.get('obsAudioSources') || [];
        populateSelect(audioSelect, audioList.map(a => ({ value: a.name, label: a.name })), params?.input_name);
    }
    
    // --- VTS HOTKEYS ---
    if (type === 'vts_hotkey') {
        const select = container.querySelector('.param-vts-hotkey-id');
        const vtsList = store.get('vtsHotkeys') || [];
        populateSelect(select, vtsList.map(h => ({ value: h.hotkeyID, label: `${h.name} (${h.type})` })), params?.hotkey_id);
    }
    
    // --- CAMPOS DE TEXTO SIMPLES ---
    if (params?.file_name) {
        const inp = container.querySelector('.param-file-name');
        if (inp) inp.value = params.file_name;
    }
    if (params?.keys_str) {
         const inp = container.querySelector('.param-keys-str');
         if (inp) inp.value = params.keys_str;
         // Aqui você poderia chamar a função de renderizar as pílulas visuais das hotkeys
    }
    if (params?.deck_id) {
        const inp = container.querySelector('.param-deck-id');
        if (inp) inp.value = params.deck_id;
    }
}

// --- A CORREÇÃO MÁGICA ESTÁ AQUI ---
function populateSelect(selectElement, items, selectedValue) {
    if (!selectElement) return;
    
    selectElement.innerHTML = '<option value="">-- Selecione --</option>';
    
    // 1. Adiciona itens disponíveis (da conexão ao vivo)
    items.forEach(item => {
        const opt = new Option(item.label, item.value);
        selectElement.add(opt);
    });

    // 2. Se tiver um valor salvo...
    if (selectedValue) {
        // Verifica se ele já está na lista
        const exists = Array.from(selectElement.options).some(opt => opt.value === selectedValue);
        
        // 3. Se NÃO estiver na lista (ex: OBS desconectado), cria a "Opção Fantasma"
        if (!exists) {
            const label = `[Salvo] ${selectedValue}`; 
            const opt = new Option(label, selectedValue);
            // Opcional: Adicionar estilo visual para indicar que está offline/salvo
            opt.style.color = 'orange'; 
            selectElement.add(opt);
        }
        
        // 4. Seleciona o valor
        selectElement.value = selectedValue;
    }
}

async function saveButtonConfig() {
    const config = {
        label: document.getElementById('button-label').value,
        is_stateful: document.getElementById('button-is-stateful').checked,
        actions_on: readActionsFromList('action-list-on'),
        actions_off: readActionsFromList('action-list-off'),
        // Verifica qual aba de imagem está ativa
        icon: getIconValue()
    };

    try {
        await fetchApi('/api/save_button', {
            method: 'POST',
            body: JSON.stringify({
                slot_id: currentSlotId,
                deck_id: store.get('currentDeckId'),
                config
            })
        });
        modal.hide();
    } catch(e) { alert("Erro ao salvar: " + e.message); }
}

function getIconValue() {
    // Lógica simples para pegar ícone baseado na aba ativa
    const activeTab = document.querySelector('.tab-button.active');
    if (activeTab && activeTab.dataset.tab === 'link') {
        return document.getElementById('button-image-link').value;
    } else if (activeTab && activeTab.dataset.tab === 'icon') {
        return document.getElementById('button-icon').value;
    }
    // Para upload, assumimos que o upload já retornou URL e foi colocado em algum lugar,
    // ou usamos a lógica do seu script original de tratar o upload separadamente.
    return document.getElementById('button-icon').value; // Fallback
}

function readActionsFromList(listId) {
    const actions = [];
    document.getElementById(listId).querySelectorAll('.action-card').forEach(card => {
        const type = card.querySelector('.action-type-select').value;
        if(!type) return;
        
        const paramsContainer = card.querySelector(`.action-params[data-param-for="${type}"]`);
        const params = {};
        
        paramsContainer.querySelectorAll('input, select').forEach(input => {
            const key = input.className.split(' ').find(c => c.startsWith('param-'))?.replace('param-', '').replace(/-/g, '_');
            if(key) params[key] = input.value;
        });
        
        actions.push({ type, params });
    });
    return actions;
}

async function deleteButtonConfig() {
    if(!confirm("Deletar?")) return;
    await fetchApi('/api/delete_button', {
        method: 'POST',
        body: JSON.stringify({ slot_id: currentSlotId, deck_id: store.get('currentDeckId') })
    });
    modal.hide();
}

function handleImageUpload(e) {
    const file = e.target.files[0];
    if(file) {
        const reader = new FileReader();
        reader.onload = (evt) => {
            const img = document.getElementById('image-to-crop');
            img.src = evt.target.result;
            document.getElementById('cropper-container').style.display = 'block';
            if(cropper) cropper.destroy();
            cropper = new Cropper(img, { aspectRatio: 1, viewMode: 1 });
        };
        reader.readAsDataURL(file);
    }
}