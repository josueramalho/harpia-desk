import obsws_python as obs
import logging
import threading

class ObsManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ObsManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'): return
        self.client = None
        self.host = "127.0.0.1"
        self.port = 4455
        self.password = None
        self.is_connected = False
        self.initialized = True
        self.logger = logging.getLogger("ObsManager")

    def configure(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password

    def connect(self):
        """
        Tenta estabelecer conexão com o OBS uma única vez.
        Não lança exceções no console, apenas retorna False se falhar.
        """
        if self.is_connected:
            try:
                self.client.get_version()
                return True
            except:
                self.is_connected = False
        
        try:
            self.client = obs.ReqClient(
                host=self.host, 
                port=self.port, 
                password=self.password, 
                timeout=1 # Timeout curto para não travar a UI
            )
            version = self.client.get_version()
            self.is_connected = True
            self.logger.info(f"Conectado ao OBS v{version.obs_version}")
            return True
        except Exception as e:
            # Log simplificado para evitar poluição visual
            error_msg = str(e)
            if "10061" in error_msg or "refused" in error_msg.lower():
                self.logger.warning("Não foi possível conectar ao OBS (Porta fechada ou app desligado).")
            else:
                self.logger.warning(f"Falha ao conectar OBS: {error_msg}")
            
            self.is_connected = False
            return False

    def execute(self, command_lambda):
        """
        Executa comando. Se falhar, marca como desconectado e NÃO tenta reconectar.
        """
        if not self.is_connected:
            return None

        try:
            return command_lambda(self.client)
        except Exception as e:
            self.logger.warning(f"Comando falhou. Marcando OBS como desconectado: {e}")
            self.is_connected = False
            return None

    def get_scene_details(self):
        def _logic(c):
            scenes = []
            scene_list = c.get_scene_list().scenes
            
            for s in scene_list:
                items = c.get_scene_item_list(s['sceneName']).scene_items
                sources = [{"name": i['sourceName'], "id": i['sceneItemId']} for i in items]
                scenes.append({"name": s['sceneName'], "sources": sources})
            
            inputs = c.get_input_list().inputs
            audio_inputs = [
                {"name": i['inputName']} 
                for i in inputs 
                if any(x in i.get('inputKind', '') for x in ['capture', 'audio', 'input'])
            ]
            
            return {"scenes": scenes, "audio_inputs": audio_inputs}

        return self.execute(_logic)

# Instância Global
obs_manager = ObsManager()