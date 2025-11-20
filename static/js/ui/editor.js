import { store } from '../store.js';
import { fetchApi } from '../utils.js';

const modalElement = document.getElementById('edit-modal');
const modal = new bootstrap.Modal(modalElement);
let currentSlotId = null;
let cropper = null;
let originalFile = null; // Armazena o arquivo original para GIFs

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

    // Lógica de Abas
    document.querySelectorAll('.tab-button').forEach(button => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            button.classList.add('active');
            
            const tabId = button.dataset.tab;
            const content = document.getElementById(`${tabId}-tab`);
            if (content) content.classList.add('active');

            if (tabId !== 'upload' && cropper) {
                destroyCropper();
            }
        });
    });

    // Listeners
    document.getElementById('save-button').onclick = saveButtonConfig;
    document.getElementById('delete-button').onclick = deleteButtonConfig;
    document.getElementById('button-image-upload').addEventListener('change', handleImageUpload);
    
    document.querySelector('.add-action-button[data-action-list="on"]').onclick = () => createActionCard('on');
    document.querySelector('.add-action-button[data-action-list="off"]').onclick = () => createActionCard('off');
}

function destroyCropper() {
    if (cropper) {
        cropper.destroy();
        cropper = null;
    }
    document.getElementById('cropper-container').style.display = 'none';
    document.getElementById('image-to-crop').src = '';
    originalFile = null;
}

export function openEditModal(slotId, config) {
    currentSlotId = slotId;
    document.getElementById('edit-button-form').reset();
    document.getElementById('action-list-on').innerHTML = '';
    document.getElementById('action-list-off').innerHTML = '';
    
    destroyCropper(); // Limpa estado anterior

    document.querySelector('.tab-button[data-tab="icon"]').click();

    if (config) {
        document.getElementById('modal-title').textContent = "Editar Botão";
        document.getElementById('button-label').value = config.label || '';
        document.getElementById('button-is-stateful').checked = config.is_stateful || false;
        
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

// --- LÓGICA DE SALVAMENTO (Com suporte a GIF) ---
async function saveButtonConfig() {
    const saveBtn = document.getElementById('save-button');
    saveBtn.disabled = true;
    saveBtn.textContent = "Salvando...";

    try {
        let finalIconValue = "";
        const activeTab = document.querySelector('.tab-button.active').dataset.tab;

        if (activeTab === 'link') {
            finalIconValue = document.getElementById('button-image-link').value;
        } else if (activeTab === 'icon') {
            finalIconValue = document.getElementById('button-icon').value;
        } else if (activeTab === 'upload') {
            
            // Caso GIF: Envia o arquivo original sem processar
            if (originalFile && originalFile.type === 'image/gif') {
                const formData = new FormData();
                formData.append('croppedImage', originalFile); // Backend aceita 'croppedImage' como nome do campo
                
                const response = await fetchApi('/api/upload_image', {
                    method: 'POST',
                    body: formData
                });
                finalIconValue = response.url;
            } 
            // Caso Outros (PNG/JPG): Usa o canvas do Cropper
            else if (cropper) {
                const canvas = cropper.getCroppedCanvas({ width: 128, height: 128 });
                if (canvas) {
                    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
                    const formData = new FormData();
                    formData.append('croppedImage', blob, 'cropped.png');

                    const response = await fetchApi('/api/upload_image', {
                        method: 'POST',
                        body: formData
                    });
                    finalIconValue = response.url;
                }
            }
        }

        const config = {
            label: document.getElementById('button-label').value,
            is_stateful: document.getElementById('button-is-stateful').checked,
            actions_on: readActionsFromList('action-list-on'),
            actions_off: readActionsFromList('action-list-off'),
            icon: finalIconValue
        };

        await fetchApi('/api/save_button', {
            method: 'POST',
            body: JSON.stringify({
                slot_id: currentSlotId,
                deck_id: store.get('currentDeckId'),
                config
            })
        });
        
        modal.hide();
    } catch(e) { 
        alert("Erro ao salvar: " + e.message); 
        console.error(e);
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Salvar";
    }
}

function handleImageUpload(e) {
    const file = e.target.files[0];
    if(!file) return;

    originalFile = file; // Guarda referência para usar no save se for GIF

    const reader = new FileReader();
    reader.onload = (evt) => {
        const img = document.getElementById('image-to-crop');
        img.src = evt.target.result;
        const container = document.getElementById('cropper-container');
        
        if(cropper) cropper.destroy();

        if (file.type === 'image/gif') {
            // Se for GIF, mostra apenas o preview sem inicializar o Cropper
            container.style.display = 'block';
            // Adiciona aviso visual que GIF não será recortado
            if (!document.getElementById('gif-warning')) {
                const warning = document.createElement('p');
                warning.id = 'gif-warning';
                warning.className = 'text-warning small';
                warning.textContent = 'GIFs animados não podem ser recortados e serão salvos como estão.';
                container.insertBefore(warning, img);
            }
        } else {
            // Se for imagem estática, inicializa Cropper
            const warning = document.getElementById('gif-warning');
            if(warning) warning.remove();
            
            container.style.display = 'block';
            cropper = new Cropper(img, { aspectRatio: 1, viewMode: 1 });
        }
    };
    reader.readAsDataURL(file);
}

// ... Funções auxiliares (mantidas iguais) ...
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
    if (type === 'obs_scene' || type === 'obs_source') {
        const sceneSelect = container.querySelector('.param-scene-name') || container.querySelector('.param-source-scene');
        const sceneList = store.get('obsScenes') || [];
        populateSelect(sceneSelect, sceneList.map(s => ({ value: s.name, label: s.name })), params?.scene_name);

        if (type === 'obs_source') {
            const sourceSelect = container.querySelector('.param-source-name');
            const updateSources = (sceneName) => {
                const sceneData = sceneList.find(s => s.name === sceneName);
                const sources = sceneData ? sceneData.sources : [];
                const valToSelect = (sceneName === params?.scene_name) ? params?.source_name : '';
                populateSelect(sourceSelect, sources.map(s => ({ value: s.name, label: s.name })), valToSelect);
            };
            sceneSelect.onchange = () => updateSources(sceneSelect.value);
            updateSources(params?.scene_name);
        }
    }
    if (type === 'obs_set_mute_on' || type === 'obs_set_mute_off') {
        const audioSelect = container.querySelector('.param-audio-input-name');
        const audioList = store.get('obsAudioSources') || [];
        populateSelect(audioSelect, audioList.map(a => ({ value: a.name, label: a.name })), params?.input_name);
    }
    if (type === 'vts_hotkey') {
        const select = container.querySelector('.param-vts-hotkey-id');
        const vtsList = store.get('vtsHotkeys') || [];
        populateSelect(select, vtsList.map(h => ({ value: h.hotkeyID, label: `${h.name} (${h.type})` })), params?.hotkey_id);
    }
    if (params?.file_name) { const inp = container.querySelector('.param-file-name'); if (inp) inp.value = params.file_name; }
    if (params?.keys_str) { const inp = container.querySelector('.param-keys-str'); if (inp) inp.value = params.keys_str; }
    if (params?.deck_id) { const inp = container.querySelector('.param-deck-id'); if (inp) inp.value = params.deck_id; }
}

function populateSelect(selectElement, items, selectedValue) {
    if (!selectElement) return;
    selectElement.innerHTML = '<option value="">-- Selecione --</option>';
    items.forEach(item => {
        const opt = new Option(item.label, item.value);
        selectElement.add(opt);
    });
    if (selectedValue) {
        const exists = Array.from(selectElement.options).some(opt => opt.value === selectedValue);
        if (!exists) {
            const label = `[Salvo] ${selectedValue}`; 
            const opt = new Option(label, selectedValue);
            opt.style.color = 'orange'; 
            selectElement.add(opt);
        }
        selectElement.value = selectedValue;
    }
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