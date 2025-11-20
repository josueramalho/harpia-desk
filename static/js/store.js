// Simple State Management (Reactive-ish)
class Store {
    constructor() {
        this.state = {
            deckConfig: { decks: {}, settings: {} },
            currentDeckId: "root",
            obsScenes: [],
            obsAudioSources: [],
            vtsHotkeys: [],
            buttonStates: {}, // Para botões toggle (ON/OFF)
            isEditMode: false
        };
        this.listeners = [];
    }

    get(key) {
        return this.state[key];
    }

    set(key, value) {
        this.state[key] = value;
        this.notify(key, value);
    }

    // Atalho para atualizar config inteira e resetar estados se necessário
    updateDeckConfig(config) {
        this.state.deckConfig = config;
        if (!this.state.deckConfig.decks[this.state.currentDeckId]) {
            this.state.currentDeckId = "root";
        }
        this.notify('deckConfig', config);
    }

    subscribe(key, callback) {
        this.listeners.push({ key, callback });
    }

    notify(key, value) {
        this.listeners
            .filter(l => l.key === key || l.key === '*')
            .forEach(l => l.callback(value));
    }
}

export const store = new Store();