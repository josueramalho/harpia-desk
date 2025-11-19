# --- IMPORTS ---
import os
import time
import functools
import json
import socket
import atexit

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
import keyboard # Usamos 'keyboard' para hotkeys de baixo nível
import obsws_python as obs
try:
    from obsws_python import InputKind
except ImportError:
    # Fallback para versões mais antigas do obsws_python
    print("Aviso: 'InputKind' não encontrado. Usando filtro de string para áudio.")
    InputKind = None

# --- Carregar Variáveis de Ambiente ---
load_dotenv()

# --- Configuração do App ---
app = Flask(__name__, template_folder='templates', static_folder='static')

# Diga ao Flask para confiar nos cabeçalhos do proxy (ngrok)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
socketio = SocketIO(app, async_mode='eventlet') 

# --- Inicialização de Ações ---
try:
    pygame.mixer.init()
    atexit.register(pygame.mixer.quit) # Garante que o mixer feche corretamente
except pygame.error as e:
    print(f"Aviso: Falha ao inicializar o Pygame Mixer (Soundboard). Erro: {e}")
SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "sounds")
if not os.path.exists(SOUNDS_DIR):
    os.makedirs(SOUNDS_DIR)
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Constantes da Twitch ---
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
SCOPES = (
    "channel:manage:broadcast chat:read chat:edit " 
    "channel:read:subscriptions moderator:read:followers "
    "channel:read:redemptions channel:read:hype_train "
    "channel:moderate"
)
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_URL = "https://api.twitch.tv/helix"
TWITCH_EVENTSUB_WSS = "wss://eventsub.wss.twitch.tv/ws" # URL Corrigida

# --- Constantes do OBS ---
OBS_HOST = os.getenv("OBS_HOST", "127.0.0.1")
OBS_PORT = int(os.getenv("OBS_PORT", 4455))
OBS_PASSWORD = os.getenv("OBS_PASSWORD")

# --- Constantes do VTube Studio ---
VTS_HOST = os.getenv("VTS_HOST", "127.0.0.1")
VTS_PORT = int(os.getenv("VTS_PORT", 8001))
VTS_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "vts_token.json")

# --- Caminho para o "Banco de Dados" ---
DECK_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "deck_config.json")

# --- Globais ---
obs_client = None
obs_thread = None
eventsub_ws = None
eventsub_thread = None
eventsub_session_id = None 
vts_ws = None
vts_thread = None
vts_token = None
vts_hotkeys = []

# --- 1. LÓGICA DE AUTENTICAÇÃO E REFRESH TOKEN ---

def log_twitch_ratelimit(response):
    """Extrai os headers de rate limit da Twitch e os imprime no console."""
    headers = response.headers
    remaining = headers.get('Ratelimit-Remaining')
    limit = headers.get('Ratelimit-Limit')
    reset = headers.get('Ratelimit-Reset')
    if remaining and limit and reset:
        try:
            seconds_to_reset = max(0, int(reset) - int(time.time()))
            print(f"[TWITCH API] Rate Limit: {remaining}/{limit} restantes. (Reset em {seconds_to_reset}s)")
        except (ValueError, TypeError):
            print(f"[TWITCH API] Rate Limit: {remaining}/{limit} restantes.")

def refresh_access_token():
    if 'refresh_token' not in session:
        print("Erro: Refresh token não encontrado na sessão.")
        session.clear()
        return False
    print("Token expirado. Tentando atualizar...")
    token_params = {
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token", "refresh_token": session['refresh_token']
    }
    try:
        response = requests.post(TWITCH_TOKEN_URL, data=token_params)
        log_twitch_ratelimit(response) 
        response.raise_for_status()
        token_data = response.json()
        session['access_token'] = token_data['access_token']
        session['refresh_token'] = token_data['refresh_token']
        session['expires_at'] = time.time() + token_data['expires_in'] - 300
        print("Token atualizado com sucesso.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Erro ao atualizar token: {e}")
        session.clear()
        return False

def token_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'access_token' not in session:
            return jsonify({"error": "Não autorizado"}), 401
        if time.time() > session.get('expires_at', 0):
            if not refresh_access_token():
                return jsonify({"error": "Sessão expirada. Faça login novamente."}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_twitch_headers():
    return {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {session['access_token']}"
    }

@token_required
def get_current_user_id():
    if 'user_id' in session:
        return session['user_id']
    headers = get_twitch_headers()
    try:
        response = requests.get(f"{TWITCH_API_URL}/users", headers=headers)
        log_twitch_ratelimit(response) 
        response.raise_for_status()
        user_data = response.json()
        if user_data.get("data"):
            user = user_data["data"][0]
            session["user_id"] = user["id"]
            session["nickname"] = user["login"]
            return user["id"]
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar ID do usuário: {e}")
        return None

# --- 2. Rotas de Autenticação (Dinâmicas) ---

@app.route("/")
def index():
    """Renderiza a página de login."""
    if 'access_token' in session:
        return redirect(url_for('dashboard'))
    return render_template("index.html")

@app.route("/login")
def login():
    dynamic_redirect_uri = f"{request.host_url}auth/callback"
    print(f"Gerando link de login com REDIRECT_URI: {dynamic_redirect_uri}")
    auth_params = {
        "client_id": CLIENT_ID, "redirect_uri": dynamic_redirect_uri,
        "response_type": "code", "scope": SCOPES
    }
    auth_url = f"{TWITCH_AUTH_URL}?{'&'.join([f'{k}={v}' for k, v in auth_params.items()])}"
    return redirect(auth_url)

@app.route("/auth/callback")
def auth_callback():
    code = request.args.get('code')
    dynamic_redirect_uri = f"{request.host_url}auth/callback"
    print(f"Callback recebido. Validando com REDIRECT_URI: {dynamic_redirect_uri}")
    token_params = {
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "code": code, "grant_type": "authorization_code", "redirect_uri": dynamic_redirect_uri
    }
    try:
        response = requests.post(TWITCH_TOKEN_URL, data=token_params)
        log_twitch_ratelimit(response) 
        response.raise_for_status()
        token_data = response.json()
        session['access_token'] = token_data['access_token']
        session['refresh_token'] = token_data['refresh_token']
        session['expires_at'] = time.time() + token_data['expires_in'] - 300 
        get_current_user_id() 
        return redirect(url_for('dashboard'))
    except requests.exceptions.RequestException as e:
        try: error_details = e.response.json()
        except: error_details = str(e)
        print(f"Erro ao obter token: {error_details}")
        return f"Erro ao obter token: {error_details}", 500
        
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- ROTA PARA SERVIR IMAGENS DE UPLOAD ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve os arquivos de imagem que foram enviados."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- 3. Rotas da API (Twitch) ---

@app.route("/dashboard")
def dashboard():
    """Passa o nome do canal e o host para o template do iframe."""
    if 'access_token' not in session:
        return redirect(url_for('index'))
    
    nickname = session.get("nickname", "twitch") 
    host = request.host # ex: "abc.ngrok-free.app"
    
    return render_template("dashboard.html", 
                           twitch_nickname=nickname,
                           parent_host=host)

@app.route("/api/channel_info")
@token_required
def get_channel_info():
    headers = get_twitch_headers()
    user_id = session.get('user_id')
    try:
        response = requests.get(f"{TWITCH_API_URL}/channels?broadcaster_id={user_id}", headers=headers)
        log_twitch_ratelimit(response) 
        response.raise_for_status()
        data = response.json()["data"][0]
        return jsonify({
            "title": data.get("title"), "category": data.get("game_name"),
            "category_id": data.get("game_id")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stream_stats")
@token_required
def get_stream_stats():
    headers = get_twitch_headers()
    user_id = session.get('user_id')
    try:
        response = requests.get(f"{TWITCH_API_URL}/streams?user_id={user_id}", headers=headers)
        log_twitch_ratelimit(response) 
        response.raise_for_status()
        data = response.json().get("data")
        if data:
            stream_data = data[0]
            return jsonify({
                "status": "online", "viewer_count": stream_data.get("viewer_count"),
                "started_at": stream_data.get("started_at")
            })
        else:
            return jsonify({"status": "offline"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/search_games")
@token_required
def search_games():
    query = request.args.get("query")
    if not query:
        return jsonify({"error": "Query não fornecida"}), 400
    headers = get_twitch_headers()
    try:
        response = requests.get(f"{TWITCH_API_URL}/search/categories?query={query}", headers=headers)
        log_twitch_ratelimit(response) 
        response.raise_for_status()
        return jsonify(response.json().get("data", []))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/update_channel", methods=["POST"])
@token_required
def update_channel():
    user_id = session.get('user_id')
    data = request.json
    body = {}
    if "title" in data: body["title"] = data["title"]
    if "game_id" in data: body["game_id"] = data["game_id"]
    if not body:
        return jsonify({"error": "Nada para atualizar"}), 400
    headers = get_twitch_headers()
    headers["Content-Type"] = "application/json"
    try:
        response = requests.patch(f"{TWITCH_API_URL}/channels?broadcaster_id={user_id}", headers=headers, json=body)
        log_twitch_ratelimit(response) 
        response.raise_for_status()
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 4. Rotas da API (Deck Config) ---

def read_deck_config():
    """Lê a configuração do deck, agora baseada em múltiplos decks (pastas)."""
    if not os.path.exists(DECK_CONFIG_FILE):
        # Nova estrutura padrão com decks
        default_config = {
            "decks": {
                "root": {} # O deck principal agora se chama 'root'
            },
            "settings": {
                "start_deck": "root"
            }
        }
        with open(DECK_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        return default_config
    try:
        with open(DECK_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Garante que a estrutura mínima exista em arquivos antigos
            if "decks" not in config or "root" not in config.get("decks", {}):
                 # Tenta migrar a estrutura antiga
                 if "buttons" in config:
                     print("Migrando estrutura antiga de 'buttons' para 'decks'...")
                     config["decks"] = {"root": config["buttons"]}
                     del config["buttons"]
                 else:
                     config["decks"] = {"root": {}}
                 config["settings"] = {"start_deck": "root"}
            return config
    except json.JSONDecodeError:
        print("Erro: deck_config.json está corrompido. Resetando...")
        return {
            "decks": {"root": {}},
            "settings": {"start_deck": "root"}
        }

def write_deck_config(config_data):
    try:
        with open(DECK_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        print(f"Erro ao salvar deck_config.json: {e}")
        return False

@app.route("/api/deck_config", methods=["GET"])
@token_required
def get_deck_config():
    config = read_deck_config()
    return jsonify(config)

@app.route("/api/save_button", methods=["POST"])
@token_required
def save_button_config():
    """Salva a configuração de um único botão em um deck específico."""
    data = request.json
    slot_id = data.get("slot_id")
    deck_id = data.get("deck_id", "root") # Recebe o deck_id do frontend
    button_config = data.get("config") # O objeto config completo
    
    if not slot_id or button_config is None:
        return jsonify({"error": "Dados inválidos"}), 400
        
    config_data = read_deck_config()
    
    # Garante que o deck exista no JSON
    if deck_id not in config_data["decks"]:
        config_data["decks"][deck_id] = {}
        
    # Salva o botão dentro do deck correto
    config_data["decks"][deck_id][slot_id] = button_config
    
    # --- [NOVO] Lógica de Criação Automática de Pasta ---
    # Verifica se alguma ação é 'open_deck' para criar a pasta
    if button_config.get("actions_on"):
        for action in button_config["actions_on"]:
            if action.get("type") == "open_deck":
                new_deck_id = action.get("params", {}).get("deck_id")
                
                # Se for um ID válido e *não* for 'root' e *não* existir...
                if new_deck_id and new_deck_id != "root" and new_deck_id not in config_data["decks"]:
                    print(f"Ação 'open_deck' detectada. Criando deck: {new_deck_id}")
                    
                    # 1. Cria o novo deck
                    config_data["decks"][new_deck_id] = {}
                    
                    # 2. Cria um botão "Voltar"
                    back_button_config = {
                        "label": "Voltar",
                        "icon": "fa-solid fa-arrow-left",
                        "is_stateful": False,
                        "actions_on": [
                            {
                                "type": "open_deck",
                                # Volta para o deck onde o botão de pasta foi criado
                                "params": {"deck_id": deck_id} 
                            }
                        ],
                        "actions_off": []
                    }
                    
                    # 3. Adiciona o botão "Voltar" no slot-0 do novo deck
                    config_data["decks"][new_deck_id]["slot-0"] = back_button_config
    # --- Fim da Lógica de Criação Automática ---

    if write_deck_config(config_data):
        socketio.emit("deck_updated", config_data, namespace="/dashboard")
        return jsonify({"success": True, "message": "Botão salvo."})
    else:
        return jsonify({"error": "Falha ao salvar no servidor"}), 500

@app.route("/api/delete_button", methods=["POST"])
@token_required
def delete_button_config():
    """Deleta um único botão de um deck específico."""
    data = request.json
    slot_id = data.get("slot_id")
    deck_id = data.get("deck_id", "root") # Recebe o deck_id do frontend
    
    if not slot_id:
        return jsonify({"error": "Slot ID não fornecido"}), 400
        
    config_data = read_deck_config()
    
    # Verifica se o deck e o botão existem antes de deletar
    if deck_id in config_data["decks"] and slot_id in config_data["decks"][deck_id]:
        del config_data["decks"][deck_id][slot_id]
        if write_deck_config(config_data):
            socketio.emit("deck_updated", config_data, namespace="/dashboard")
            return jsonify({"success": True, "message": "Botão deletado."})
        else:
            return jsonify({"error": "Falha ao salvar no servidor"}), 500
    else:
        # Se o deck ou botão não existir, apenas retorne sucesso (já está deletado)
        return jsonify({"success": True, "message": "Botão não encontrado."})

@app.route("/api/save_deck_layout", methods=["POST"])
@token_required
def save_deck_layout():
    """Salva a configuração de botões inteira (reordenada) para um deck específico."""
    data = request.json
    deck_id = data.get("deck_id", "root")
    buttons_layout = data.get("buttons") # Recebe o objeto 'buttons' reordenado
    
    if buttons_layout is None:
        return jsonify({"error": "Layout de botões não fornecido"}), 400
        
    config_data = read_deck_config()
    
    # Garante que o deck exista no JSON
    if deck_id not in config_data["decks"]:
        config_data["decks"][deck_id] = {}
        
    # Substitui a configuração de botões antiga pela nova (reordenada)
    config_data["decks"][deck_id] = buttons_layout
    
    if write_deck_config(config_data):
        # Emite a atualização para todos, exceto o remetente
        # O remetente atualizará sua UI localmente
        socketio.emit("deck_updated", config_data, namespace="/dashboard", skip_sid=request.sid)
        return jsonify({"success": True, "message": "Layout salvo."})
    else:
        return jsonify({"error": "Falha ao salvar layout no servidor"}), 500

@app.route('/api/upload_image', methods=['POST'])
@token_required
def upload_image():
    if 'croppedImage' not in request.files:
        return jsonify({"error": "Nenhum arquivo de imagem enviado"}), 400
    file = request.files['croppedImage']
    if file.filename == '':
        return jsonify({"error": "Nome de arquivo vazio"}), 400
    if file:
        filename = secure_filename(f"{int(time.time())}_{file.filename}")
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        file_url = url_for('uploaded_file', filename=filename)
        return jsonify({"success": True, "url": file_url})
    return jsonify({"error": "Falha no upload"}), 500

# --- 5. Lógica do Chat (REMOVIDA) ---

# --- 6. Lógica do OBS (Thread-safe e Robusta) ---

def connect_obs_client():
    global obs_client
    print(f"Tentando conectar ao OBS em ws://{OBS_HOST}:{OBS_PORT}...")
    try:
        obs_client = obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD, timeout=5)
        version = obs_client.get_version()
        print(f"Conectado ao OBS Studio. Versão: {version.obs_version}")
        socketio.emit("obs_status", {"connected": True, "message": "Conectado ao OBS"}, namespace="/dashboard")
    except Exception as e:
        print(f"Erro ao conectar ao OBS: {e}")
        obs_client = None
        socketio.emit("obs_status", {"connected": False, "message": f"Erro: {e}"}, namespace="/dashboard")

# [NOVO] Wrapper auxiliar para tentar reconectar automaticamente
def execute_obs_command(command_lambda, action_name="Comando OBS"):
    global obs_client
    
    # Tenta reconectar se estiver nulo
    if not obs_client:
        connect_obs_client()
        
    if not obs_client:
        # Se falhar, apenas retorna False ou levanta erro, sem crashar o socket
        return None

    try:
        return command_lambda(obs_client)
    except Exception as e:
        error_str = str(e).lower()
        # Se detectar que o socket fechou, tenta reconectar E reexecutar
        if "socket is already closed" in error_str or "broken pipe" in error_str or "connection" in error_str:
            print(f"Conexão perdida com OBS ({action_name}). Tentando reconectar...")
            obs_client = None
            connect_obs_client()
            if obs_client:
                try:
                    print(f"Reconectado! Reenviando {action_name}...")
                    return command_lambda(obs_client)
                except Exception as e2:
                     print(f"Falha no retry de {action_name}: {e2}")
                     raise e2
            else:
                print("Não foi possível reconectar ao OBS.")
                raise Exception("OBS desconectado.")
        else:
            raise e

@socketio.on("get_obs_scene_details", namespace="/dashboard")
def get_obs_scene_details():
    """Busca todas as cenas, suas fontes E todas as entradas de áudio."""
    
    def logic(client):
        scene_list_response = client.get_scene_list()
        scenes_data = []
        for scene in scene_list_response.scenes:
            scene_name = scene['sceneName']
            item_list_response = client.get_scene_item_list(scene_name)
            sources = []
            for item in item_list_response.scene_items:
                sources.append({"name": item['sourceName'], "id": item['sceneItemId']})
            scenes_data.append({"name": scene_name, "sources": sources})
            
        input_list_response = client.get_input_list()
        audio_inputs = []
        for input_data in input_list_response.inputs:
            kind = input_data.get('inputKind', '') 
            if 'capture' in kind or 'audio' in kind or 'input' in kind:
                audio_inputs.append({"name": input_data.get('inputName')})
        
        return {"scenes": scenes_data, "audio_inputs": audio_inputs}

    try:
        data = execute_obs_command(logic, "Get Scene Details")
        if data:
            emit("obs_scene_details_data", data, namespace="/dashboard")
            print("Dados de Cenas, Fontes e Áudio do OBS enviados ao frontend.")
    except Exception as e:
        emit("obs_error", {"message": f"Erro ao buscar detalhes do OBS: {e}"}, namespace="/dashboard")

@socketio.on("set_obs_scene", namespace="/dashboard")
def set_obs_scene(data):
    scene_name = data.get("scene_name")
    if not scene_name: return

    try:
        execute_obs_command(lambda c: c.set_current_program_scene(scene_name), "Mudar Cena")
        emit("obs_status", {"connected": True, "message": f"Cena: {scene_name}"}, namespace="/dashboard")
    except Exception as e:
        emit("obs_error", {"message": f"Erro ao mudar cena: {e}"}, namespace="/dashboard")

@socketio.on("toggle_source_visibility", namespace="/dashboard")
def toggle_source_visibility(data):
    scene_name = data.get("scene_name")
    source_name = data.get("source_name")
    if not scene_name or not source_name: return

    try:
        def logic(client):
            item_id = client.get_scene_item_id(scene_name, source_name).scene_item_id
            current_visibility = client.get_scene_item_enabled(scene_name, item_id).scene_item_enabled
            client.set_scene_item_enabled(scene_name, item_id, not current_visibility)
            return current_visibility
            
        visible = execute_obs_command(logic, "Toggle Source")
        status = 'OFF' if visible else 'ON' # Lógica invertida pois visible era o estado ANTERIOR
        emit("obs_status", {"connected": True, "message": f"{source_name}: {status}"}, namespace="/dashboard")
    except Exception as e:
        emit("obs_error", {"message": f"Erro ao alternar '{source_name}': {e}"}, namespace="/dashboard")

@socketio.on("obs_stream_toggle", namespace="/dashboard")
def obs_stream_toggle():
    try:
        execute_obs_command(lambda c: c.toggle_stream(), "Toggle Stream")
        emit("obs_status", {"connected": True, "message": "Comando de Stream enviado."}, namespace="/dashboard")
    except Exception as e:
        emit("obs_error", {"message": f"Erro no Stream: {e}"}, namespace="/dashboard")

@socketio.on("obs_record_toggle", namespace="/dashboard")
def obs_record_toggle():
    try:
        execute_obs_command(lambda c: c.toggle_record(), "Toggle Record")
        emit("obs_status", {"connected": True, "message": "Comando de Gravação enviado."}, namespace="/dashboard")
    except Exception as e:
        emit("obs_error", {"message": f"Erro na Gravação: {e}"}, namespace="/dashboard")

@socketio.on("obs_set_mute", namespace="/dashboard")
def obs_set_mute(data):
    """Define o estado de mudo de uma entrada de áudio."""
    input_name = data.get("input_name")
    mute_state = data.get("mute_state") 
    if input_name is None or mute_state is None: return

    try:
        execute_obs_command(lambda c: c.set_input_mute(input_name, mute_state), "Mute Audio")
        status_str = "MUTADO" if mute_state else "DESMUTADO"
        emit("obs_status", {"connected": True, "message": f"Áudio '{input_name}': {status_str}"}, namespace="/dashboard")
    except Exception as e:
        emit("obs_error", {"message": f"Erro ao mutar '{input_name}': {e}"}, namespace="/dashboard")

# --- 7. Lógica do Stream Deck (Soundboard/Hotkey) ---

@socketio.on("run_hotkey", namespace="/dashboard")
def run_hotkey(data):
    """Usa a biblioteca 'keyboard' para simulação de hotkey de baixo nível."""
    keys_str = data.get("keys_str", "") 
    if not keys_str:
        return
    try:
        print(f"Executando hotkey (com 'keyboard'): {keys_str}")
        keyboard.press_and_release(keys_str) 
    except Exception as e:
        print(f"Erro ao executar hotkey: {e}")
        emit("obs_error", {"message": f"Erro de Hotkey: {e}"}, namespace="/dashboard")

@socketio.on("play_sound", namespace="/dashboard")
def play_sound(data):
    filename = data.get("file") 
    if not filename: return
    if ".." in filename or "/" in filename or "\\" in filename:
        print(f"Tentativa de tocar som inválido: {filename}")
        return
    sound_path = os.path.join(SOUNDS_DIR, filename)
    if os.path.exists(sound_path):
        try:
            pygame.mixer.Sound(sound_path).play()
            print(f"Tocando som: {filename}")
        except Exception as e:
            print(f"Erro ao tocar som: {e}")
            emit("obs_error", {"message": f"Erro de Soundboard: {e}"}, namespace="/dashboard")
    else:
        print(f"Arquivo de som não encontrado: {sound_path}")
        emit("obs_error", {"message": f"Som não encontrado: {filename}"}, namespace="/dashboard")

# --- 8. Lógica do EventSub ---

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
        log_twitch_ratelimit(response) 
        response.raise_for_status()
        print(f"EventSub: Assinatura para '{event_type}' criada com sucesso.")
        return True
    except requests.exceptions.RequestException as e:
        try: error_details = e.response.json()
        except: error_details = str(e)
        print(f"Erro ao criar assinatura EventSub para '{event_type}': {error_details}")
        return False

def connect_eventsub_client(access_token, user_id):
    global eventsub_ws, eventsub_session_id
    try:
        eventsub_ws = websocket.create_connection(TWITCH_EVENTSUB_WSS)
        print("Conectado ao WebSocket do EventSub.")
        while True:
            response_str = eventsub_ws.recv()
            if not response_str: break
            message = json.loads(response_str)
            metadata = message.get("metadata", {})
            payload = message.get("payload", {})
            message_type = metadata.get("message_type")
            if message_type == "session_welcome":
                eventsub_session_id = payload["session"]["id"]
                print(f"EventSub: Sessão estabelecida. ID: {eventsub_session_id}")
                create_eventsub_subscription(access_token, user_id, eventsub_session_id, "channel.follow", version="2")
                create_eventsub_subscription(access_token, user_id, eventsub_session_id, "channel.subscribe")
                create_eventsub_subscription(access_token, user_id, eventsub_session_id, "channel.raid")
                create_eventsub_subscription(access_token, user_id, eventsub_session_id, "channel.channel_points_custom_reward_redemption.add")
            elif message_type == "notification":
                event = payload.get("event", {})
                event_type = payload.get("subscription", {}).get("type")
                feed_message = ""
                if event_type == "channel.follow":
                    feed_message = f"Novo Seguidor: {event.get('user_name')}"
                elif event_type == "channel.subscribe":
                    tier = event.get('tier', '1000').replace('000', 'k')
                    feed_message = f"Novo Inscrito (Tier {tier}): {event.get('user_name')}"
                elif event_type == "channel.raid":
                    viewers = event.get('viewers', 0)
                    feed_message = f"Raid de {event.get('from_broadcaster_user_name')} com {viewers}!"
                elif event_type == "channel.channel_points_custom_reward_redemption.add":
                    reward_title = event.get('reward', {}).get('title')
                    user_input = event.get('user_input', '')
                    feed_message = f"Resgate ({reward_title}): {event.get('user_name')} {user_input}"
                if feed_message:
                    print(f"EVENTSUB: Enviando notificação para o frontend: {feed_message}")
                    socketio.emit("eventsub_notification", {"message": feed_message, "type": event_type}, namespace="/dashboard")
            elif message_type == "session_keepalive": pass
            elif message_type == "ping": eventsub_ws.send(json.dumps({"type": "pong"}))
            elif message_type == "session_reconnect":
                print("EventSub: Solicitação de reconexão...")
                break
    except Exception as e:
        print(f"Erro fatal no WebSocket do EventSub: {e}")
    finally:
        if eventsub_ws: eventsub_ws.close()
        eventsub_ws = None
        eventsub_session_id = None
        print("Desconectado do EventSub.")
        global eventsub_thread
        eventsub_thread = None 
        print("EventSub: Tentando reconectar em 5 segundos...")
        socketio.sleep(5)

# --- 9. Lógica do VTube Studio (Thread-safe) ---

def vts_send_request(ws, message_type, data=None):
    payload = {
        "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
        "requestID": str(int(time.time() * 1000)), "messageType": message_type,
    }
    if data:
        payload["data"] = data
    ws.send(json.dumps(payload))

def vts_auth_flow(ws):
    global vts_token
    if os.path.exists(VTS_TOKEN_FILE):
        try:
            with open(VTS_TOKEN_FILE, 'r') as f:
                vts_token = json.load(f).get("authenticationToken")
                print("VTS: Token carregado do arquivo.")
        except Exception as e:
            print(f"VTS: Erro ao carregar token: {e}")
            vts_token = None
    if vts_token:
        print("VTS: Autenticando com token existente...")
        vts_send_request(ws, "AuthenticationRequest", {
            "pluginName": "FoxyDeck", "pluginDeveloper": "Foxy",
            "authenticationToken": vts_token
        })
    else:
        print("VTS: Solicitando novo token...")
        vts_send_request(ws, "AuthenticationTokenRequest", {
            "pluginName": "FoxyDeck", "pluginDeveloper": "Foxy",
            "pluginIcon": None
        })

def connect_vts_client():
    global vts_ws, vts_token, vts_hotkeys
    vts_url = f"ws://{VTS_HOST}:{VTS_PORT}"
    try:
        vts_ws = websocket.create_connection(vts_url)
        print(f"VTS: Conectado em {vts_url}.")
        vts_auth_flow(vts_ws)
        while True:
            try:
                response_str = vts_ws.recv()
                if not response_str: break
                message = json.loads(response_str)
                msg_type = message.get("messageType")
                data = message.get("data", {})
                if msg_type == "AuthenticationTokenResponse":
                    vts_token = data.get("authenticationToken")
                    with open(VTS_TOKEN_FILE, 'w') as f:
                        json.dump(data, f)
                    print("VTS: Novo token recebido e salvo. Autenticando...")
                    vts_auth_flow(vts_ws)
                elif msg_type == "AuthenticationResponse":
                    if data.get("authenticated"):
                        print("VTS: Autenticado com sucesso!")
                        socketio.emit("vts_status", {"connected": True, "message": "VTS Conectado"}, namespace="/dashboard")
                        print("VTS: Solicitando lista de hotkeys...")
                        vts_send_request(vts_ws, "HotkeysInCurrentModelRequest") 
                    else:
                        print("VTS: Falha na autenticação. Token inválido.")
                        vts_token = None
                        if os.path.exists(VTS_TOKEN_FILE):
                             os.remove(VTS_TOKEN_FILE)
                        vts_auth_flow(vts_ws)
                elif msg_type == "APIError" and data.get("errorID") == 1:
                     print("VTS: API não está pronta. Aguardando...")
                     socketio.emit("vts_status", {"connected": False, "message": "VTS: API não pronta..."}, namespace="/dashboard")
                     vts_token = None 
                     time.sleep(2)
                     vts_auth_flow(vts_ws)
                elif msg_type == "APIError" and data.get("errorID") == 100:
                    print("VTS: Por favor, clique em 'Permitir' dentro do VTube Studio.")
                    socketio.emit("vts_status", {"connected": False, "message": "VTS: Clique 'Permitir' no VTube Studio!"}, namespace="/dashboard")
                elif msg_type == "HotkeysInCurrentModelResponse": 
                    print("VTS: Lista de Hotkeys recebida.")
                    vts_hotkeys = data.get("availableHotkeys", [])
                    socketio.emit("vts_data_list", {"hotkeys": vts_hotkeys}, namespace="/dashboard")
                elif msg_type == "APIError":
                    print(f"VTS ERRO: ID={data.get('errorID')}, Mensagem={data.get('message')}")
            except websocket.WebSocketException as e:
                print(f"VTS: Erro no loop: {e}")
                break
    except Exception as e:
        print(f"VTS: Falha ao conectar: {e}")
    finally:
        if vts_ws: vts_ws.close()
        vts_ws = None
        print("VTS: Desconectado.")
        socketio.emit("vts_status", {"connected": False, "message": "VTS Desconectado"}, namespace="/dashboard")
        global vts_thread
        vts_thread = None 
        print("VTS: Tentando reconectar em 5 segundos...")
        socketio.sleep(5)

@socketio.on("get_vts_data", namespace="/dashboard")
def get_vts_data():
    """Envia a lista de hotkeys (do cache) para o frontend."""
    if vts_ws and vts_token:
        print("VTS: Frontend pediu atualização da lista de hotkeys...")
        vts_send_request(vts_ws, "HotkeysInCurrentModelRequest") 
    socketio.emit("vts_data_list", {"hotkeys": vts_hotkeys}, namespace="/dashboard")


# --- 10. Conexão Principal do SocketIO ---

@socketio.on("connect", namespace="/dashboard")
def on_socket_connect(auth=None):
    global obs_thread, eventsub_thread, vts_thread 
    if 'access_token' in session:
        if time.time() > session.get('expires_at', 0):
            if not refresh_access_token():
                print("Não foi possível conectar o socket, token inválido.")
                return
    
    if obs_thread is None: 
        if OBS_PASSWORD: 
            obs_thread = socketio.start_background_task(connect_obs_client)
        else:
            socketio.emit("obs_status", {"connected": False, "message": "OBS_PASSWORD não configurada no .env"}, namespace="/dashboard")
    elif obs_client:
         socketio.emit("obs_status", {"connected": True, "message": "Conectado ao OBS"}, namespace="/dashboard")
         get_obs_scene_details()

    if eventsub_thread is None: 
        if 'access_token' in session and 'user_id' in session:
            print("Iniciando tarefa de fundo do EventSub...")
            token = session['access_token']
            user_id = session['user_id']
            eventsub_thread = socketio.start_background_task(connect_eventsub_client, token, user_id)
            print("Tarefa de fundo do EventSub iniciada.")
        else:
            print("EventSub não iniciado: access_token ou user_id não encontrados.")
            
    if vts_thread is None: 
        print("Iniciando tarefa de fundo do VTS...")
        vts_thread = socketio.start_background_task(connect_vts_client)
        print("Tarefa de fundo do VTS iniciada.")
    elif vts_ws and vts_token:
        socketio.emit("vts_status", {"connected": True, "message": "VTS Conectado"}, namespace="/dashboard")
        get_vts_data()

# --- Execução (Simples, HTTP) ---

if __name__ == "__main__":
    if not all([app.config["SECRET_KEY"], CLIENT_ID, CLIENT_SECRET]):
        print("="*50)
        print("ERRO CRÍTICO: Variáveis de ambiente da Twitch não encontradas.")
        print("Verifique seu .env")
        print("="*50)
    elif not OBS_PASSWORD:
         print("="*50)
         print("AVISO: OBS_PASSWORD não definida no .env. Integração com OBS desativada.")
         print("="*50)
    
    print("="*50)
    print("Iniciando servidor em MODO PADRÃO (HTTP)")
    print("Acesse no seu PC: http://localhost:5000")
    print("Rode 'ngrok http 5000' em outro terminal para acessar de outros dispositivos.")
    print("="*50)
    
    socketio.run(
        app, 
        debug=True, 
        port=5000, 
        host='0.0.0.0'
    )