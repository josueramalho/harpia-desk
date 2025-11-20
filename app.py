# --- CRÍTICO: MONKEY PATCH DEVE SER A PRIMEIRA LINHA ---
import eventlet
eventlet.monkey_patch(os=False)

import os
import time
import json
import logging
import requests 
import pygame.mixer
import keyboard

from flask import Flask, session, request, redirect, url_for, render_template, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

# --- MÓDULOS CUSTOMIZADOS ---
# Importe após o monkey_patch para garantir que usem sockets patched
from services.obs_manager import obs_manager
from services.vts_manager import vts_manager
from utils.security import is_safe_file

# --- CONFIGURAÇÃO DE LOGGING ---
# Configuração simples para evitar recursão
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HarpiaDesk")

# --- CONFIGURAÇÃO APP ---
load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "TROQUE_ISSO_EM_PROD_POR_UMA_HASH_FORTE")
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
DECK_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "deck_config.json")

# Constantes Twitch
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_API_URL = "https://api.twitch.tv/helix"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
SCOPES = "channel:manage:broadcast chat:read chat:edit channel:read:subscriptions moderator:read:followers channel:read:redemptions channel:read:hype_train channel:moderate"

# Garante diretórios
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), "sounds"), exist_ok=True)

socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# --- INICIALIZAÇÃO DE SERVIÇOS ---
try:
    pygame.mixer.init()
except Exception as e:
    logger.warning(f"Sem áudio (pygame): {e}")

# Configura OBS (Singleton)
obs_manager.configure(
    host=os.getenv("OBS_HOST", "127.0.0.1"),
    port=int(os.getenv("OBS_PORT", 4455)),
    password=os.getenv("OBS_PASSWORD")
)

# Configura VTS (Singleton)
def vts_event_handler(event_type, data):
    if event_type == "STATUS":
        socketio.emit("vts_status", data, namespace="/dashboard")
    elif event_type == "HOTKEYS":
        socketio.emit("vts_data_list", data, namespace="/dashboard")

vts_manager.configure(
    host=os.getenv("VTS_HOST", "127.0.0.1"),
    port=int(os.getenv("VTS_PORT", 8001)),
    token_file=os.path.join(os.path.dirname(__file__), "vts_token.json"),
    callback=vts_event_handler
)

# --- HELPERS ---

def get_twitch_headers():
    token = session.get('access_token')
    if not token:
        # Se não tiver token na sessão, tenta renovar ou falha
        raise ValueError("Token de acesso não encontrado.")
    return {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

def read_deck_config():
    default_config = {"decks": {"root": {}}, "settings": {"start_deck": "root"}}
    if not os.path.exists(DECK_CONFIG_FILE):
        try:
            with open(DECK_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)
        except: return default_config
        return default_config
    try:
        with open(DECK_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            if "decks" not in config: config["decks"] = {"root": {}}
            return config
    except:
        return default_config

def write_deck_config(data):
    try:
        with open(DECK_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar deck: {e}")
        return False

# --- ROTAS HTTP ---

@app.route("/")
def index():
    if 'access_token' in session:
        return redirect(url_for('dashboard'))
    return render_template("index.html")

@app.route("/login")
def login():
    redirect_uri = url_for('auth_callback', _external=True)
    params = {
        "client_id": CLIENT_ID, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": SCOPES
    }
    url = f"{TWITCH_AUTH_URL}?{'&'.join([f'{k}={v}' for k,v in params.items()])}"
    return redirect(url)

@app.route("/auth/callback")
def auth_callback():
    code = request.args.get('code')
    redirect_uri = url_for('auth_callback', _external=True)
    params = {
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri
    }
    try:
        res = requests.post(TWITCH_TOKEN_URL, data=params)
        res.raise_for_status()
        data = res.json()
        
        session['access_token'] = data['access_token']
        session['refresh_token'] = data.get('refresh_token')
        
        # Busca dados do usuário
        headers = {"Client-Id": CLIENT_ID, "Authorization": f"Bearer {data['access_token']}"}
        user_res = requests.get(f"{TWITCH_API_URL}/users", headers=headers)
        user_res.raise_for_status()
        user_data = user_res.json()['data'][0]
        
        session['user_id'] = user_data['id']
        session['nickname'] = user_data['login']
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        logger.error(f"Erro login Twitch: {e}")
        return f"Erro de login: {e}", 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route("/dashboard")
def dashboard():
    if 'access_token' not in session: return redirect(url_for('index'))
    return render_template("dashboard.html", twitch_nickname=session.get("nickname"), parent_host=request.host)

# --- API ENDPOINTS ---

@app.route('/api/deck_config')
def get_deck_config_api():
    if 'access_token' not in session: return jsonify({"error": "Unauthorized"}), 401
    return jsonify(read_deck_config())

@app.route('/api/save_button', methods=['POST'])
def save_button():
    if 'access_token' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    slot, deck, config = data.get('slot_id'), data.get('deck_id', 'root'), data.get('config')
    
    full_config = read_deck_config()
    if deck not in full_config['decks']: full_config['decks'][deck] = {}
    full_config['decks'][deck][slot] = config
    
    # Criação de sub-pastas
    if config.get("actions_on"):
        for action in config["actions_on"]:
            if action.get("type") == "open_deck":
                new_id = action.get("params", {}).get("deck_id")
                if new_id and new_id != "root" and new_id not in full_config["decks"]:
                    full_config["decks"][new_id] = {}
                    full_config["decks"][new_id]["slot-0"] = {
                        "label": "Voltar", "icon": "fa-solid fa-arrow-left", "is_stateful": False,
                        "actions_on": [{"type": "open_deck", "params": {"deck_id": deck}}], "actions_off": []
                    }

    if write_deck_config(full_config):
        socketio.emit('deck_updated', full_config, namespace='/dashboard')
        return jsonify({"success": True})
    return jsonify({"error": "Erro ao salvar"}), 500

@app.route('/api/delete_button', methods=['POST'])
def delete_button():
    if 'access_token' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    slot, deck = data.get('slot_id'), data.get('deck_id', 'root')
    
    full_config = read_deck_config()
    if deck in full_config['decks'] and slot in full_config['decks'][deck]:
        del full_config['decks'][deck][slot]
        if write_deck_config(full_config):
            socketio.emit('deck_updated', full_config, namespace='/dashboard')
    return jsonify({"success": True})

@app.route('/api/save_deck_layout', methods=['POST'])
def save_layout():
    if 'access_token' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    deck, layout = data.get('deck_id'), data.get('buttons')
    
    full_config = read_deck_config()
    if deck not in full_config['decks']: full_config['decks'][deck] = {}
    full_config['decks'][deck] = layout
    
    if write_deck_config(full_config):
        socketio.emit('deck_updated', full_config, namespace='/dashboard', skip_sid=request.sid)
        return jsonify({"success": True})
    return jsonify({"error": "Failed"}), 500

@app.route('/api/channel_info')
def channel_info():
    if 'access_token' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        uid = session.get('user_id')
        res = requests.get(f"{TWITCH_API_URL}/channels?broadcaster_id={uid}", headers=get_twitch_headers())
        res.raise_for_status()
        data = res.json()['data']
        if not data: return jsonify({"title": "Offline", "category": "N/A"})
        return jsonify({"title": data[0]['title'], "category": data[0]['game_name']})
    except Exception as e:
        return jsonify({"title": "Erro", "category": "Erro"}), 200 # Retorna 200 para não quebrar o frontend

@app.route('/api/stream_stats')
def stream_stats():
    if 'access_token' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        uid = session.get('user_id')
        res = requests.get(f"{TWITCH_API_URL}/streams?user_id={uid}", headers=get_twitch_headers())
        res.raise_for_status()
        data = res.json()['data']
        if data:
            return jsonify({"status": "online", "viewer_count": data[0]['viewer_count']})
        return jsonify({"status": "offline"})
    except Exception as e:
        return jsonify({"status": "offline"}), 200

@app.route('/api/update_channel', methods=['POST'])
def update_channel():
    if 'access_token' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    try:
        uid = session['user_id']
        headers = get_twitch_headers()
        headers['Content-Type'] = 'application/json'
        requests.patch(f"{TWITCH_API_URL}/channels?broadcaster_id={uid}", headers=headers, json=data)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Erro ao atualizar canal: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/upload_image', methods=['POST'])
def upload_image():
    if 'access_token' not in session: return jsonify({"error": "Unauthorized"}), 401
    file = request.files.get('croppedImage')
    if not file or file.filename == '': return jsonify({"error": "No file"}), 400
    if not is_safe_file(file): return jsonify({"error": "Invalid file"}), 400
    
    filename = secure_filename(f"{int(time.time())}_{file.filename}")
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return jsonify({"success": True, "url": url_for('uploaded_file', filename=filename)})

# --- SOCKET IO ---

@socketio.on("connect", namespace="/dashboard")
def handle_connect():
    if 'access_token' not in session: return False
    
    # Conecta OBS em background (uma vez)
    socketio.start_background_task(background_obs_connect)
    
    # Inicia VTS se necessário e envia status
    vts_manager.start()
    vts_manager.request_hotkeys()
    
    if vts_manager.is_connected:
        emit("vts_status", {"connected": True, "message": "VTS Online"})
    else:
        emit("vts_status", {"connected": False, "message": "VTS Offline"})

def background_obs_connect():
    """Tenta conectar OBS e envia status."""
    success = obs_manager.connect()
    msg = "Conectado" if success else "Desconectado"
    socketio.emit("obs_status", {"connected": success, "message": msg}, namespace="/dashboard")
    if success:
        data = obs_manager.get_scene_details()
        if data: socketio.emit("obs_scene_details_data", data, namespace="/dashboard")

# --- Eventos de Reconexão Manual ---
@socketio.on("reconnect_obs", namespace="/dashboard")
def manual_obs_reconnect():
    socketio.start_background_task(background_obs_connect)

@socketio.on("reconnect_vts", namespace="/dashboard")
def manual_vts_reconnect():
    vts_manager.start()
    status = "Online" if vts_manager.is_connected else "Tentando..."
    emit("vts_status", {"connected": vts_manager.is_connected, "message": status}, namespace="/dashboard")

# --- Eventos de Ação ---
@socketio.on("get_obs_scene_details", namespace="/dashboard")
def get_obs_details():
    data = obs_manager.get_scene_details()
    if data: emit("obs_scene_details_data", data, namespace="/dashboard")

@socketio.on("set_obs_scene", namespace="/dashboard")
def set_obs_scene(data):
    if data.get("scene_name"):
        obs_manager.execute(lambda c: c.set_current_program_scene(data["scene_name"]))

@socketio.on("toggle_source_visibility", namespace="/dashboard")
def toggle_source(data):
    scene, source = data.get("scene_name"), data.get("source_name")
    if scene and source:
        def _toggle(c):
            iid = c.get_scene_item_id(scene, source).scene_item_id
            curr = c.get_scene_item_enabled(scene, iid).scene_item_enabled
            c.set_scene_item_enabled(scene, iid, not curr)
            return not curr
        state = obs_manager.execute(_toggle)
        emit("obs_status", {"connected": True, "message": f"{source}: {'ON' if state else 'OFF'}"}, namespace="/dashboard")

@socketio.on("obs_set_mute", namespace="/dashboard")
def obs_set_mute(data):
    obs_manager.execute(lambda c: c.set_input_mute(data["input_name"], data["mute_state"]))

@socketio.on("obs_stream_toggle", namespace="/dashboard")
def obs_stream(): obs_manager.execute(lambda c: c.toggle_stream())

@socketio.on("obs_record_toggle", namespace="/dashboard")
def obs_rec(): obs_manager.execute(lambda c: c.toggle_record())

@socketio.on("vts_trigger_hotkey", namespace="/dashboard")
def vts_hotkey(data):
    vts_manager.trigger_hotkey(data.get("hotkey_id"))

@socketio.on("play_sound", namespace="/dashboard")
def play_sound(data):
    path = os.path.join("sounds", secure_filename(data.get("file", "")))
    if os.path.exists(path):
        try: pygame.mixer.Sound(path).play()
        except: pass

@socketio.on("run_hotkey", namespace="/dashboard")
def run_hotkey(data):
    try: keyboard.press_and_release(data.get("keys_str", ""))
    except: pass

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000, host='0.0.0.0')