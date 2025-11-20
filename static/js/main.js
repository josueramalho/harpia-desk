import { initSocket } from './socket.js';
import { initDeck } from './ui/deck.js';
import { initTwitch } from './ui/twitch.js';
import { initEditor } from './ui/editor.js';
import { initStatus } from './ui/status.js'; // [NOVO]
import { fetchApi } from './utils.js';
import { store } from './store.js';

document.addEventListener('DOMContentLoaded', async () => {
    console.log("[App] Inicializando Harpia Desk Modular...");

    // 1. Inicializa subsistemas
    initSocket();
    initDeck();
    initTwitch();
    initEditor();
    initStatus(); // [NOVO] Inicializa gerenciador de status e botões

    // 2. Carrega configuração inicial
    try {
        const config = await fetchApi('/api/deck_config');
        store.updateDeckConfig(config);
        
        // Define deck inicial
        const startDeck = config.settings?.start_deck || "root";
        store.set('currentDeckId', startDeck);
    } catch (e) {
        console.error("Erro fatal ao carregar config:", e);
    }
    
    // Listener antigo de status removido daqui e movido para ui/status.js
});