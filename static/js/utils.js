// Mapeamento de teclas para exibição amigável
export const codeToKeyName = {
    "ControlLeft": "left ctrl", "ControlRight": "right ctrl",
    "ShiftLeft": "left shift", "ShiftRight": "right shift",
    "AltLeft": "left alt", "AltRight": "right alt",
    "MetaLeft": "left windows", "MetaRight": "right windows",
    "Enter": "enter", "Escape": "esc", "Space": "space",
    "ArrowUp": "up", "ArrowDown": "down", "ArrowLeft": "left", "ArrowRight": "right"
    // ... Adicione o restante do mapeamento original se necessário
};

export function friendlyKeyName(key) {
    if (!key) return "";
    return key.split(' ').map(s => s.charAt(0).toUpperCase() + s.substring(1)).join(' ');
}

export async function fetchApi(url, options = {}) {
    if (!(options.body instanceof FormData)) {
        options.headers = { ...options.headers, 'Content-Type': 'application/json' };
    }
    const response = await fetch(url, options);
    if (response.status === 401) {
        window.location.reload();
        throw new Error("Sessão expirada");
    }
    if (!response.ok) throw new Error(await response.text());
    return response.json();
}