import { socket } from './socket.js';
import { store } from './store.js';

export function executeAction(config, buttonElement) {
    if (!config) return;

    const slotId = buttonElement.dataset.slotId;
    let actionsToRun = config.actions_on || [];

    // Lógica de Estado (Toggle)
    if (config.is_stateful) {
        const currentButtonStates = store.get('buttonStates');
        const isOn = currentButtonStates[slotId] || false;
        
        // Inverte estado
        currentButtonStates[slotId] = !isOn;
        store.set('buttonStates', currentButtonStates);
        
        // Decide qual lista de ações rodar
        actionsToRun = !isOn ? (config.actions_on || []) : (config.actions_off || []);
        
        // Atualiza visual imediato
        buttonElement.classList.toggle('is-active', !isOn);
    }

    actionsToRun.forEach(action => {
        const { type, params } = action;
        console.log(`Executando: ${type}`, params);

        switch (type) {
            case 'obs_scene':
                socket.emit('set_obs_scene', { scene_name: params.scene_name });
                break;
            case 'obs_source':
                socket.emit('toggle_source_visibility', params);
                break;
            case 'sound':
                socket.emit('play_sound', { file: params.file_name });
                break;
            case 'hotkey':
                socket.emit('run_hotkey', { keys_str: params.keys_str });
                break;
            case 'vts_hotkey':
                socket.emit('vts_trigger_hotkey', { hotkey_id: params.hotkey_id });
                break;
            case 'obs_set_mute_on':
                socket.emit('obs_set_mute', { input_name: params.input_name, mute_state: true });
                break;
            case 'obs_set_mute_off':
                socket.emit('obs_set_mute', { input_name: params.input_name, mute_state: false });
                break;
            case 'obs_stream_toggle':
                socket.emit('obs_stream_toggle');
                break;
            case 'obs_record_toggle':
                socket.emit('obs_record_toggle');
                break;
            case 'open_deck':
                store.set('currentDeckId', params.deck_id || "root");
                // Reseta estados visuais ao mudar de pasta
                store.set('buttonStates', {}); 
                break;
        }
    });
}