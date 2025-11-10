import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Configuración de Telegram API
    API_ID = int(os.getenv("API_ID", 12345678))
    API_HASH = os.getenv("API_HASH", "tu_api_hash_aqui")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "tu_bot_token_aqui")
    
    # Configuración de Administradores
    ADMINISTRADORES = [int(admin_id.strip()) for admin_id in os.getenv("ADMINISTRADORES", "123456789").split(",")]
    
    # Configuración de Comportamiento del Bot
    MAX_CONCURRENT_PROCESSES = int(os.getenv("MAX_CONCURRENT_PROCESSES", 3))
    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 300))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 300))
    
    # Configuración de Calidad por Defecto
    DEFAULT_QUALITY = {
        "resolution": os.getenv("DEFAULT_RESOLUTION", "1280x720"),
        "crf": os.getenv("DEFAULT_CRF", "23"),
        "audio_bitrate": os.getenv("DEFAULT_AUDIO_BITRATE", "128k"),
        "fps": os.getenv("DEFAULT_FPS", "30"),
        "preset": os.getenv("DEFAULT_PRESET", "medium"),
        "codec": os.getenv("DEFAULT_CODEC", "libx264")
    }
    
    # Rutas del Sistema
    TEMP_DIR = os.getenv("TEMP_DIR", "temp_files")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def validar_configuracion(cls):
        """Valida los valores críticos de configuración"""
        variables_requeridas = ["API_ID", "API_HASH", "BOT_TOKEN"]
        variables_faltantes = [var for var in variables_requeridas if not getattr(cls, var)]
        
        if variables_faltantes:
            raise ValueError(f"Faltan variables de entorno requeridas: {', '.join(variables_faltantes)}")
        
        if not cls.ADMINISTRADORES:
            raise ValueError("Debe especificar al menos un ID de administrador en ADMINISTRADORES")
        
        return True

# Instancia global de configuración
config = Config()
