// 1. Defina as variáveis globais
let socketInstance = null;
let obsSceneData = []; 
let obsAudioSources = [];
let vtsHotkeys = []; 
let cropper = null; 
let buttonStates = {}; 

let isObsConnected = false;
let isVtsConnected = false;

// Variáveis para Pastas (Decks)
let currentDeckId = "root";    // Rastreia o deck visível
let fullDeckConfig = {};       // Armazena todo o JSON de configuração

// 3. Mapa de tradução de event.code
const codeToKeyName = {
    "ControlLeft": "left ctrl", "ControlRight": "right ctrl",
    "ShiftLeft": "left shift", "ShiftRight": "right shift",
    "AltLeft": "left alt", "AltRight": "right alt",
    "MetaLeft": "left windows", "MetaRight": "right windows",
    "Numpad0": "num 0", "Numpad1": "num 1", "Numpad2": "num 2",
    "Numpad3": "num 3", "Numpad4": "num 4", "Numpad5": "num 5",
    "Numpad6": "num 6", "Numpad7": "num 7", "Numpad8": "num 8",
    "Numpad9": "num 9",
    "NumpadAdd": "num +", "NumpadSubtract": "num -",
    "NumpadMultiply": "num *", "NumpadDivide": "num /",
    "NumpadDecimal": "num .", "NumpadEnter": "num enter",
    "Digit1": "1", "Digit2": "2", "Digit3": "3", "Digit4": "4", "Digit5": "5",
    "Digit6": "6", "Digit7": "7", "Digit8": "8", "Digit9": "9", "Digit0": "0",
    "KeyA": "a", "KeyB": "b", "KeyC": "c", "KeyD": "d", "KeyE": "e", "KeyF": "f",
    "KeyG": "g", "KeyH": "h", "KeyI": "i", "KeyJ": "j", "KeyK": "k", "KeyL": "l",
    "KeyM": "m", "KeyN": "n", "KeyO": "o", "KeyP": "p", "KeyQ": "q", "KeyR": "r",
    "KeyS": "s", "KeyT": "t", "KeyU": "u", "KeyV": "v", "KeyW": "w", "KeyX": "x",
    "KeyY": "y", "KeyZ": "z",
    "F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4", "F5": "f5", "F6": "f6",
    "F7": "f7", "F8": "f8", "F9": "f9", "F10": "f10", "F11": "f11", "F12": "f12",
    "F13": "f13", "F14": "f14", "F15": "f15", "F16": "f16", "F17": "f17", "F18": "f18",
    "F19": "f19", "F20": "f20", "F21": "f21", "F22": "f22", "F23": "f23", "F24": "f24",
    "Space": "space", "Enter": "enter", "Escape": "esc", "Tab": "tab",
    "Backspace": "backspace", "ArrowUp": "up", "ArrowDown": "down",
    "ArrowLeft": "left", "ArrowRight": "right",
    "PageUp": "page up", "PageDown": "page down", "Home": "home", "End": "end",
    "Insert": "insert", "Delete": "delete",
    "Minus": "-", "Equal": "=", "BracketLeft": "[", "BracketRight": "]",
    "Backslash": "\\", "Semicolon": ";", "Quote": "'", "Comma": ",",
    "Period": ".", "Slash": "/", "Backquote": "`"
};


// 4. Lógica Principal do DOM
document.addEventListener('DOMContentLoaded', () => {

    // --- Variáveis Globais do DOM ---
    let selectedGameId = null;
    let uptimeInterval = null;
    let isEditMode = false;
    let currentEditingSlot = null;
    let isRecordingHotkey = false;
    let recordedKeys = new Set();
    let activeHotkeyRecorder = null;
    const TOTAL_DECK_SLOTS = 16; 

    // --- Seletores de Elementos ---
    const elements = {
        titleInput: document.getElementById('title'),
        categoryLabel: document.getElementById('current-category'),
        gameSearchInput: document.getElementById('game-search'),
        gameSearchResults: document.getElementById('game-search-results'),
        updateButton: document.getElementById('update-button'),
        updateStatus: document.getElementById('update-status'),
        statusBox: document.getElementById('status-box'),
        viewersBox: document.getElementById('viewers-box')?.querySelector('p'),
        uptimeBox: document.getElementById('uptime-box')?.querySelector('p'),
        obsStatusMessage: document.getElementById('obs-status-message'),
        obsStatusMessageConfig: document.getElementById('obs-status-message-config'),
        activityFeedBox: document.getElementById('activity-feed-box'),
        deckGrid: document.getElementById('streamdeck-grid'),
        editDeckButtons: document.querySelectorAll('#edit-deck-button-main, #edit-deck-button-config'),
        showLabelsToggle: document.getElementById('show-labels-toggle'),
        modal: document.getElementById('edit-modal'),
        modalTitle: document.getElementById('modal-title'),
        saveButton: document.getElementById('save-button'),
        deleteButton: document.getElementById('delete-button'),
        editForm: document.getElementById('edit-button-form'),
        slotIdInput: document.getElementById('slot-id-input'),
        buttonLabel: document.getElementById('button-label'),
        buttonActionType: document.getElementById('button-action-type'),
        buttonIsStateful: document.getElementById('button-is-stateful'),
        imageSourceTabs: document.querySelectorAll('.tab-button'),
        tabContents: document.querySelectorAll('.tab-content'),
        buttonIconInput: document.getElementById('button-icon'),
        buttonImageLinkInput: document.getElementById('button-image-link'),
        buttonImageUploadInput: document.getElementById('button-image-upload'),
        cropperContainer: document.getElementById('cropper-container'),
        imageToCrop: document.getElementById('image-to-crop'),
        actionOnList: document.getElementById('action-list-on'),
        actionOffList: document.getElementById('action-list-off'),
        actionOffContainer: document.getElementById('action-off-container'), 
        addActionButtonOn: document.querySelector('.add-action-button[data-action-list="on"]'),
        addActionButtonOff: document.querySelector('.add-action-button[data-action-list="off"]'),
        actionTemplate: document.getElementById('action-template'),
    };

    const editModal = new bootstrap.Modal(elements.modal);
    
    // --- INICIALIZA O SORTABLE (Drag-and-Drop) ---
    if (elements.deckGrid) {
        new Sortable(elements.deckGrid, {
            animation: 150,
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            onStart: () => {
                if (!isEditMode) return false; 
            },
            onEnd: async (evt) => {
                if (evt.oldIndex === evt.newIndex) return;
                
                const buttonsInOrder = elements.deckGrid.querySelectorAll('.deck-button');
                const newButtonsLayout = {};
                
                buttonsInOrder.forEach((buttonEl, index) => {
                    const currentSlotId = buttonEl.dataset.slotId;
                    const newSlotId = `slot-${index}`;
                    
                    const currentDeck = fullDeckConfig.decks[currentDeckId] || {};
                    const config = currentDeck[currentSlotId];
                    
                    if (config) {
                        newButtonsLayout[newSlotId] = config;
                    }
                });

                if (!fullDeckConfig.decks) fullDeckConfig.decks = {};
                fullDeckConfig.decks[currentDeckId] = newButtonsLayout;
                
                renderDeck(); 

                try {
                    await fetchApi('/api/save_deck_layout', {
                        method: 'POST',
                        body: JSON.stringify({
                            deck_id: currentDeckId,
                            buttons: newButtonsLayout
                        })
                    });
                    console.log("Novo layout salvo no servidor.");
                } catch (error) {
                    console.error("Falha ao salvar novo layout:", error);
                }
            }
        });
    }
    
    const socket = io(window.location.origin + '/dashboard');
    socketInstance = socket; 

    function friendlyKeyName(key) {
        if (!key) return "";
        return key.split(' ').map(s => s.charAt(0).toUpperCase() + s.substring(1)).join(' ');
    }

    // 2. Defina as funções de Ação
    function runButtonAction(config, buttonElement) {
        if (!config || !socketInstance) return;
        
        let actionsToRun = [];
        const slotId = buttonElement.dataset.slotId;

        if (config.is_stateful) {
            const currentState = buttonStates[slotId] || false; 
            if (!currentState) {
                actionsToRun = config.actions_on || [];
                buttonStates[slotId] = true;
            } else {
                actionsToRun = config.actions_off || [];
                buttonStates[slotId] = false;
            }
            buttonElement.classList.toggle('is-active', buttonStates[slotId]);
        } else {
            actionsToRun = config.actions_on || [];
        }
        
        actionsToRun.forEach((action, index) => {
            const type = action.type;
            const params = action.params;
            console.log(`Ação ${index + 1}: ${type}`, params);

            if (type === 'obs_scene') {
                socketInstance.emit('set_obs_scene', { scene_name: params.scene_name });
            }
            else if (type === 'obs_source') {
                socketInstance.emit('toggle_source_visibility', { 
                    scene_name: params.scene_name, 
                    source_name: params.source_name 
                });
            }
            else if (type === 'sound') {
                socketInstance.emit('play_sound', { file: params.file_name });
            }
            else if (type === 'hotkey') {
                socketInstance.emit('run_hotkey', { keys_str: params.keys_str });
            }
            else if (type === 'obs_stream_toggle') {
                socketInstance.emit('obs_stream_toggle');
            }
            else if (type === 'obs_record_toggle') {
                socketInstance.emit('obs_record_toggle');
            }
            else if (type === 'open_deck') {
                const deckId = params.deck_id || "root";
                currentDeckId = deckId;
                buttonStates = {};      
                renderDeck();           
            }
            else if (type === 'vts_hotkey') {
                socketInstance.emit('vts_trigger_hotkey', { hotkey_id: params.hotkey_id });
            }
            else if (type === 'obs_set_mute_on') {
                socketInstance.emit('obs_set_mute', { 
                    input_name: params.input_name,
                    mute_state: true 
                });
            }
            else if (type === 'obs_set_mute_off') {
                socketInstance.emit('obs_set_mute', { 
                    input_name: params.input_name,
                    mute_state: false
                });
            }
        });
    }

    // --- Wrapper de Fetch ---
    async function fetchApi(url, options) {
        if (!(options?.body instanceof FormData)) {
            options = options || {};
            options.headers = options.headers || {};
            options.headers['Content-Type'] = 'application/json';
        }
        const response = await fetch(url, options);
        if (response.status === 401) {
            alert("Sua sessão expirou. A página será recarregada para você fazer login.");
            window.location.reload(); 
            throw new Error("Sessão expirada");
        }
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Falha na requisição: ${response.statusText} - ${errorText}`);
        }
        return response.json();
    }

    // ---- Lógica do Painel de Controle da Twitch ----
    
    async function loadChannelInfo() {
        try {
            const data = await fetchApi('/api/channel_info');
            if(elements.titleInput) elements.titleInput.value = data.title;
            if(elements.categoryLabel) elements.categoryLabel.textContent = data.category;
            selectedGameId = data.category_id;
        } catch (error) { 
            console.error("Erro ao carregar Channel Info:", error);
            if (elements.categoryLabel) elements.categoryLabel.textContent = "Erro."; 
        }
    }
    
    async function loadStreamStats() {
        try {
            const data = await fetchApi('/api/stream_stats');
            if (data.status === "online") {
                if(elements.statusBox) {
                    elements.statusBox.querySelector('p').textContent = "Online";
                    elements.statusBox.className = "stat-box online";
                }
                if(elements.viewersBox) elements.viewersBox.textContent = data.viewer_count;
                startUptimeTimer(data.started_at);
            } else {
                if(elements.statusBox) {
                    elements.statusBox.querySelector('p').textContent = "Offline";
                    elements.statusBox.className = "stat-box offline";
                }
                if(elements.viewersBox) elements.viewersBox.textContent = "0";
                stopUptimeTimer();
            }
        } catch (error) { 
            console.error("Erro ao carregar Stream Stats:", error);
            if(elements.statusBox) elements.statusBox.querySelector('p').textContent = "Erro";
        }
    }
    
    function startUptimeTimer(startTime) {
        stopUptimeTimer(); 
        const startDate = new Date(startTime);
        uptimeInterval = setInterval(() => {
            const now = new Date();
            const diff = now.getTime() - startDate.getTime();
            const hours = Math.floor(diff / 3600000);
            const minutes = Math.floor((diff % 3600000) / 60000);
            const seconds = Math.floor((diff % 60000) / 1000);
            if(elements.uptimeBox) elements.uptimeBox.textContent = 
                `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }, 1000);
    }
    
    function stopUptimeTimer() {
        if (uptimeInterval) clearInterval(uptimeInterval);
        uptimeInterval = null;
        if(elements.uptimeBox) elements.uptimeBox.textContent = "00:00:00";
    }

    elements.gameSearchInput?.addEventListener('keyup', async (e) => {
        const query = e.target.value;
        if (query.length < 3) {
            elements.gameSearchResults.innerHTML = ''; return;
        }
        const games = await fetchApi(`/api/search_games?query=${encodeURIComponent(query)}`);
        elements.gameSearchResults.innerHTML = '';
        games.slice(0, 5).forEach(game => {
            const div = document.createElement('div');
            div.textContent = game.name;
            div.onclick = () => {
                elements.gameSearchInput.value = game.name;
                selectedGameId = game.id;
                elements.gameSearchResults.innerHTML = '';
            };
            elements.gameSearchResults.appendChild(div);
        });
    });

    elements.updateButton?.addEventListener('click', async () => {
        const body = { title: elements.titleInput.value };
        if (selectedGameId) body.game_id = selectedGameId;
        elements.updateStatus.textContent = "Atualizando...";
        elements.updateStatus.style.display = "inline";
        try {
            await fetchApi('/api/update_channel', {
                method: 'POST',
                body: JSON.stringify(body)
            });
            elements.updateStatus.textContent = "Atualizado!";
            await loadChannelInfo();
        } catch (error) {
            console.error("Erro ao atualizar canal:", error);
            elements.updateStatus.textContent = "Erro.";
        }
        setTimeout(() => { elements.updateStatus.style.display = "none"; }, 3000);
    });
    
    // ---- Lógica do Feed de Atividades ----
    
    function addActivityToFeed(message, type) {
        if (!elements.activityFeedBox) return;
        const feedItem = document.createElement('div');
        feedItem.className = 'feed-item';
        const cssType = type.replace(/\./g, '-').replace(/_/g, '-');
        feedItem.classList.add(`type-${cssType}`);
        feedItem.textContent = message;
        elements.activityFeedBox.prepend(feedItem);
        if (elements.activityFeedBox.children.length > 50) {
            elements.activityFeedBox.removeChild(elements.activityFeedBox.lastChild);
        }
    }
    
    // ---- LÓGICA DE APARÊNCIA DO DECK ----
    
    function setShowLabels(show) {
        localStorage.setItem('foxydeck-show-labels', show ? 'true' : 'false');
        document.body.classList.toggle('labels-hidden', !show);
        if (elements.showLabelsToggle) {
            elements.showLabelsToggle.checked = show;
        }
    }

    // ---- LÓGICA DO STREAM DECK ----

    function toggleEditMode() {
        isEditMode = !isEditMode;
        document.body.classList.toggle('edit-mode', isEditMode);
        
        elements.editDeckButtons.forEach(button => {
            if (!button) return;
            button.classList.toggle('active', isEditMode);
            if(isEditMode) {
                button.innerHTML = '<i class="fa-solid fa-check"></i> Concluir Edição';
            } else {
                if (button.id === 'edit-deck-button-config') {
                    button.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Ativar Modo de Edição';
                } else {
                    button.innerHTML = '<i class="fa-solid fa-pen-to-square"></i>';
                }
            }
        });
        
        loadDeckConfig(); 
    }

    function renderDeck() {
        if (!elements.deckGrid) return; 
        elements.deckGrid.innerHTML = ''; 
        
        const buttons = fullDeckConfig.decks ? (fullDeckConfig.decks[currentDeckId] || {}) : {};
        
        for (let i = 0; i < TOTAL_DECK_SLOTS; i++) {
            const slotId = `slot-${i}`;
            const config = buttons[slotId];
            const button = document.createElement('div');
            
            button.dataset.slotId = slotId;

            if (config) {
                button.className = 'deck-button';
                let iconHtml = '';
                if (config.icon && (config.icon.startsWith('http') || config.icon.startsWith('/uploads'))) {
                    iconHtml = `<img src="${config.icon}">`;
                } else {
                    iconHtml = `<i class="${config.icon || 'fa-solid fa-question'}"></i>`;
                }
                
                button.innerHTML = `${iconHtml}<span>${config.label}</span>`;
                
                if (config.is_stateful && buttonStates[slotId]) {
                    button.classList.add('is-active');
                }

                let actionClass = 'obs'; 
                if (config.actions_on && config.actions_on.length > 0) {
                    const firstActionType = config.actions_on[0].type;
                    if (firstActionType === 'sound') actionClass = 'sound';
                    else if (firstActionType === 'hotkey') actionClass = 'hotkey';
                    else if (firstActionType.includes('stream') || firstActionType.includes('record')) actionClass = 'control';
                    else if (firstActionType.includes('vts')) actionClass = 'vts';
                    else if (firstActionType === 'open_deck') actionClass = 'hotkey'; 
                }

                button.classList.add(actionClass);
                
                button.onclick = (e) => {
                    if (isEditMode) {
                        openEditModal(slotId, config);
                    } else {
                        runButtonAction(config, e.currentTarget);
                    }
                };
            } else {
                button.className = 'deck-button empty';
                button.innerHTML = `<i class="fa-solid fa-plus"></i>`;
                button.onclick = () => { if (isEditMode) openEditModal(slotId, null); };
            }
            elements.deckGrid.appendChild(button);
        }
    }

    async function loadDeckConfig() {
        try {
            const data = await fetchApi('/api/deck_config');
            fullDeckConfig = data; 
            
            if (!currentDeckId || !fullDeckConfig.decks[currentDeckId]) {
                currentDeckId = fullDeckConfig.settings?.start_deck || "root";
            }
            
            const oldStates = { ...buttonStates }; 
            buttonStates = {}; 
            
            const currentButtons = fullDeckConfig.decks ? (fullDeckConfig.decks[currentDeckId] || {}) : {};
            for (const slotId in currentButtons) {
                if (currentButtons[slotId].is_stateful) {
                    buttonStates[slotId] = oldStates[slotId] || false; 
                }
            }
            renderDeck(); 
        } catch (error) {
            console.error("Erro ao carregar configuração do deck:", error);
        }
    }

    // ---- LÓGICA DO MODAL ----
    
    // [CORREÇÃO] Removida lógica que impedia duplicatas com o item salvo.
    // Agora adiciona TODOS os itens da lista ao vivo E o item salvo (se faltar).
    function populateSceneDropdowns(selectElement, selectedValue = '') {
        const scenes = obsSceneData.map(scene => scene.name);
        if (!selectElement) return; 
        
        selectElement.innerHTML = '<option value="">-- Selecione uma Cena --</option>';
        
        // Adiciona opção salva MANUALMENTE APENAS se não existir na lista
        if (selectedValue && !scenes.includes(selectedValue)) {
            const savedOption = new Option(`[Salvo] ${selectedValue}`, selectedValue);
            selectElement.appendChild(savedOption);
        }
        
        // Adiciona TODAS as cenas disponíveis
        scenes.forEach(sceneName => {
            const option = new Option(sceneName, sceneName);
            selectElement.appendChild(option);
        });

        if (selectedValue) {
            selectElement.value = selectedValue;
        }
    }

    function populateSourceDropdown(selectElement, sceneName, selectedValue = '') {
        const scene = obsSceneData.find(s => s.name === sceneName);
        if (!selectElement) return; 
        
        selectElement.innerHTML = ''; 
        const sources = scene ? scene.sources.map(s => s.name) : [];

        if (!sceneName || (!scene && !selectedValue)) {
            selectElement.innerHTML = '<option value="">-- Selecione uma cena primeiro --</option>';
            return;
        }

        selectElement.innerHTML = '<option value="">-- Selecione uma Fonte --</option>';
        
        if (selectedValue && !sources.includes(selectedValue)) {
            const savedOption = new Option(`[Salvo] ${selectedValue}`, selectedValue);
            selectElement.appendChild(savedOption);
        }

        sources.forEach(sourceName => {
            const option = new Option(sourceName, sourceName);
            selectElement.appendChild(option);
        });

        if (selectedValue) {
            selectElement.value = selectedValue;
        }
    }
    
    function populateVTSHotkeyDropdown(selectElement, selectedValue = '') {
        if (!selectElement) return; 
        selectElement.innerHTML = ''; 
        const hotkeyIDs = vtsHotkeys.map(h => h.hotkeyID);

        if (vtsHotkeys.length === 0 && !selectedValue) {
            selectElement.innerHTML = '<option value="">-- VTS não conectado ou sem hotkeys --</option>';
            return;
        }

        selectElement.innerHTML = '<option value="">-- Selecione uma Hotkey --</option>';
        
        if (selectedValue && !hotkeyIDs.includes(selectedValue)) {
             const savedHotkey = vtsHotkeys.find(h => h.hotkeyID === selectedValue);
             const displayName = savedHotkey ? savedHotkey.name : `[Salvo] ID: ${selectedValue}`;
             const savedOption = new Option(displayName, selectedValue);
             if (!savedHotkey) savedOption.textContent = `[Salvo] ID: ${selectedValue.substring(0, 8)}...`;
             selectElement.appendChild(savedOption);
        }

        vtsHotkeys.forEach(hotkey => {
            const option = new Option(`${hotkey.name} (Tipo: ${hotkey.type})`, hotkey.hotkeyID);
            selectElement.appendChild(option);
        });
        if (selectedValue) {
            selectElement.value = selectedValue;
        }
    }
    
    function populateAudioInputDropdown(selectElement, selectedValue = '') {
        const audioInputs = obsAudioSources.map(input => input.name);
        if (!selectElement) return; 
        
        selectElement.innerHTML = '<option value="">-- Selecione uma Fonte de Áudio --</option>';
        
        if (selectedValue && !audioInputs.includes(selectedValue)) {
             const savedOption = new Option(`[Salvo] ${selectedValue}`, selectedValue);
             selectElement.appendChild(savedOption);
        }

        audioInputs.forEach(inputName => {
            const option = new Option(inputName, inputName);
            selectElement.appendChild(option);
        });

        if (selectedValue) {
            selectElement.value = selectedValue;
        }
    }

    function populateHotkeySelector(selectElement) {
        if (!selectElement || selectElement.options.length > 1) return; 

        const modifiers = {};
        const functionKeys = {};
        const navigation = {};
        const numpad = {};
        const letters = {};
        const numbers = {};
        
        for (const [code, keyName] of Object.entries(codeToKeyName)) {
            if (keyName.includes("ctrl") || keyName.includes("shift") || keyName.includes("alt") || keyName.includes("windows")) {
                modifiers[keyName] = friendlyKeyName(keyName);
            } else if (keyName.match(/^f[0-9]+$/)) {
                functionKeys[keyName] = friendlyKeyName(keyName);
            } else if (keyName.startsWith("num ")) {
                numpad[keyName] = friendlyKeyName(keyName);
            } else if (keyName.length === 1 && keyName >= 'a' && keyName <= 'z') {
                letters[keyName] = keyName.toUpperCase();
            } else if (keyName.length === 1 && keyName >= '0' && keyName <= '9') {
                numbers[keyName] = keyName;
            } else {
                navigation[keyName] = friendlyKeyName(keyName);
            }
        }
        
        const createOptgroup = (label, keys) => {
            const group = document.createElement('optgroup');
            group.label = label;
            Object.entries(keys).sort((a,b) => a[1].localeCompare(b[1])).forEach(([value, text]) => {
                group.appendChild(new Option(text, value));
            });
            return group;
        };

        selectElement.appendChild(createOptgroup("Modificadores", modifiers));
        selectElement.appendChild(createOptgroup("Teclas de Função (F1-F24)", functionKeys));
        selectElement.appendChild(createOptgroup("Teclado Numérico", numpad));
        selectElement.appendChild(createOptgroup("Navegação e Especiais", navigation));
        selectElement.appendChild(createOptgroup("Letras", letters));
        selectElement.appendChild(createOptgroup("Números (Topo)", numbers));
    }

    function updateHotkeyDisplay(displayElement, hiddenInputElement, keysSet) {
        if (!displayElement || !hiddenInputElement) return;

        displayElement.innerHTML = '';
        if (keysSet.size === 0) {
            displayElement.innerHTML = '<span class="text-secondary">Nenhuma tecla selecionada...</span>';
        }
        
        let hotkeyString = "";
        let first = true;
        
        keysSet.forEach(key => {
            if (!first) hotkeyString += "+";
            hotkeyString += key;
            first = false;
            
            const pill = document.createElement('div');
            pill.className = 'hotkey-pill';
            const friendlyName = friendlyKeyName(key);
            pill.innerHTML = `<span>${friendlyName}</span> <span class="remove-key" data-key="${key}">&times;</span>`;
            displayElement.appendChild(pill);
        });
        
        hiddenInputElement.value = hotkeyString;

        displayElement.querySelectorAll('.remove-key').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation(); 
                const keyToRemove = e.target.dataset.key;
                keysSet.delete(keyToRemove);
                updateHotkeyDisplay(displayElement, hiddenInputElement, keysSet); 
            };
        });
    }

    
    function populateActionTypeDropdown(selectElement, selectedAction = "") {
        if (!selectElement) return;
        selectElement.innerHTML = '<option value="">-- Selecione uma Ação --</option>';

        {
            const group = document.createElement('optgroup');
            group.label = "OBS - Controles";
            group.appendChild(new Option("Alternar Stream", "obs_stream_toggle"));
            group.appendChild(new Option("Alternar Gravação", "obs_record_toggle"));
            group.appendChild(new Option("OBS: Mutar Áudio", "obs_set_mute_on"));
            group.appendChild(new Option("OBS: Desmutar Áudio", "obs_set_mute_off"));
            selectElement.appendChild(group);
        }
        
        {
            const group = document.createElement('optgroup');
            group.label = "OBS - Cenas/Fontes";
            group.appendChild(new Option("Mudar Cena", "obs_scene"));
            group.appendChild(new Option("Alternar Fonte", "obs_source"));
            selectElement.appendChild(group);
        }

        {
            const group = document.createElement('optgroup');
            group.label = "VTube Studio";
            group.appendChild(new Option("Disparar Hotkey", "vts_hotkey"));
            selectElement.appendChild(group);
        }
        
        const group = document.createElement('optgroup');
        group.label = "Sistema";
        group.appendChild(new Option("Tocar Som (Soundboard)", "sound"));
        group.appendChild(new Option("Acionar Hotkey (PC)", "hotkey"));
        group.appendChild(new Option("Abrir Pasta (Deck)", "open_deck")); 
        selectElement.appendChild(group);
        
        selectElement.value = selectedAction;
    }


    function createActionCard(actionListElement, config = null) {
        const template = elements.actionTemplate.content.cloneNode(true);
        const card = template.querySelector('.action-card');
        const title = card.querySelector('.action-title');
        const typeSelect = card.querySelector('.action-type-select');
        const paramsContainer = card.querySelector('.action-params-template');

        let currentCardKeys = new Set(); 
        
        card.querySelector('.remove-action-button').onclick = () => card.remove();
        
        typeSelect.onchange = () => {
            paramsContainer.querySelectorAll('.action-params').forEach(p => p.style.display = 'none');
            const selectedParams = paramsContainer.querySelector(`.action-params[data-param-for="${typeSelect.value}"]`);
            if (selectedParams) {
                selectedParams.style.display = 'block';
            }
            title.textContent = typeSelect.options[typeSelect.selectedIndex]?.text || "Nova Ação";

            if (typeSelect.value === 'open_deck') {
                const deckIdInput = selectedParams.querySelector('.param-deck-id');
                if (!deckIdInput.value || deckIdInput.value === 'root') {
                    const newDeckId = 'deck_' + Date.now();
                    deckIdInput.value = newDeckId;
                }
            }
        };
        
        populateActionTypeDropdown(typeSelect, config?.type || "");
        
        // Inicialização Padrão (Vazio)
        populateSceneDropdowns(paramsContainer.querySelector('.param-scene-name'));
        const sourceSceneSelect = paramsContainer.querySelector('.param-source-scene');
        const sourceNameSelect = paramsContainer.querySelector('.param-source-name');
        populateSceneDropdowns(sourceSceneSelect);
        sourceSceneSelect.onchange = () => populateSourceDropdown(sourceNameSelect, sourceSceneSelect.value);
        
        populateVTSHotkeyDropdown(paramsContainer.querySelector('.param-vts-hotkey-id'));
        populateAudioInputDropdown(paramsContainer.querySelector('[data-param-for="obs_set_mute_on"] .param-audio-input-name'));
        populateAudioInputDropdown(paramsContainer.querySelector('[data-param-for="obs_set_mute_off"] .param-audio-input-name'));
        
        const hotkeyParams = paramsContainer.querySelector('.action-params[data-param-for="hotkey"]');
        const addKeySelect = hotkeyParams.querySelector('.add-hotkey-select');
        const hotkeyDisplay = hotkeyParams.querySelector('.hotkey-display-area');
        const clearHotkeyButton = hotkeyParams.querySelector('.clear-hotkey-button');
        const hiddenInput = hotkeyParams.querySelector('.param-keys-str');

        populateHotkeySelector(addKeySelect);
        addKeySelect.onchange = () => {
            const newKey = addKeySelect.value;
            if (newKey && !currentCardKeys.has(newKey)) {
                currentCardKeys.add(newKey);
                updateHotkeyDisplay(hotkeyDisplay, hiddenInput, currentCardKeys);
            }
            addKeySelect.value = ""; 
        };
        clearHotkeyButton.onclick = () => {
            currentCardKeys.clear();
            updateHotkeyDisplay(hotkeyDisplay, hiddenInput, currentCardKeys);
        };

        if (config) {
            typeSelect.value = config.type; 
            
            setTimeout(() => { typeSelect.dispatchEvent(new Event('change')); }, 0);
            
            const params = config.params || {};
            
            if (config.type === 'obs_scene') {
                populateSceneDropdowns(paramsContainer.querySelector('.param-scene-name'), params.scene_name);
            } 
            else if (config.type === 'obs_source') {
                populateSceneDropdowns(paramsContainer.querySelector('.param-source-scene'), params.scene_name);
                populateSourceDropdown(sourceNameSelect, params.scene_name, params.source_name || '');
            } 
            else if (config.type === 'sound') {
                paramsContainer.querySelector('.param-file-name').value = params.file_name || '';
            } 
            else if (config.type === 'hotkey') {
                const keysStr = params.keys_str || '';
                hiddenInput.value = keysStr;
                if (keysStr) keysStr.split('+').forEach(key => currentCardKeys.add(key));
                updateHotkeyDisplay(hotkeyDisplay, hiddenInput, currentCardKeys);
            } 
            else if (config.type === 'open_deck') {
                paramsContainer.querySelector('.param-deck-id').value = params.deck_id || 'root';
            }
            else if (config.type === 'vts_hotkey') {
                populateVTSHotkeyDropdown(paramsContainer.querySelector('.param-vts-hotkey-id'), params.hotkey_id);
            } 
            else if (config.type === 'obs_set_mute_on') {
                populateAudioInputDropdown(paramsContainer.querySelector('[data-param-for="obs_set_mute_on"] .param-audio-input-name'), params.input_name);
            }
            else if (config.type === 'obs_set_mute_off') {
                populateAudioInputDropdown(paramsContainer.querySelector('[data-param-for="obs_set_mute_off"] .param-audio-input-name'), params.input_name);
            }
        }
        
        actionListElement.appendChild(card);
    }

    function openEditModal(slotId, config) {
        currentEditingSlot = slotId;
        elements.slotIdInput.value = slotId;
        elements.editForm.reset();
        
        if (cropper) cropper.destroy();
        cropper = null;
        elements.cropperContainer.style.display = 'none';
        document.querySelector('.tab-button[data-tab="icon"]').click();
        
        elements.actionOnList.innerHTML = '';
        elements.actionOffList.innerHTML = '';
        elements.actionOffContainer.style.display = 'none'; 

        elements.buttonIsStateful.checked = false;

        if (config) {
            elements.modalTitle.textContent = "Editar Botão";
            elements.buttonLabel.value = config.label || '';
            elements.buttonIsStateful.checked = config.is_stateful || false;
            elements.deleteButton.style.display = 'block';
            if (config.icon && (config.icon.startsWith('http') || config.icon.startsWith('/uploads'))) {
                document.querySelector('.tab-button[data-tab="link"]').click();
                elements.buttonImageLinkInput.value = config.icon;
            } else {
                document.querySelector('.tab-button[data-tab="icon"]').click();
                elements.buttonIconInput.value = config.icon || '';
            }

            if (config.is_stateful) {
                elements.actionOffContainer.style.display = 'block'; 
                (config.actions_on || []).forEach(action => createActionCard(elements.actionOnList, action));
                (config.actions_off || []).forEach(action => createActionCard(elements.actionOffList, action));
            } else {
                (config.actions_on || []).forEach(action => createActionCard(elements.actionOnList, action));
            }
        } else {
            elements.modalTitle.textContent = "Adicionar Novo Botão";
            elements.deleteButton.style.display = 'none';
            createActionCard(elements.actionOnList, null);
        }
        
        elements.actionOffContainer.style.display = elements.buttonIsStateful.checked ? 'block' : 'none';
        
        editModal.show();
    }

    function closeEditModal() {
        editModal.hide(); 
    }

    elements.modal.addEventListener('hidden.bs.modal', () => {
        if (cropper) cropper.destroy();
        cropper = null;
        elements.cropperContainer.style.display = 'none';
        elements.buttonImageUploadInput.value = '';
        currentEditingSlot = null;
    });
    
    async function saveButton() {
        elements.saveButton.textContent = "Salvando...";
        elements.saveButton.disabled = true;
        let imageUrl = null;
        const activeTab = document.querySelector('.tab-button.active').dataset.tab;
        if (activeTab === 'link') {
            imageUrl = elements.buttonImageLinkInput.value;
        } else if (activeTab === 'icon') {
            imageUrl = elements.buttonIconInput.value;
        } else if (activeTab === 'upload' && cropper) {
            const canvas = cropper.getCroppedCanvas({ width: 128, height: 128 });
            const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
            const formData = new FormData();
            formData.append('croppedImage', blob, 'cropped.png');
            try {
                const response = await fetchApi('/api/upload_image', {
                    method: 'POST',
                    body: formData,
                });
                imageUrl = response.url;
            } catch (error) {
                console.error("Erro no upload:", error);
                alert("Falha no upload da imagem.");
                elements.saveButton.textContent = "Salvar";
                elements.saveButton.disabled = false;
                return; 
            }
        }
        
        const config = {
            label: elements.buttonLabel.value,
            icon: imageUrl,
            is_stateful: elements.buttonIsStateful.checked,
            actions_on: [],
            actions_off: []
        };
        
        const readActionCard = (card) => {
            const type = card.querySelector('.action-type-select').value;
            if (!type) return null;
            
            const action = { type: type, params: {} };
            const paramsDiv = card.querySelector(`.action-params[data-param-for="${type}"]`);
            
            if (type === 'obs_scene') {
                action.params.scene_name = paramsDiv.querySelector('.param-scene-name').value;
            } else if (type === 'obs_source') {
                action.params.scene_name = paramsDiv.querySelector('.param-source-scene').value;
                action.params.source_name = paramsDiv.querySelector('.param-source-name').value;
            } else if (type === 'sound') {
                action.params.file_name = paramsDiv.querySelector('.param-file-name').value;
            } else if (type === 'hotkey') {
                action.params.keys_str = paramsDiv.querySelector('.param-keys-str').value;
            } 
            else if (type === 'open_deck') {
                action.params.deck_id = paramsDiv.querySelector('.param-deck-id').value;
            }
            else if (type === 'vts_hotkey') {
                action.params.hotkey_id = paramsDiv.querySelector('.param-vts-hotkey-id').value;
            } else if (type === 'obs_set_mute_on' || type === 'obs_set_mute_off') {
                action.params.input_name = paramsDiv.querySelector('.param-audio-input-name').value;
            }
            return action;
        };

        elements.actionOnList.querySelectorAll('.action-card').forEach(card => {
            const action = readActionCard(card);
            if (action) config.actions_on.push(action);
        });
        if (config.is_stateful) {
            elements.actionOffList.querySelectorAll('.action-card').forEach(card => {
                const action = readActionCard(card);
                if (action) config.actions_off.push(action);
            });
        }
        
        try {
            await fetchApi('/api/save_button', {
                method: 'POST',
                body: JSON.stringify({
                    slot_id: currentEditingSlot,
                    deck_id: currentDeckId, 
                    config: config
                })
            });
            closeEditModal();
        } catch (error) {
            console.error("Erro ao salvar botão:", error);
            alert("Erro ao salvar. Verifique o console.");
        }
        elements.saveButton.textContent = "Salvar";
        elements.saveButton.disabled = false;
    }

    async function deleteButton() {
        if (!confirm("Tem certeza que deseja deletar este botão?")) return;
        try {
            await fetchApi('/api/delete_button', {
                method: 'POST',
                body: JSON.stringify({ 
                    slot_id: currentEditingSlot,
                    deck_id: currentDeckId 
                })
            });
            closeEditModal();
        } catch (error) {
            console.error("Erro ao deletar botão:", error);
            alert("Erro ao deletar. Verifique o console.");
        }
    }

    elements.editDeckButtons.forEach(button => {
        button?.addEventListener('click', toggleEditMode);
    });
    
    elements.showLabelsToggle?.addEventListener('change', () => {
        setShowLabels(elements.showLabelsToggle.checked);
    });
    
    elements.editForm?.addEventListener('submit', (e) => { e.preventDefault(); saveButton(); });
    elements.deleteButton?.addEventListener('click', deleteButton);
    
    elements.imageSourceTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            elements.imageSourceTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            elements.tabContents.forEach(content => content.classList.remove('active'));
            const activeTabContent = document.getElementById(tab.dataset.tab + '-tab');
            if (activeTabContent) activeTabContent.classList.add('active');
            if (tab.dataset.tab !== 'upload' && cropper) {
                cropper.destroy();
                cropper = null;
                elements.cropperContainer.style.display = 'none';
            }
        });
    });
    
    elements.buttonImageUploadInput?.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files && files.length > 0) {
            const reader = new FileReader();
            reader.onload = (event) => {
                elements.imageToCrop.src = event.target.result;
                elements.cropperContainer.style.display = 'block';
                if (cropper) cropper.destroy();
                cropper = new Cropper(elements.imageToCrop, {
                    aspectRatio: 1,
                    viewMode: 1,
                    background: false,
                });
            };
            reader.readAsDataURL(files[0]);
        }
    });
    
    elements.buttonIsStateful?.addEventListener('change', () => {
        const showOffList = elements.buttonIsStateful.checked;
        elements.actionOffContainer.style.display = showOffList ? 'block' : 'none';
    });

    elements.addActionButtonOn?.addEventListener('click', () => createActionCard(elements.actionOnList, null));
    elements.addActionButtonOff?.addEventListener('click', () => createActionCard(elements.actionOffList, null));


    // ---- Lógica de Eventos do Socket ----

    socket.on('connect', () => {
        console.log("Conectado ao servidor do painel.");
        loadDeckConfig(); 
        socket.emit("get_vts_data");
        
        loadChannelInfo();
        loadStreamStats();
        setInterval(loadStreamStats, 60000); 
    });
    
    socket.on('deck_updated', (configData) => {
        console.log("Configuração do deck atualizada pelo servidor.");
        fullDeckConfig = configData; 
        
        if (!fullDeckConfig.decks || !fullDeckConfig.decks[currentDeckId]) {
            currentDeckId = "root";
        }

        const oldStates = { ...buttonStates };
        buttonStates = {};
        
        const currentButtons = fullDeckConfig.decks ? (fullDeckConfig.decks[currentDeckId] || {}) : {};
        for (const slotId in currentButtons) {
            if (currentButtons[slotId].is_stateful) {
                buttonStates[slotId] = oldStates[slotId] || false; 
            }
        }
        renderDeck(); 
    });
    
    socket.on('eventsub_notification', (data) => { addActivityToFeed(data.message, data.type); });
    
    socket.on('obs_status', (data) => {
        isObsConnected = data.connected; 
        const obsMessages = [elements.obsStatusMessage, elements.obsStatusMessageConfig];
        obsMessages.forEach(el => {
            if (el) {
                el.textContent = `OBS Status: ${data.message}`;
                el.classList.remove('alert-danger', 'alert-warning', 'alert-success', 'alert-secondary');
                el.classList.add(data.connected ? 'alert-success' : 'alert-danger');
            }
        });
        
        if (data.connected && (data.message === "Conectado ao OBS" || data.message.startsWith("Cena:"))) {
            console.log("OBS conectado/atualizado. Solicitando detalhes das cenas...");
            socket.emit("get_obs_scene_details");
        }
    });
    socket.on('obs_scene_details_data', (data) => {
        console.log("Recebido detalhes de Cenas/Fontes/Áudio do OBS:", data);
        obsSceneData = data.scenes || [];
        obsAudioSources = data.audio_inputs || [];
    });
    socket.on('obs_error', (data) => {
        isObsConnected = false; 
        const obsMessages = [elements.obsStatusMessage, elements.obsStatusMessageConfig];
        obsMessages.forEach(el => {
            if(el) {
                el.textContent = `Erro no OBS: ${data.message}`;
                el.classList.remove('alert-success', 'alert-warning', 'alert-secondary');
                el.classList.add('alert-danger');
            }
        });
    });
    
    socket.on('vts_status', (data) => {
        isVtsConnected = data.connected; 
        [elements.obsStatusMessage, elements.obsStatusMessageConfig].forEach((obsEl, index) => {
            if(obsEl) {
                let vtsMsg = obsEl.parentNode.querySelector('.vts-status-msg');
                if (!vtsMsg) {
                    vtsMsg = document.createElement('div');
                    vtsMsg.id = 'vts-status-msg-' + (index === 0 ? 'main' : 'config');
                    vtsMsg.className = 'alert mt-2 vts-status-msg'; 
                    obsEl.parentNode.appendChild(vtsMsg);
                }
                vtsMsg.textContent = `VTS Status: ${data.message}`;
                vtsMsg.classList.remove('alert-danger', 'alert-warning', 'alert-success', 'alert-secondary');
                vtsMsg.classList.add(data.connected ? 'alert-success' : 'alert-warning');
            }
        });
    });
    
    socket.on('vts_data_list', (data) => {
        console.log("Recebido lista de Hotkeys do VTS:", data);
        vtsHotkeys = data.hotkeys || [];
    });

    // ---- Inicialização ----
    const showLabels = localStorage.getItem('foxydeck-show-labels') !== 'false'; 
    setShowLabels(showLabels);
});