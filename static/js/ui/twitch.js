import { fetchApi } from '../utils.js';
import { socket } from '../socket.js';

export function initTwitch() {
    loadChannelInfo();
    loadStreamStats();
    setInterval(loadStreamStats, 60000);

    // Listeners de UI
    document.getElementById('update-button')?.addEventListener('click', updateChannelInfo);
    
    // Feed via Socket
    socket.on('eventsub_notification', (data) => addActivityToFeed(data.message, data.type));
}

async function loadChannelInfo() {
    try {
        const data = await fetchApi('/api/channel_info');
        document.getElementById('title').value = data.title;
        document.getElementById('current-category').textContent = data.category;
    } catch (e) { console.error(e); }
}

async function loadStreamStats() {
    try {
        const data = await fetchApi('/api/stream_stats');
        const statusBox = document.getElementById('status-box');
        const viewersBox = document.getElementById('viewers-box').querySelector('p');
        
        if (data.status === "online") {
            statusBox.querySelector('p').textContent = "Online";
            statusBox.className = "stat-box online";
            viewersBox.textContent = data.viewer_count;
        } else {
            statusBox.querySelector('p').textContent = "Offline";
            statusBox.className = "stat-box offline";
        }
    } catch (e) { console.error(e); }
}

async function updateChannelInfo() {
    const title = document.getElementById('title').value;
    // Nota: Lógica de busca de jogo simplificada para brevidade
    try {
        await fetchApi('/api/update_channel', {
            method: 'POST',
            body: JSON.stringify({ title })
        });
        alert("Atualizado!");
    } catch (e) { alert("Erro ao atualizar."); }
}

function addActivityToFeed(message, type) {
    const box = document.getElementById('activity-feed-box');
    if (!box) return;
    
    const div = document.createElement('div');
    div.className = `feed-item type-${type.replace(/\./g, '-')}`;
    div.textContent = message;
    
    box.prepend(div);
    if (box.children.length > 50) box.lastChild.remove();
}