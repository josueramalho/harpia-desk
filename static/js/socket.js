import { store } from './store.js';

export const socket = io(window.location.origin + '/dashboard');

export function initSocket() {
    socket.on('connect', () => {
        console.log("[Socket] Conectado");
        socket.emit("get_obs_scene_details");
        socket.emit("get_vts_data");
    });

    socket.on('deck_updated', (config) => {
        console.log("[Socket] Deck atualizado");
        store.updateDeckConfig(config);
    });

    socket.on('obs_status', (data) => updateStatusUI('obs', data));
    socket.on('vts_status', (data) => updateStatusUI('vts', data));

    socket.on('obs_scene_details_data', (data) => {
        store.set('obsScenes', data.scenes || []);
        store.set('obsAudioSources', data.audio_inputs || []);
    });

    socket.on('vts_data_list', (data) => {
        store.set('vtsHotkeys', data.hotkeys || []);
    });

    // Eventos Twitch (Feed) são tratados no módulo UI/Twitch
}

function updateStatusUI(service, data) {
    // Dispara evento customizado para quem estiver ouvindo na UI
    const event = new CustomEvent('status-update', { detail: { service, ...data } });
    document.dispatchEvent(event);
}