# --- IMPORTS ---
import os
import time
import functools
import json
import socket
import atexit
import threading

# Importa o ProxyFix para o ngrok
from werkzeug.middleware.proxy_fix import ProxyFix

# O Monkey-patching DEVE vir ANTES de 'flask'
import eventlet
eventlet.monkey_patch(os=False) 

from flask import Flask, session, request, redirect, url_for, render_template, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import requests
import websocket
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Imports de Ação
import pygame.mixer
import keyboard 
import obsws_python as obs
try:
    from obsws_python import InputKind
except ImportError:
    print("Aviso: 'InputKind' não encontrado. Usando filtro de string para áudio.")
    InputKind = None

# --- Carregar Variáveis de Ambiente ---
load_dotenv()

# --- Configuração do App ---
app = Flask(__name__, template_folder='templates', static_folder='static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
socketio = SocketIO(app, async_mode='eventlet') 

# --- Inicialização de Ações ---
try:
    pygame.mixer.init()
    atexit.register(pygame.mixer.quit)
except pygame.error as e:
    print(f"Aviso: Falha ao inicializar o Pygame Mixer (Soundboard). Erro: {e}")

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "sounds")
if not os.path.exists(SOUNDS_DIR): os.makedirs(SOUNDS_DIR)
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

# --- Constantes ---
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
SCOPES = ("channel:manage:broadcast chat:read chat:edit channel:read:subscriptions "
          "moderator:read:followers channel:read:redemptions channel:read:hype_train channel:moderate")
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_URL = "https://api.twitch.tv/helix"
TWITCH_EVENTSUB_WSS = "wss://eventsub.wss.twitch.tv/ws"

OBS_HOST = os.getenv("OBS_HOST", "127.0.0.1")
OBS_PORT = int(os.getenv("OBS_PORT", 4455))
OBS_PASSWORD = os.getenv("OBS_PASSWORD")

VTS_HOST = os.getenv("VTS_HOST", "127.0.0.1")
VTS_PORT = int(os.getenv("VTS_PORT", 8001))
VTS_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "vts_token.json")

DECK_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "deck_config.json")

# --- Globais ---
obs_client = None
eventsub_ws = None
eventsub_thread = None
eventsub_session_id = None 

vts_ws = None
vts_token = None
vts_hotkeys = []

# --- LÓGICA DE AUTENTICAÇÃO (TWITCH) ---
def refresh_access_token():
    if 'refresh_token' not in session:
        session.clear()
        return False
    token_params = {
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token", "refresh_token": session['refresh_token']
    }
    try:
        response = requests.post(TWITCH_TOKEN_URL, data=token_params)
        response.raise_for_status()
        token_data = response.json()
        session['access_token'] = token_data['access_token']
        session['refresh_token'] = token_data['refresh_token']
        session['expires_at'] = time.time() + token_data['expires_in'] - 300
        return True
    except:
        session.clear()
        return False

def token_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'access_token' not in session: return jsonify({"error": "Não autorizado"}), 401
        if time.time() > session.get('expires_at', 0):
            if not refresh_access_token(): return jsonify({"error": "Sessão expirada"}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_twitch_headers():
    return {"Client-Id": CLIENT_ID, "Authorization": f"Bearer {session['access_token']}"}

@token_required
def get_current_user_id():
    if 'user_id' in session: return session['user_id']
    try:
        response = requests.get(f"{TWITCH_API_URL}/users", headers=get_twitch_headers())
        response.raise_for_status()
        user = response.json()["data"][0]
        session["user_id"] = user["id"]
        session["nickname"] = user["login"]
        return user["id"]
    except: return None

# --- ROTAS HTTP BÁSICAS ---
@app.route("/")
def index():
    if 'access_token' in session: return redirect(url_for('dashboard'))
    return render_template("index.html")

@app.route("/login")
def login():
    uri = f"{request.host_url}auth/callback"
    params = {"client_id": CLIENT_ID, "redirect_uri": uri, "response_type": "code", "scope": SCOPES}
    return redirect(f"{TWITCH_AUTH_URL}?{'&'.join([f'{k}={v}' for k, v in params.items()])}")

@app.route("/auth/callback")
def auth_callback():
    code = request.args.get('code')
    uri = f"{request.host_url}auth/callback"
    params = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": code, "grant_type": "authorization_code", "redirect_uri": uri}
    try:
        response = requests.post(TWITCH_TOKEN_URL, data=params)
        response.raise_for_status()
        data = response.json()
        session['access_token'] = data['access_token']
        session['refresh_token'] = data['refresh_token']
        session['expires_at'] = time.time() + data['expires_in'] - 300
        get_current_user_id()
        return redirect(url_for('dashboard'))
    except Exception as e:
        return f"Erro no login: {e}", 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/dashboard")
def dashboard():
    if 'access_token' not in session: return redirect(url_for('index'))
    return render_template("dashboard.html", twitch_nickname=session.get("nickname", "twitch"), parent_host=request.host)

# --- ROTAS API (DADOS) ---
@app.route("/api/channel_info")
@token_required
def get_channel_info():
    try:
        user_id = session.get('user_id')
        res = requests.get(f"{TWITCH_API_URL}/channels?broadcaster_id={user_id}", headers=get_twitch_headers())
        data = res.json()["data"][0]
        return jsonify({"title": data.get("title"), "category": data.get("game_name"), "category_id": data.get("game_id")})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/stream_stats")
@token_required
def get_stream_stats():
    try:
        user_id = session.get('user_id')
        res = requests.get(f"{TWITCH_API_URL}/streams?user_id={user_id}", headers=get_twitch_headers())
        data = res.json().get("data")
        if data:
            return jsonify({"status": "online", "viewer_count": data[0].get("viewer_count"), "started_at": data[0].get("started_at")})
        return jsonify({"status": "offline"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/search_games")
@token_required
def search_games():
    query = request.args.get("query")
    try:
        res = requests.get(f"{TWITCH_API_URL}/search/categories?query={query}", headers=get_twitch_headers())
        return jsonify(res.json().get("data", []))
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/update_channel", methods=["POST"])
@token_required
def update_channel():
    user_id = session.get('user_id')
    data = request.json
    body = {k: v for k, v in data.items() if k in ["title", "game_id"]}
    if not body: return jsonify({"error": "Nada para atualizar"}), 400
    headers = get_twitch_headers()
    headers["Content-Type"] = "application/json"
    try:
        requests.patch(f"{TWITCH_API_URL}/channels?broadcaster_id={user_id}", headers=headers, json=body)
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# --- CONFIGURAÇÃO DO DECK (ARQUIVO) ---
def read_deck_config():
    default = {"decks": {"root": {}}, "settings": {"start_deck": "root"}}
    if not os.path.exists(DECK_CONFIG_FILE):
        with open(DECK_CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(default, f, indent=4)
        return default
    try:
        with open(DECK_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            if "decks" not in config or "root" not in config.get("decks", {}):
                if "buttons" in config: config["decks"] = {"root": config["buttons"]}; del config["buttons"]
                else: config["decks"] = {"root": {}}
                config["settings"] = {"start_deck": "root"}
            return config
    except: return default

def write_deck_config(data):
    try:
        with open(DECK_CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)
        return True
    except: return False

@app.route("/api/deck_config", methods=["GET"])
@token_required
def get_deck_config_api(): return jsonify(read_deck_config())

@app.route("/api/save_button", methods=["POST"])
@token_required
def save_button_config():
    data = request.json
    slot_id, deck_id, config = data.get("slot_id"), data.get("deck_id", "root"), data.get("config")
    if not slot_id or config is None: return jsonify({"error": "Dados inválidos"}), 400
    
    config_data = read_deck_config()
    if deck_id not in config_data["decks"]: config_data["decks"][deck_id] = {}
    config_data["decks"][deck_id][slot_id] = config

    # Criação automática de pasta e botão voltar
    if config.get("actions_on"):
        for action in config["actions_on"]:
            if action.get("type") == "open_deck":
                new_id = action.get("params", {}).get("deck_id")
                if new_id and new_id != "root" and new_id not in config_data["decks"]:
                    config_data["decks"][new_id] = {}
                    config_data["decks"][new_id]["slot-0"] = {
                        "label": "Voltar", "icon": "fa-solid fa-arrow-left", "is_stateful": False,
                        "actions_on": [{"type": "open_deck", "params": {"deck_id": deck_id}}], "actions_off": []
                    }

    if write_deck_config(config_data):
        socketio.emit("deck_updated", config_data, namespace="/dashboard")
        return jsonify({"success": True})
    return jsonify({"error": "Falha ao salvar"}), 500

@app.route("/api/delete_button", methods=["POST"])
@token_required
def delete_button_config():
    data = request.json
    slot_id, deck_id = data.get("slot_id"), data.get("deck_id", "root")
    config_data = read_deck_config()
    if deck_id in config_data["decks"] and slot_id in config_data["decks"][deck_id]:
        del config_data["decks"][deck_id][slot_id]
        write_deck_config(config_data)
        socketio.emit("deck_updated", config_data, namespace="/dashboard")
    return jsonify({"success": True})

@app.route("/api/save_deck_layout", methods=["POST"])
@token_required
def save_deck_layout():
    data = request.json
    deck_id, layout = data.get("deck_id", "root"), data.get("buttons")
    config_data = read_deck_config()
    if deck_id not in config_data["decks"]: config_data["decks"][deck_id] = {}
    config_data["decks"][deck_id] = layout
    if write_deck_config(config_data):
        socketio.emit("deck_updated", config_data, namespace="/dashboard", skip_sid=request.sid)
        return jsonify({"success": True})
    return jsonify({"error": "Falha ao salvar"}), 500

@app.route('/api/upload_image', methods=['POST'])
@token_required
def upload_image():
    file = request.files.get('croppedImage')
    if file and file.filename:
        filename = secure_filename(f"{int(time.time())}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({"success": True, "url": url_for('uploaded_file', filename=filename)})
    return jsonify({"error": "Upload falhou"}), 400


# --- LÓGICA DE CONEXÃO SOB DEMANDA (OBS) ---

def fetch_obs_data_internal(client):
    """Busca dados do OBS. Lança exceção se falhar."""
    scenes_resp = client.get_scene_list()
    scenes_data = []
    for s in scenes_resp.scenes:
        items_resp = client.get_scene_item_list(s['sceneName'])
        sources = [{"name": i['sourceName'], "id": i['sceneItemId']} for i in items_resp.scene_items]
        scenes_data.append({"name": s['sceneName'], "sources": sources})
    
    inputs_resp = client.get_input_list()
    audio_inputs = []
    for i in inputs_resp.inputs:
        kind = i.get('inputKind', '')
        if 'capture' in kind or 'audio' in kind or 'input' in kind:
            audio_inputs.append({"name": i.get('inputName')})
            
    return {"scenes": scenes_data, "audio_inputs": audio_inputs}

def connect_obs():
    """Tenta conectar ao OBS uma vez (chamado no F5)."""
    global obs_client
    
    # Se já estiver conectado e respondendo, não faz nada
    if obs_client:
        try:
            obs_client.get_version()
            print("OBS já conectado.")
            # Força atualização dos dados para o frontend recém-conectado
            data = fetch_obs_data_internal(obs_client)
            socketio.emit("obs_status", {"connected": True, "message": "Conectado"}, namespace="/dashboard")
            socketio.emit("obs_scene_details_data", data, namespace="/dashboard")
            return
        except:
            print("OBS estava marcado como conectado mas falhou. Reconectando...")
            obs_client = None

    print("Tentando conectar ao OBS...")
    try:
        client = obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD, timeout=3)
        version = client.get_version()
        obs_client = client
        print(f"OBS Conectado! Versão: {version.obs_version}")
        
        socketio.emit("obs_status", {"connected": True, "message": "Conectado ao OBS"}, namespace="/dashboard")
        
        # Carrega dados iniciais
        data = fetch_obs_data_internal(obs_client)
        socketio.emit("obs_scene_details_data", data, namespace="/dashboard")
        
    except Exception as e:
        print(f"Falha ao conectar OBS: {e}")
        socketio.emit("obs_status", {"connected": False, "message": f"Erro: {str(e)}"}, namespace="/dashboard")

def execute_obs_command(command_lambda):
    """Wrapper para comandos do OBS. Se falhar, apenas desconecta."""
    global obs_client
    if not obs_client:
        return None # Não tenta reconectar automaticamente, espera F5
    try:
        return command_lambda(obs_client)
    except Exception as e:
        print(f"Erro no comando OBS: {e}")
        # Se for erro de socket, marca como desconectado
        err_str = str(e).lower()
        if "socket" in err_str or "closed" in err_str or "pipe" in err_str:
            print("Socket OBS fechado. Marcando como desconectado.")
            obs_client = None 
            socketio.emit("obs_status", {"connected": False, "message": "Desconectado (F5 p/ Reconectar)"}, namespace="/dashboard")
        raise e

# --- EVENTOS SOCKET OBS ---

@socketio.on("get_obs_scene_details", namespace="/dashboard")
def get_obs_scene_details():
    if obs_client:
        try:
            data = fetch_obs_data_internal(obs_client)
            emit("obs_scene_details_data", data, namespace="/dashboard")
        except Exception as e:
            emit("obs_error", {"message": f"Erro ao buscar detalhes: {e}"}, namespace="/dashboard")
    else:
        # Tenta conectar sob demanda se o front pediu dados e não estamos conectados
        socketio.start_background_task(connect_obs)

@socketio.on("set_obs_scene", namespace="/dashboard")
def set_obs_scene(data):
    if not data.get("scene_name"): return
    try:
        execute_obs_command(lambda c: c.set_current_program_scene(data["scene_name"]))
        emit("obs_status", {"connected": True, "message": f"Cena: {data['scene_name']}"}, namespace="/dashboard")
    except: pass

@socketio.on("toggle_source_visibility", namespace="/dashboard")
def toggle_source_visibility(data):
    scene, source = data.get("scene_name"), data.get("source_name")
    if not scene or not source: return
    try:
        def logic(c):
            iid = c.get_scene_item_id(scene, source).scene_item_id
            curr = c.get_scene_item_enabled(scene, iid).scene_item_enabled
            c.set_scene_item_enabled(scene, iid, not curr)
            return not curr
        state = execute_obs_command(logic)
        emit("obs_status", {"connected": True, "message": f"{source}: {'ON' if state else 'OFF'}"}, namespace="/dashboard")
    except: pass

@socketio.on("obs_stream_toggle", namespace="/dashboard")
def obs_stream_toggle():
    try:
        execute_obs_command(lambda c: c.toggle_stream())
        emit("obs_status", {"connected": True, "message": "Stream Toggle enviado"}, namespace="/dashboard")
    except: pass

@socketio.on("obs_record_toggle", namespace="/dashboard")
def obs_record_toggle():
    try:
        execute_obs_command(lambda c: c.toggle_record())
        emit("obs_status", {"connected": True, "message": "Record Toggle enviado"}, namespace="/dashboard")
    except: pass

@socketio.on("obs_set_mute", namespace="/dashboard")
def obs_set_mute(data):
    input_name, state = data.get("input_name"), data.get("mute_state")
    if input_name is None or state is None: return
    try:
        execute_obs_command(lambda c: c.set_input_mute(input_name, state))
        emit("obs_status", {"connected": True, "message": f"Áudio {input_name}: {'Mutado' if state else 'Aberto'}"}, namespace="/dashboard")
    except: pass


# --- LÓGICA DE CONEXÃO SOB DEMANDA (VTS) ---

def vts_listen_loop():
    """Loop de leitura do socket VTS. Roda apenas enquanto conectado."""
    global vts_ws, vts_token, vts_hotkeys
    print("Iniciando loop de leitura VTS...")
    
    while vts_ws:
        try:
            resp = vts_ws.recv()
            if not resp: 
                break # Socket fechou
            
            msg = json.loads(resp)
            mtype = msg.get("messageType")
            data = msg.get("data", {})
            
            if mtype == "AuthenticationTokenResponse":
                vts_token = data.get("authenticationToken")
                with open(VTS_TOKEN_FILE, 'w') as f: json.dump(data, f)
                vts_send_request(vts_ws, "AuthenticationRequest", {"pluginName": "FoxyDeck", "pluginDeveloper": "Foxy", "authenticationToken": vts_token})
            
            elif mtype == "AuthenticationResponse":
                if data.get("authenticated"):
                    socketio.emit("vts_status", {"connected": True, "message": "VTS Conectado"}, namespace="/dashboard")
                    vts_send_request(vts_ws, "HotkeysInCurrentModelRequest")
                else:
                    print("VTS: Token inválido.")
                    vts_token = None
                    if os.path.exists(VTS_TOKEN_FILE): os.remove(VTS_TOKEN_FILE)
                    # Tenta re-autenticar solicitando novo token
                    vts_send_request(vts_ws, "AuthenticationTokenRequest", {"pluginName": "FoxyDeck", "pluginDeveloper": "Foxy"})
            
            elif mtype == "HotkeysInCurrentModelResponse":
                vts_hotkeys = data.get("availableHotkeys", [])
                socketio.emit("vts_data_list", {"hotkeys": vts_hotkeys}, namespace="/dashboard")
            
            elif mtype == "APIError":
                err_id = data.get("errorID")
                if err_id == 100: # User needs to allow
                    socketio.emit("vts_status", {"connected": False, "message": "Aceite no VTube Studio!"}, namespace="/dashboard")

        except Exception as e:
            print(f"Erro leitura VTS: {e}")
            break # Quebra loop em erro de socket

    print("Loop VTS encerrado. Desconectado.")
    vts_ws = None
    socketio.emit("vts_status", {"connected": False, "message": "Desconectado"}, namespace="/dashboard")

def connect_vts():
    """Tenta conectar ao VTS uma vez (F5)."""
    global vts_ws, vts_token
    
    if vts_ws:
        try:
            # Teste simples de envio (ping)
            vts_ws.ping()
            # Se ok, reenvia dados
            if vts_hotkeys: socketio.emit("vts_data_list", {"hotkeys": vts_hotkeys}, namespace="/dashboard")
            socketio.emit("vts_status", {"connected": True, "message": "VTS Conectado"}, namespace="/dashboard")
            # Pede refresh das hotkeys
            vts_send_request(vts_ws, "HotkeysInCurrentModelRequest")
            return
        except:
            vts_ws = None # Estava quebrado

    print("Tentando conectar ao VTS...")
    try:
        url = f"ws://{VTS_HOST}:{VTS_PORT}"
        vts_ws = websocket.create_connection(url)
        
        # Inicia thread de leitura APENAS se conectar
        socketio.start_background_task(vts_listen_loop)
        
        # Fluxo de Autenticação
        if os.path.exists(VTS_TOKEN_FILE):
            with open(VTS_TOKEN_FILE, 'r') as f: vts_token = json.load(f).get("authenticationToken")
        
        if vts_token:
            vts_send_request(vts_ws, "AuthenticationRequest", {"pluginName": "FoxyDeck", "pluginDeveloper": "Foxy", "authenticationToken": vts_token})
        else:
            vts_send_request(vts_ws, "AuthenticationTokenRequest", {"pluginName": "FoxyDeck", "pluginDeveloper": "Foxy"})
            
    except Exception as e:
        print(f"Falha ao conectar VTS: {e}")
        socketio.emit("vts_status", {"connected": False, "message": "VTS Offline"}, namespace="/dashboard")

def vts_send_request(ws, msg_type, data=None):
    payload = {"apiName": "FoxyDeck", "apiVersion": "1.0", "requestID": str(int(time.time()*1000)), "messageType": msg_type}
    if data: payload["data"] = data
    try: ws.send(json.dumps(payload))
    except: pass # Erro será pego no loop de leitura ou na proxima tentativa

@socketio.on("get_vts_data", namespace="/dashboard")
def get_vts_data():
    socketio.emit("vts_data_list", {"hotkeys": vts_hotkeys}, namespace="/dashboard")
    if vts_ws:
        vts_send_request(vts_ws, "HotkeysInCurrentModelRequest")
    else:
        socketio.start_background_task(connect_vts)

@socketio.on("vts_trigger_hotkey", namespace="/dashboard")
def vts_trigger_hotkey(data):
    hid = data.get("hotkey_id")
    if vts_ws and hid:
        vts_send_request(vts_ws, "HotkeyTriggerRequest", {"hotkeyID": hid})

# --- OUTROS EVENTOS ---
@socketio.on("run_hotkey", namespace="/dashboard")
def run_hotkey(data):
    try: keyboard.press_and_release(data.get("keys_str", ""))
    except Exception as e: print(f"Erro Hotkey: {e}")

@socketio.on("play_sound", namespace="/dashboard")
def play_sound(data):
    f = data.get("file")
    if not f or ".." in f: return
    try: pygame.mixer.Sound(os.path.join(SOUNDS_DIR, f)).play()
    except Exception as e: print(f"Erro Som: {e}")

# --- EVENTOSUB (CORRIGIDO) ---

def _get_twitch_headers_threadsafe(token):
    return {
        "Client-Id": CLIENT_ID, "Authorization": f"Bearer {token}"
    }

def create_eventsub_subscription(access_token, user_id, eventsub_id, event_type, version="1"):
    headers = _get_twitch_headers_threadsafe(access_token)
    headers["Content-Type"] = "application/json"
    if event_type == "channel.raid": condition = {"to_broadcaster_user_id": user_id}
    else: condition = {"broadcaster_user_id": user_id}
    if event_type == "channel.follow":
        version = "2"
        condition = {"broadcaster_user_id": user_id, "moderator_user_id": user_id}
    body = {
        "type": event_type, "version": version, "condition": condition,
        "transport": {"method": "websocket", "session_id": eventsub_id}
    }
    try:
        response = requests.post(f"{TWITCH_API_URL}/eventsub/subscriptions", headers=headers, json=body)
        if response.status_code != 409: # 409 significa que já existe
            response.raise_for_status()
        print(f"EventSub: Assinatura para '{event_type}' OK.")
        return True
    except Exception as e:
        print(f"Erro ao criar assinatura EventSub ({event_type}): {e}")
        return False

def connect_eventsub_client(token, user_id):
    global eventsub_ws
    try:
        eventsub_ws = websocket.create_connection(TWITCH_EVENTSUB_WSS)
        while True:
            res = eventsub_ws.recv()
            if not res: break
            msg = json.loads(res)
            mtype = msg.get("metadata", {}).get("message_type")
            if mtype == "session_welcome":
                sid = msg["payload"]["session"]["id"]
                create_eventsub_subscription(token, user_id, sid, "channel.follow", "2")
                create_eventsub_subscription(token, user_id, sid, "channel.subscribe")
            elif mtype == "notification":
                evt = msg["payload"]["event"]
                etype = msg["payload"]["subscription"]["type"]
                txt = f"Evento: {etype}"
                if etype == "channel.follow": txt = f"Novo Seguidor: {evt['user_name']}"
                socketio.emit("eventsub_notification", {"message": txt, "type": etype}, namespace="/dashboard")
    except: pass
    if eventsub_ws: eventsub_ws.close()

@socketio.on("connect", namespace="/dashboard")
def on_socket_connect(auth=None):
    global eventsub_thread
    if 'access_token' in session:
        if time.time() > session.get('expires_at', 0): 
            if not refresh_access_token(): return

    # DISPARA CONEXÕES SOB DEMANDA (Uma única vez por F5)
    if OBS_PASSWORD:
        socketio.start_background_task(connect_obs)
    
    socketio.start_background_task(connect_vts)
        
    if eventsub_thread is None and 'access_token' in session:
        eventsub_thread = socketio.start_background_task(connect_eventsub_client, session['access_token'], session['user_id'])

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000, host='0.0.0.0')