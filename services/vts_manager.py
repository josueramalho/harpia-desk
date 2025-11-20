import websocket
import json
import threading
import time
import os
import logging

class VtsManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(VtsManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'): return
        self.host = "127.0.0.1"
        self.port = 8001
        self.token_file = "vts_token.json"
        
        self.ws = None
        self.token = None
        self.hotkeys = []
        self.is_connected = False
        self.callback = None
        self._keep_running = False
        self.thread = None
        
        self.logger = logging.getLogger("VtsManager")
        self.initialized = True

    def configure(self, host, port, token_file, callback=None):
        self.host = host
        self.port = port
        self.token_file = token_file
        self.callback = callback

    def start(self):
        """
        Inicia uma thread para tentar conexão. 
        Se a thread anterior já morreu (por falha de conexão), inicia uma nova.
        """
        if self.thread and self.thread.is_alive():
            return

        self._keep_running = True
        self.thread = threading.Thread(target=self._connection_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._keep_running = False
        if self.ws:
            try: self.ws.close()
            except: pass

    def trigger_hotkey(self, hotkey_id):
        if not self.is_connected or not hotkey_id:
            return
        self._send("HotkeyTriggerRequest", {"hotkeyID": hotkey_id})

    def request_hotkeys(self):
        if self.is_connected:
            self._send("HotkeysInCurrentModelRequest")

    def _notify(self, event_type, data):
        if self.callback:
            self.callback(event_type, data)

    def _connection_loop(self):
        """
        Tenta conectar UMA VEZ. Se conseguir, mantém escutando. 
        Se falhar ou cair, encerra.
        """
        url = f"ws://{self.host}:{self.port}"
        
        self.logger.info(f"Tentando conectar ao VTS em {url}...")
        
        try:
            self.ws = websocket.create_connection(url, timeout=2)
            self.is_connected = True
            self._notify("STATUS", {"connected": True, "message": "VTS Conectado"})
            
            # Inicia fluxo de autenticação
            self._auth_flow()
            
            # Loop de leitura (só roda enquanto estiver conectado)
            while self._keep_running:
                try:
                    message = self.ws.recv()
                    if not message: break
                    self._handle_message(message)
                except websocket.WebSocketTimeoutException:
                    continue 
                except Exception:
                    break # Sai do loop se houver erro de socket
                    
        except Exception as e:
            # Falha na conexão inicial ou erro crítico
            pass # Silencioso no console, UI mostrará desconectado

        # Limpeza ao sair
        self.is_connected = False
        self._notify("STATUS", {"connected": False, "message": "VTS Desconectado"})
        if self.ws:
            try: self.ws.close()
            except: pass
        self.ws = None
        self.logger.info("Thread VTS encerrada.")

    def _send(self, msg_type, data=None):
        if not self.ws: return
        payload = {
            "apiName": "FoxyDeck",
            "apiVersion": "1.0",
            "requestID": str(int(time.time()*1000)),
            "messageType": msg_type
        }
        if data: payload["data"] = data
        try:
            self.ws.send(json.dumps(payload))
        except:
            pass

    def _auth_flow(self):
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'r') as f:
                    data = json.load(f)
                    self.token = data.get("authenticationToken")
            except:
                self.token = None

        if self.token:
            self._send("AuthenticationRequest", {
                "pluginName": "FoxyDeck", "pluginDeveloper": "Foxy", "authenticationToken": self.token
            })
        else:
            self._send("AuthenticationTokenRequest", {
                "pluginName": "FoxyDeck", "pluginDeveloper": "Foxy"
            })

    def _handle_message(self, message_str):
        try:
            msg = json.loads(message_str)
            msg_type = msg.get("messageType")
            data = msg.get("data", {})

            if msg_type == "AuthenticationTokenResponse":
                self.token = data.get("authenticationToken")
                with open(self.token_file, 'w') as f: json.dump(data, f)
                self._auth_flow()

            elif msg_type == "AuthenticationResponse":
                if data.get("authenticated"):
                    self._notify("STATUS", {"connected": True, "message": "VTS Autenticado"})
                    self.request_hotkeys()
                else:
                    self.token = None
                    if os.path.exists(self.token_file): os.remove(self.token_file)
                    self._send("AuthenticationTokenRequest", { "pluginName": "FoxyDeck", "pluginDeveloper": "Foxy" })

            elif msg_type == "HotkeysInCurrentModelResponse":
                self.hotkeys = data.get("availableHotkeys", [])
                self._notify("HOTKEYS", {"hotkeys": self.hotkeys})

            elif msg_type == "APIError" and data.get("errorID") == 100:
                self._notify("STATUS", {"connected": False, "message": "Aceite a permissão no VTube Studio!"})
        except:
            pass

# Instância Global
vts_manager = VtsManager()