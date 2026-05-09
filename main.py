import os
import asyncio
import shutil
import json
import time
import math
import datetime
import subprocess
import re
import logging
import uuid
import mimetypes
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from collections import deque
import threading
import psutil

class Config:
    API_ID = 22788599 
    API_HASH = "6fd904cf42bbe1f6d57f22d8d392e9b4"
    BOT_TOKEN = "8230649001:AAEpb7ZdkKV9zFo1X3Wojem9g_UOKMv_-UA"
    ADMINISTRADORES = [7400531692]
    MAX_CONCURRENT_PROCESSES = 10
    MAX_FILE_SIZE_MB = 300
    REQUEST_TIMEOUT = 300
    DEFAULT_QUALITY = {
        "resolution": "360x240",
        "crf": "34",
        "audio_bitrate": "60k",
        "fps": "16",
        "preset": "ultrafast",
        "codec": "libx265"
    }
    TEMP_DIR = "temp_files"
    LOG_LEVEL = "INFO"
    DB_FILE = "bot_database.json"

    @classmethod
    def validar_configuracion(cls):
        variables_requeridas = ["API_ID", "API_HASH", "BOT_TOKEN"]
        variables_faltantes = [var for var in variables_requeridas if not getattr(cls, var)]
        
        if variables_faltantes:
            raise ValueError(f"Faltan variables requeridas: {', '.join(variables_faltantes)}")
        
        return True

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

estado_broadcast = {}
estado_importacion_db = {}

class DatabaseManager:
    def __init__(self, archivo_db=Config.DB_FILE):
        self.archivo_db = archivo_db
        self.datos = {
            "usuarios": {},
            "videos_convertidos": [],
            "configuracion_sistema": {},
            "administradores": [],
            "next_ids": {
                "videos": 1,
                "admins": 1
            }
        }
        self.inicializar_base_datos()
    
    def guardar_datos(self):
        try:
            with open(self.archivo_db, 'w', encoding='utf-8') as f:
                json.dump(self.datos, f, ensure_ascii=False, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"Error guardando datos: {e}")
            return False
    
    def cargar_datos(self):
        try:
            if os.path.exists(self.archivo_db):
                with open(self.archivo_db, 'r', encoding='utf-8') as f:
                    self.datos = json.load(f)
                return True
            return False
        except Exception as e:
            logger.error(f"Error cargando datos: {e}")
            return False
    
    def inicializar_base_datos(self):
        try:
            if not self.cargar_datos():
                self.datos["configuracion_sistema"] = {
                    'limite_peso_mb': {'valor': str(Config.MAX_FILE_SIZE_MB), 'descripcion': 'Límite máximo de tamaño de archivo en MB'},
                    'max_concurrente': {'valor': str(Config.MAX_CONCURRENT_PROCESSES), 'descripcion': 'Máximo de procesos concurrentes'},
                    'calidad_default': {'valor': json.dumps(Config.DEFAULT_QUALITY), 'descripcion': 'Configuración de calidad por defecto'},
                    'mantenimiento': {'valor': 'false', 'descripcion': 'Modo mantenimiento del bot'},
                    'modo_soporte': {'valor': 'false', 'descripcion': 'Modo soporte activado'}
                }
                
                for admin_id in Config.ADMINISTRADORES:
                    self.agregar_administrador(admin_id, None, "Admin", 0)
                
                self.guardar_datos()
                logger.info("Base de datos JSON inicializada")
            
            self.cargar_configuracion_desde_db()
            
        except Exception as e:
            logger.error(f"Error inicializando base de datos: {e}")
            raise
    
    def cargar_configuracion_desde_db(self):
        try:
            config = self.datos.get("configuracion_sistema", {})
            
            if 'limite_peso_mb' in config:
                Config.MAX_FILE_SIZE_MB = int(config['limite_peso_mb']['valor'])
            
            if 'calidad_default' in config:
                Config.DEFAULT_QUALITY = json.loads(config['calidad_default']['valor'])
            
            admins = self.obtener_administradores()
            Config.ADMINISTRADORES = [admin['user_id'] for admin in admins]
            
            logger.info("Configuración cargada desde JSON")
            
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
    
    def agregar_actualizar_usuario(self, datos_usuario):
        try:
            user_id = str(datos_usuario['user_id'])
            fecha_actual = datetime.datetime.now().isoformat()
            
            if user_id in self.datos["usuarios"]:
                usuario = self.datos["usuarios"][user_id]
                usuario.update({
                    'username': datos_usuario.get('username'),
                    'first_name': datos_usuario.get('first_name'),
                    'last_name': datos_usuario.get('last_name'),
                    'language_code': datos_usuario.get('language_code'),
                    'fecha_ultimo_uso': fecha_actual
                })
            else:
                self.datos["usuarios"][user_id] = {
                    'user_id': datos_usuario['user_id'],
                    'username': datos_usuario.get('username'),
                    'first_name': datos_usuario.get('first_name'),
                    'last_name': datos_usuario.get('last_name'),
                    'language_code': datos_usuario.get('language_code'),
                    'fecha_registro': fecha_actual,
                    'fecha_ultimo_uso': fecha_actual,
                    'total_conversiones': 0,
                    'es_activo': True,
                    'esta_baneado': False,
                    'configuracion_personalizada': None
                }
            
            return self.guardar_datos()
        except Exception as e:
            logger.error(f"Error agregando usuario: {e}")
            return False
    
    def incrementar_conversion_usuario(self, user_id):
        try:
            user_id_str = str(user_id)
            if user_id_str in self.datos["usuarios"]:
                usuario = self.datos["usuarios"][user_id_str]
                usuario['total_conversiones'] = usuario.get('total_conversiones', 0) + 1
                usuario['fecha_ultimo_uso'] = datetime.datetime.now().isoformat()
                return self.guardar_datos()
            return False
        except Exception as e:
            logger.error(f"Error incrementando conversiones: {e}")
            return False
    
    def obtener_usuario(self, user_id):
        try:
            user_id_str = str(user_id)
            if user_id_str in self.datos["usuarios"]:
                return self.datos["usuarios"][user_id_str]
            return None
        except Exception as e:
            logger.error(f"Error obteniendo usuario: {e}")
            return None
    
    def banear_usuario(self, user_id, admin_id):
        try:
            user_id_str = str(user_id)
            if user_id_str in self.datos["usuarios"]:
                self.datos["usuarios"][user_id_str]['esta_baneado'] = True
                return self.guardar_datos()
            return False
        except Exception as e:
            logger.error(f"Error baneando usuario: {e}")
            return False
    
    def desbanear_usuario(self, user_id):
        try:
            user_id_str = str(user_id)
            if user_id_str in self.datos["usuarios"]:
                self.datos["usuarios"][user_id_str]['esta_baneado'] = False
                return self.guardar_datos()
            return False
        except Exception as e:
            logger.error(f"Error desbaneando usuario: {e}")
            return False
    
    def usuario_esta_baneado(self, user_id):
        try:
            user_id_str = str(user_id)
            if user_id_str in self.datos["usuarios"]:
                return self.datos["usuarios"][user_id_str].get('esta_baneado', False)
            return False
        except Exception as e:
            logger.error(f"Error verificando ban: {e}")
            return False
    
    def agregar_administrador(self, user_id, username, first_name, agregado_por):
        try:
            for admin in self.datos["administradores"]:
                if admin['user_id'] == user_id:
                    admin.update({
                        'username': username,
                        'first_name': first_name,
                        'fecha_agregado': datetime.datetime.now().isoformat(),
                        'agregado_por': agregado_por
                    })
                    self.guardar_datos()
                    
                    if user_id not in Config.ADMINISTRADORES:
                        Config.ADMINISTRADORES.append(user_id)
                    
                    return True
            
            nuevo_admin = {
                'id': self.datos["next_ids"]["admins"],
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'fecha_agregado': datetime.datetime.now().isoformat(),
                'agregado_por': agregado_por
            }
            
            self.datos["administradores"].append(nuevo_admin)
            self.datos["next_ids"]["admins"] += 1
            self.guardar_datos()
            
            if user_id not in Config.ADMINISTRADORES:
                Config.ADMINISTRADORES.append(user_id)
            
            return True
        except Exception as e:
            logger.error(f"Error agregando administrador: {e}")
            return False
    
    def eliminar_administrador(self, user_id):
        try:
            nuevos_admins = []
            eliminado = False
            
            for admin in self.datos["administradores"]:
                if admin['user_id'] != user_id:
                    nuevos_admins.append(admin)
                else:
                    eliminado = True
            
            self.datos["administradores"] = nuevos_admins
            self.guardar_datos()
            
            if user_id in Config.ADMINISTRADORES:
                Config.ADMINISTRADORES.remove(user_id)
            
            return eliminado
        except Exception as e:
            logger.error(f"Error eliminando administrador: {e}")
            return False
    
    def obtener_administradores(self):
        try:
            return self.datos["administradores"]
        except Exception as e:
            logger.error(f"Error obteniendo administradores: {e}")
            return []
    
    def es_administrador(self, user_id):
        try:
            for admin in self.datos["administradores"]:
                if admin['user_id'] == user_id:
                    return True
            return False
        except Exception as e:
            logger.error(f"Error verificando administrador: {e}")
            return user_id in Config.ADMINISTRADORES
    
    def obtener_todos_usuarios(self):
        try:
            usuarios = []
            for user_id, usuario in self.datos["usuarios"].items():
                usuarios.append({
                    'user_id': usuario['user_id'],
                    'username': usuario.get('username'),
                    'first_name': usuario.get('first_name'),
                    'fecha_registro': usuario.get('fecha_registro'),
                    'esta_baneado': usuario.get('esta_baneado', False)
                })
            return usuarios
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {e}")
            return []
    
    def obtener_usuarios_baneados(self):
        try:
            baneados = []
            for user_id, usuario in self.datos["usuarios"].items():
                if usuario.get('esta_baneado', False):
                    baneados.append({
                        'user_id': usuario['user_id'],
                        'username': usuario.get('username'),
                        'first_name': usuario.get('first_name'),
                        'fecha_registro': usuario.get('fecha_registro')
                    })
            return baneados
        except Exception as e:
            logger.error(f"Error obteniendo usuarios baneados: {e}")
            return []
    
    def actualizar_configuracion_usuario(self, user_id, configuracion):
        try:
            user_id_str = str(user_id)
            if user_id_str in self.datos["usuarios"]:
                self.datos["usuarios"][user_id_str]['configuracion_personalizada'] = json.dumps(configuracion)
                return self.guardar_datos()
            return False
        except Exception as e:
            logger.error(f"Error actualizando configuración usuario: {e}")
            return False
    
    def obtener_configuracion_usuario(self, user_id):
        try:
            user_id_str = str(user_id)
            if user_id_str in self.datos["usuarios"]:
                config = self.datos["usuarios"][user_id_str].get('configuracion_personalizada')
                if config:
                    return json.loads(config)
            return None
        except Exception as e:
            logger.error(f"Error obteniendo configuración usuario: {e}")
            return None
    
    def agregar_video_convertido(self, datos_video):
        try:
            nuevo_video = {
                'id': self.datos["next_ids"]["videos"],
                'user_id': datos_video['user_id'],
                'nombre_archivo': datos_video['nombre_archivo'],
                'tamano_original': datos_video['tamano_original'],
                'tamano_convertido': datos_video['tamano_convertido'],
                'duracion_original': datos_video.get('duracion_original', ''),
                'duracion_convertido': datos_video.get('duracion_convertido', ''),
                'calidad_config': datos_video.get('calidad_config', ''),
                'tiempo_procesamiento': datos_video.get('tiempo_procesamiento', 0),
                'fecha_conversion': datetime.datetime.now().isoformat(),
                'estado': 'completado',
                'mensaje_error': ''
            }
            
            self.datos["videos_convertidos"].append(nuevo_video)
            self.datos["next_ids"]["videos"] += 1
            
            self.incrementar_conversion_usuario(datos_video['user_id'])
            
            self.guardar_datos()
            return nuevo_video['id']
        except Exception as e:
            logger.error(f"Error agregando video: {e}")
            return None
    
    def eliminar_videos_antiguos(self, dias=7):
        try:
            fecha_limite = datetime.datetime.now() - datetime.timedelta(days=dias)
            videos_nuevos = []
            eliminados = 0
            
            for video in self.datos["videos_convertidos"]:
                fecha_video = datetime.datetime.fromisoformat(video['fecha_conversion'])
                if fecha_video >= fecha_limite:
                    videos_nuevos.append(video)
                else:
                    eliminados += 1
            
            self.datos["videos_convertidos"] = videos_nuevos
            self.guardar_datos()
            
            if eliminados > 0:
                logger.info(f"Eliminados {eliminados} registros de videos antiguos")
            
            return eliminados
        except Exception as e:
            logger.error(f"Error eliminando videos antiguos: {e}")
            return 0
    
    def obtener_historial_usuario(self, user_id, limite=10):
        try:
            historial = []
            for video in self.datos["videos_convertidos"]:
                if video['user_id'] == user_id:
                    historial.append(video)
            
            historial.sort(key=lambda x: x['fecha_conversion'], reverse=True)
            return historial[:limite]
        except Exception as e:
            logger.error(f"Error obteniendo historial: {e}")
            return []
    
    def obtener_estadisticas_generales(self):
        try:
            total_usuarios = len(self.datos["usuarios"])
            total_videos = len(self.datos["videos_convertidos"])
            
            espacio_ahorrado = 0
            for video in self.datos["videos_convertidos"]:
                if video['tamano_original'] > video['tamano_convertido']:
                    espacio_ahorrado += (video['tamano_original'] - video['tamano_convertido'])
            
            tiempo_total = sum(video['tiempo_procesamiento'] for video in self.datos["videos_convertidos"])
            
            total_baneados = sum(1 for usuario in self.datos["usuarios"].values() if usuario.get('esta_baneado', False))
            
            total_administradores = len(self.datos["administradores"])
            
            return {
                "total_usuarios": total_usuarios,
                "total_videos": total_videos,
                "espacio_ahorrado": espacio_ahorrado,
                "tiempo_total_procesamiento": tiempo_total,
                "total_baneados": total_baneados,
                "total_administradores": total_administradores
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {}
    
    def obtener_configuracion(self, clave):
        try:
            config = self.datos.get("configuracion_sistema", {}).get(clave)
            if config:
                return config['valor']
            return None
        except Exception as e:
            logger.error(f"Error obteniendo configuración: {e}")
            return None
    
    def actualizar_configuracion(self, clave, valor):
        try:
            if clave not in self.datos["configuracion_sistema"]:
                self.datos["configuracion_sistema"][clave] = {
                    'valor': valor,
                    'descripcion': '',
                    'fecha_actualizacion': datetime.datetime.now().isoformat()
                }
            else:
                self.datos["configuracion_sistema"][clave]['valor'] = valor
                self.datos["configuracion_sistema"][clave]['fecha_actualizacion'] = datetime.datetime.now().isoformat()
            
            if clave == 'limite_peso_mb':
                Config.MAX_FILE_SIZE_MB = int(valor)
            elif clave == 'calidad_default':
                Config.DEFAULT_QUALITY = json.loads(valor)
            
            self.guardar_datos()
            logger.info(f"Configuración actualizada: {clave} = {valor}")
            return True
        except Exception as e:
            logger.error(f"Error actualizando configuración: {e}")
            return False
    
    def normalizar_estructura_datos(self, datos):
        """Garantiza que un JSON importado tenga las claves mínimas usadas por el bot."""
        estructura_base = {
            "usuarios": {},
            "videos_convertidos": [],
            "configuracion_sistema": {},
            "administradores": [],
            "next_ids": {"videos": 1, "admins": 1}
        }

        if not isinstance(datos, dict):
            raise ValueError("El archivo no contiene un objeto JSON válido")

        for clave, valor_defecto in estructura_base.items():
            if clave not in datos or datos[clave] is None:
                datos[clave] = valor_defecto

        if not isinstance(datos.get("usuarios"), dict):
            raise ValueError("La clave 'usuarios' debe ser un objeto")
        if not isinstance(datos.get("videos_convertidos"), list):
            raise ValueError("La clave 'videos_convertidos' debe ser una lista")
        if not isinstance(datos.get("configuracion_sistema"), dict):
            raise ValueError("La clave 'configuracion_sistema' debe ser un objeto")
        if not isinstance(datos.get("administradores"), list):
            raise ValueError("La clave 'administradores' debe ser una lista")

        datos["next_ids"].setdefault("videos", 1)
        datos["next_ids"].setdefault("admins", 1)

        if datos["videos_convertidos"]:
            max_video_id = max([v.get("id", 0) for v in datos["videos_convertidos"] if isinstance(v, dict)] or [0])
            datos["next_ids"]["videos"] = max(int(datos["next_ids"].get("videos", 1)), max_video_id + 1)

        if datos["administradores"]:
            max_admin_id = max([a.get("id", 0) for a in datos["administradores"] if isinstance(a, dict)] or [0])
            datos["next_ids"]["admins"] = max(int(datos["next_ids"].get("admins", 1)), max_admin_id + 1)

        return datos

    def exportar_base_datos(self, ruta_exportacion=None):
        try:
            self.guardar_datos()
            if ruta_exportacion is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                ruta_exportacion = f"bot_database_export_{timestamp}.json"
            shutil.copy2(self.archivo_db, ruta_exportacion)
            return ruta_exportacion
        except Exception as e:
            logger.error(f"Error exportando base de datos: {e}")
            return None

    def importar_base_datos(self, ruta_archivo, admin_id=None, hacer_backup=True):
        try:
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                datos_importados = json.load(f)

            datos_importados = self.normalizar_estructura_datos(datos_importados)
            ruta_backup = None

            if hacer_backup and os.path.exists(self.archivo_db):
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                ruta_backup = f"{self.archivo_db}.backup_{timestamp}"
                shutil.copy2(self.archivo_db, ruta_backup)

            self.datos = datos_importados

            if admin_id is not None and not self.es_administrador(admin_id):
                self.datos["administradores"].append({
                    'id': self.datos["next_ids"].get("admins", 1),
                    'user_id': admin_id,
                    'username': None,
                    'first_name': 'Admin importador',
                    'fecha_agregado': datetime.datetime.now().isoformat(),
                    'agregado_por': admin_id
                })
                self.datos["next_ids"]["admins"] = self.datos["next_ids"].get("admins", 1) + 1

            if not self.guardar_datos():
                raise ValueError("No se pudo guardar la base de datos importada")

            self.cargar_configuracion_desde_db()
            return True, ruta_backup
        except Exception as e:
            logger.error(f"Error importando base de datos: {e}")
            return False, str(e)

    def obtener_videos_por_usuario(self, user_id=None, limite=50, offset=0):
        try:
            videos_filtrados = []
            
            if user_id:
                for video in self.datos["videos_convertidos"]:
                    if video['user_id'] == user_id:
                        videos_filtrados.append(video)
            else:
                videos_filtrados = self.datos["videos_convertidos"]
            
            videos_filtrados.sort(key=lambda x: x['fecha_conversion'], reverse=True)
            
            return videos_filtrados[offset:offset + limite]
        except Exception as e:
            logger.error(f"Error obteniendo videos por usuario: {e}")
            return []
    
    def contar_videos_por_usuario(self, user_id=None):
        try:
            if user_id:
                return sum(1 for video in self.datos["videos_convertidos"] if video['user_id'] == user_id)
            else:
                return len(self.datos["videos_convertidos"])
        except Exception as e:
            logger.error(f"Error contando videos: {e}")
            return 0

db = DatabaseManager()

class SistemaColas:
    def __init__(self, max_concurrente=10):
        self.cola_espera = deque()
        self.procesos_activos = {}
        self.max_concurrente = max_concurrente
        self.lock = threading.Lock()
        self.procesos_por_usuario = {}
        self.cancelaciones_solicitadas = set()
        self.estadisticas = {
            "procesos_completados": 0,
            "errores": 0,
            "total_tiempo": 0,
            "inicio_sistema": time.time()
        }
        
    def agregar_trabajo(self, user_id, trabajo):
        with self.lock:
            if not es_administrador(user_id) and user_id in self.procesos_por_usuario:
                return "usuario_ocupado"
                
            if len(self.procesos_activos) < self.max_concurrente:
                self.procesos_activos[user_id] = trabajo
                if not es_administrador(user_id):
                    self.procesos_por_usuario[user_id] = True
                return "procesando"
            else:
                self.cola_espera.append((user_id, trabajo))
                posicion = len(self.cola_espera)
                return f"encolado_{posicion}"
    
    def trabajo_completado(self, user_id, exito=True, tiempo=0):
        with self.lock:
            if user_id in self.procesos_activos:
                del self.procesos_activos[user_id]
            if not es_administrador(user_id) and user_id in self.procesos_por_usuario:
                del self.procesos_por_usuario[user_id]
            
            if exito:
                self.estadisticas["procesos_completados"] += 1
            else:
                self.estadisticas["errores"] += 1
            self.estadisticas["total_tiempo"] += tiempo
            
            if self.cola_espera and len(self.procesos_activos) < self.max_concurrente:
                siguiente_user_id, siguiente_trabajo = self.cola_espera.popleft()
                self.procesos_activos[siguiente_user_id] = siguiente_trabajo
                if not es_administrador(siguiente_user_id):
                    self.procesos_por_usuario[siguiente_user_id] = True
                return siguiente_user_id, siguiente_trabajo
        return None, None
    
    def obtener_estado(self, user_id):
        with self.lock:
            if user_id in self.procesos_activos:
                return "procesando"
            
            for i, (uid, _) in enumerate(self.cola_espera):
                if uid == user_id:
                    return f"encolado_{i + 1}"
            
            return "no_encontrado"
    
    def solicitar_cancelacion(self, user_id):
        with self.lock:
            if user_id in self.procesos_activos:
                self.cancelaciones_solicitadas.add(user_id)
                return "procesando", self.procesos_activos[user_id]

            for indice, (uid, trabajo) in enumerate(list(self.cola_espera)):
                if uid == user_id:
                    del self.cola_espera[indice]
                    if not es_administrador(user_id) and user_id in self.procesos_por_usuario:
                        del self.procesos_por_usuario[user_id]
                    self.estadisticas["errores"] += 1
                    return "encolado", trabajo

            return "no_encontrado", None

    def esta_cancelado(self, user_id):
        with self.lock:
            return user_id in self.cancelaciones_solicitadas

    def limpiar_cancelacion(self, user_id):
        with self.lock:
            self.cancelaciones_solicitadas.discard(user_id)

    def obtener_estadisticas(self):
        with self.lock:
            tiempo_promedio = (
                self.estadisticas["total_tiempo"] / self.estadisticas["procesos_completados"] 
                if self.estadisticas["procesos_completados"] > 0 else 0
            )
            uptime = time.time() - self.estadisticas["inicio_sistema"]
            
            return {
                "procesando": len(self.procesos_activos),
                "en_espera": len(self.cola_espera),
                "max_concurrente": self.max_concurrente,
                "completados": self.estadisticas["procesos_completados"],
                "errores": self.estadisticas["errores"],
                "tiempo_promedio": tiempo_promedio,
                "uptime": uptime
            }

sistema_colas = SistemaColas(max_concurrente=Config.MAX_CONCURRENT_PROCESSES)
app = Client("video_converter_bot", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN)

def obtener_duracion_video(ruta_video):
    try:
        resultado = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                ruta_video
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        return float(resultado.stdout.strip())
    except Exception as e:
        logger.error(f"Error al obtener duración: {e}")
        return 0

def formatear_tiempo(segundos):
    if segundos < 0:
        return "00:00"
    
    horas, resto = divmod(int(segundos), 3600)
    minutos, segundos = divmod(resto, 60)
    
    if horas > 0:
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"
    else:
        return f"{minutos:02d}:{segundos:02d}"

def obtener_duracion_formateada(ruta_video):
    try:
        duracion_segundos = obtener_duracion_video(ruta_video)
        return formatear_tiempo(duracion_segundos)
    except Exception:
        return "Desconocida"

def formatear_tamano(tamano_bytes):
    if tamano_bytes == 0:
        return "0 B"
    tamanos = ["B", "KB", "MB", "GB"]
    i = int(math.floor(math.log(tamano_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(tamano_bytes / p, 2)
    return f"{s} {tamanos[i]}"

def calcular_reduccion(tamano_original, tamano_convertido):
    if tamano_original == 0:
        return "0%"
    reduccion = ((tamano_original - tamano_convertido) / tamano_original) * 100
    if reduccion > 0:
        return f"Reducción: {reduccion:.1f}%"
    elif reduccion < 0:
        return f"Aumento: {abs(reduccion):.1f}%"
    else:
        return "Sin cambios en tamaño"

def es_administrador(user_id):
    return db.es_administrador(user_id)

def obtener_nombre_archivo_mensaje(mensaje: Message):
    if getattr(mensaje, "video", None):
        return mensaje.video.file_name or "video.mp4"
    if getattr(mensaje, "document", None):
        return mensaje.document.file_name or "video"
    return "video"


def obtener_extension_video(mensaje: Message):
    nombre = obtener_nombre_archivo_mensaje(mensaje)
    extension = os.path.splitext(nombre)[1].lower()
    extensiones_validas = {
        '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
        '.mpg', '.mpeg', '.3gp', '.3gpp', '.ts', '.mts', '.m2ts', '.ogv', '.vob'
    }

    if extension in extensiones_validas:
        return extension

    mime_type = ""
    if getattr(mensaje, "document", None):
        mime_type = (mensaje.document.mime_type or "").lower()
    elif getattr(mensaje, "video", None):
        mime_type = (getattr(mensaje.video, "mime_type", None) or "video/mp4").lower()

    extension_por_mime = mimetypes.guess_extension(mime_type) if mime_type else None
    if extension_por_mime in extensiones_validas:
        return extension_por_mime

    return ".mp4"


def teclado_cancelar_conversion():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_conversion")]
    ])


async def descargar_video_seguro(mensaje: Message, user_id: int):
    """Descarga usando un nombre propio para evitar fallos con caracteres especiales o rutas largas."""
    os.makedirs(Config.TEMP_DIR, exist_ok=True)
    extension = obtener_extension_video(mensaje)
    ruta_destino = os.path.join(Config.TEMP_DIR, f"video_{user_id}_{int(time.time())}_{uuid.uuid4().hex}{extension}")

    try:
        ruta_descargada = await mensaje.download(file_name=ruta_destino)
        if not ruta_descargada or not os.path.exists(ruta_descargada):
            raise FileNotFoundError(f"No se pudo completar la descarga del archivo: {ruta_destino}")
        return ruta_descargada
    except Exception:
        for ruta in (ruta_destino, f"{ruta_destino}.temp"):
            if os.path.exists(ruta):
                try:
                    os.remove(ruta)
                except Exception:
                    pass
        raise


def limpiar_archivos_trabajo(trabajo):
    for clave in ("ruta_video", "ruta_convertido"):
        ruta = trabajo.get(clave) if trabajo else None
        if ruta and os.path.exists(ruta):
            try:
                os.remove(ruta)
                logger.info(f"Archivo temporal eliminado tras cancelación: {ruta}")
            except Exception as e:
                logger.error(f"Error eliminando archivo temporal cancelado {ruta}: {e}")

def generar_thumbnail(ruta_video, ruta_salida, tiempo='00:00:05'):
    try:
        duracion = obtener_duracion_video(ruta_video)
        if duracion <= 0:
            logger.error("No se pudo obtener la duración del video.")
            return False

        ss = min(1, duracion / 2)

        comando = [
            "ffmpeg",
            "-ss", str(ss),
            "-i", ruta_video,
            "-vframes", "1",
            "-q:v", "2",
            "-vf", "scale=320:240",
            ruta_salida,
            "-y"
        ]
        
        subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return os.path.exists(ruta_salida)
    except Exception as e:
        logger.error(f"Error generando thumbnail: {e}")
        return False

def crear_barra_progreso(porcentaje, longitud=20):
    bloques_llenos = int(porcentaje * longitud / 100)
    bloques_vacios = longitud - bloques_llenos
    return "█" * bloques_llenos + "░" * bloques_vacios

def extraer_error_ffmpeg(salida_error):
    lineas = salida_error.split('\n')
    for linea in reversed(lineas):
        linea = linea.strip()
        if linea and not linea.startswith('ffmpeg version') and not linea.startswith('built with') and not linea.startswith('configuration:'):
            if 'Error' in linea or 'error' in linea.lower() or 'failed' in linea.lower():
                return linea
    return '\n'.join(lineas[-3:]) if len(lineas) > 3 else salida_error

def parsear_tiempo_ffmpeg(cadena_tiempo):
    try:
        partes = cadena_tiempo.split(':')
        if len(partes) == 3:
            horas = int(partes[0])
            minutos = int(partes[1])
            segundos = float(partes[2])
            return horas * 3600 + minutos * 60 + segundos
        elif len(partes) == 2:
            minutos = int(partes[0])
            segundos = float(partes[1])
            return minutos * 60 + segundos
        else:
            return float(cadena_tiempo)
    except:
        return 0

def modo_soporte_activo():
    modo = db.obtener_configuracion('modo_soporte')
    return modo and modo.lower() == 'true'

async def convertir_video_con_progreso(ruta_entrada, ruta_salida, duracion_total, actualizar_progreso, config_calidad=None, debe_cancelar=None):
    try:
        if not shutil.which("ffmpeg"):
            return False, "FFmpeg no disponible"
        
        if config_calidad is None:
            config_calidad = Config.DEFAULT_QUALITY
        
        resolucion = config_calidad.get("resolution", Config.DEFAULT_QUALITY.get("resolution", "360x240"))
        if "x" in resolucion:
            ancho, alto = resolucion.lower().split("x", 1)
            filtro_video = (
                f"scale={ancho}:{alto}:force_original_aspect_ratio=decrease,"
                f"pad={ancho}:{alto}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
            )
        else:
            filtro_video = "format=yuv420p"

        comando = [
            'ffmpeg',
            '-hide_banner',
            '-fflags', '+genpts',
            '-err_detect', 'ignore_err',
            '-i', ruta_entrada,
            '-map', '0:v:0',
            '-map', '0:a?',
            '-sn',
            '-dn',
            '-vf', filtro_video,
            '-c:v', config_calidad["codec"],
            '-preset', config_calidad["preset"],
            '-crf', config_calidad["crf"],
            '-r', config_calidad["fps"],
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', config_calidad["audio_bitrate"],
            '-movflags', '+faststart',
            '-threads', '0',
            '-max_muxing_queue_size', '2048',
            '-y',
            ruta_salida
        ]
        
        proceso = await asyncio.create_subprocess_exec(
            *comando,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        buffer_error = ""
        ultima_actualizacion = 0
        
        while True:
            if debe_cancelar and debe_cancelar():
                proceso.terminate()
                try:
                    await asyncio.wait_for(proceso.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proceso.kill()
                    await proceso.wait()
                return False, "cancelado"

            try:
                chunk = await asyncio.wait_for(proceso.stderr.read(1024), timeout=1)
            except asyncio.TimeoutError:
                continue

            if not chunk:
                break
                
            linea = chunk.decode('utf-8', errors='ignore')
            buffer_error += linea
            
            if 'time=' in linea:
                match = re.search(r'time=(\d+:\d+:\d+\.\d+)', linea)
                if match and duracion_total > 0:
                    tiempo_actual_str = match.group(1)
                    tiempo_actual = parsear_tiempo_ffmpeg(tiempo_actual_str)
                    
                    porcentaje = min(95, (tiempo_actual / duracion_total) * 100)
                    
                    ahora = time.time()
                    if ahora - ultima_actualizacion > 2:
                        await actualizar_progreso(porcentaje, formatear_tiempo(tiempo_actual))
                        ultima_actualizacion = ahora
        
        await proceso.wait()
        
        if debe_cancelar and debe_cancelar():
            if os.path.exists(ruta_salida):
                try:
                    os.remove(ruta_salida)
                except Exception:
                    pass
            return False, "cancelado"

        if proceso.returncode == 0 and os.path.exists(ruta_salida) and os.path.getsize(ruta_salida) > 0:
            return True, "Conversión completada exitosamente"
        else:
            error_real = extraer_error_ffmpeg(buffer_error)
            return False, f"Error en FFmpeg: {error_real}"
            
    except asyncio.TimeoutError:
        return False, "Tiempo de conversión excedido"
    except Exception as e:
        return False, f"Error del sistema: {str(e)}"

async def procesar_video(cliente, mensaje, ruta_video, ruta_convertido, user_id, mensaje_estado):
    tiempo_inicio = time.time()
    ruta_thumbnail = None
    
    config_usuario = db.obtener_configuracion_usuario(user_id)
    config_calidad = config_usuario if config_usuario else Config.DEFAULT_QUALITY
    
    async def actualizar_progreso(porcentaje, tiempo_actual=""):
        nonlocal mensaje_estado
        try:
            estadisticas = sistema_colas.obtener_estadisticas()
            barra = crear_barra_progreso(porcentaje)
            texto_progreso = (
                "**Procesamiento Inmediato**\n\n"
                f"Tu video ha comenzado a procesarse.\n"
                f"**Procesos activos:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
                f"**En espera:** `{estadisticas['en_espera']}`\n\n"
                f"**Convirtiendo Video**\n\n"
                f"**Progreso:** {porcentaje:.1f}%\n"
                f"`{barra}`\n"
                f"**Tiempo transcurrido:** `{tiempo_actual}`\n\n"
                f"Por favor espera, el proceso está en marcha..."
            )
            if mensaje_estado:
                await mensaje_estado.edit_text(texto_progreso, reply_markup=teclado_cancelar_conversion())
        except Exception as e:
            logger.error(f"Error actualizando progreso: {e}")
    
    try:
        tamano_original = os.path.getsize(ruta_video)
        nombre_original = obtener_nombre_archivo_mensaje(mensaje)
        duracion_total = obtener_duracion_video(ruta_video)
        
        estadisticas = sistema_colas.obtener_estadisticas()
        
        texto_inicial = (
            "**Procesamiento Inmediato**\n\n"
            f"Tu video ha comenzado a procesarse.\n"
            f"**Procesos activos:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
            f"**En espera:** `{estadisticas['en_espera']}`\n\n"
            "Recibirás el resultado pronto.\n\n"
            "**Convirtiendo Video**\n\n"
            "**Progreso:** 0%\n"
            "`░░░░░░░░░░░░░░░░░░░░`\n"
            "**Tiempo transcurrido:** `00:00`\n\n"
            "Preparando el video para conversión..."
        )
        
        if not mensaje_estado:
            mensaje_estado = await mensaje.reply_text(texto_inicial, reply_markup=teclado_cancelar_conversion())
        else:
            await mensaje_estado.edit_text(texto_inicial, reply_markup=teclado_cancelar_conversion())
        
        await actualizar_progreso(5, "00:00:00")
        
        if sistema_colas.esta_cancelado(user_id):
            tiempo_procesamiento = time.time() - tiempo_inicio
            await mensaje_estado.edit_text("**Conversión Cancelada**\n\nLa tarea fue cancelada correctamente.")
            return False, tiempo_procesamiento

        exito, log = await convertir_video_con_progreso(
            ruta_video,
            ruta_convertido,
            duracion_total,
            actualizar_progreso,
            config_calidad,
            debe_cancelar=lambda: sistema_colas.esta_cancelado(user_id)
        )
        
        tiempo_procesamiento = time.time() - tiempo_inicio

        if not exito:
            if log == "cancelado":
                await mensaje_estado.edit_text("**Conversión Cancelada**\n\nLa tarea fue cancelada correctamente.")
                return False, tiempo_procesamiento
            mensaje_error = ""
            if "Permission denied" in log:
                mensaje_error = "**Error de Permisos**\nNo se puede acceder a los archivos temporales."
            elif "Invalid data" in log or "Unsupported codec" in log:
                mensaje_error = "**Formato No Soportado**\nEl formato de video no es compatible."
            elif "Cannot allocate memory" in log:
                mensaje_error = "**Memoria Insuficiente**\nEl sistema no tiene suficiente memoria."
            else:
                mensaje_error = f"**Error en Conversión**\n\n`{log}`"
            
            await mensaje_estado.edit_text(
                f"{mensaje_error}\n\n"
                "**Soluciones posibles:**\n"
                "• Verifica el formato del archivo\n"
                "• Intenta con un video más pequeño\n"
                "• Usa el comando /help para obtener ayuda"
            )
            return False, tiempo_procesamiento

        if sistema_colas.esta_cancelado(user_id):
            await mensaje_estado.edit_text("**Conversión Cancelada**\n\nLa tarea fue cancelada correctamente antes de subir el resultado.")
            return False, tiempo_procesamiento

        await actualizar_progreso(100, "Completado")
        
        tamano_convertido = os.path.getsize(ruta_convertido)
        duracion_convertido = obtener_duracion_formateada(ruta_convertido)
        reduccion = calcular_reduccion(tamano_original, tamano_convertido)

        await mensaje_estado.edit_text(
            "**Conversión Exitosa**\n\n"
            "Subiendo resultado final...\n"
            "¡Casi listo!"
        )

        db.agregar_video_convertido({
            'user_id': user_id,
            'nombre_archivo': nombre_original,
            'tamano_original': tamano_original,
            'tamano_convertido': tamano_convertido,
            'duracion_original': formatear_tiempo(duracion_total),
            'duracion_convertido': duracion_convertido,
            'calidad_config': json.dumps(config_calidad),
            'tiempo_procesamiento': tiempo_procesamiento
        })

        caption = (
            "**Conversión Completada**\n\n"
            f"**Archivo:** `{nombre_original[:30]}...`\n"
            f"**Tamaño original:** `{formatear_tamano(tamano_original)}`\n"
            f"**Tamaño convertido:** `{formatear_tamano(tamano_convertido)}`\n"
            f"**{reduccion}**\n"
            f"**Tiempo de procesamiento:** `{formatear_tiempo(tiempo_procesamiento)}`\n"
            f"**Duración:** `{duracion_convertido}`\n"
            f"**Calidad:** `{config_calidad['resolution']}`\n\n"
            f"Bot: @{cliente.me.username}"
        )

        if tamano_convertido > 10 * 1024 * 1024:
            ruta_thumbnail = os.path.join(Config.TEMP_DIR, f"thumb_{user_id}_{int(time.time())}_{uuid.uuid4().hex}.jpg")
            if await asyncio.to_thread(generar_thumbnail, ruta_convertido, ruta_thumbnail):
                with open(ruta_thumbnail, 'rb') as thumb:
                    await mensaje.reply_video(
                        video=ruta_convertido,
                        caption=caption,
                        supports_streaming=True,
                        thumb=thumb
                    )
            else:
                await mensaje.reply_video(
                    video=ruta_convertido,
                    caption=caption,
                    supports_streaming=True
                )
        else:
            await mensaje.reply_video(
                video=ruta_convertido,
                caption=caption,
                supports_streaming=True
            )

        await mensaje_estado.delete()
        return True, tiempo_procesamiento

    except Exception as e:
        mensaje_error = (
            "**Error en Procesamiento**\n\n"
            f"**Detalles:** `{str(e)}`\n\n"
            "Usa el comando /help para obtener ayuda"
        )
        try:
            if mensaje_estado:
                await mensaje_estado.edit_text(mensaje_error)
            else:
                await mensaje.reply_text(mensaje_error)
        except:
            pass
        return False, time.time() - tiempo_inicio
    finally:
        if ruta_thumbnail and os.path.exists(ruta_thumbnail):
            try:
                os.remove(ruta_thumbnail)
            except:
                pass

def verificar_soporte_y_baneo(func):
    async def wrapper(cliente, mensaje):
        user_id = mensaje.from_user.id
        
        if es_administrador(user_id):
            if user_id in estado_importacion_db or user_id in estado_broadcast:
                return await func(cliente, mensaje)
        
        if modo_soporte_activo() and not es_administrador(user_id):
            await mensaje.reply_text(
                "**Modo Soporte Activo**\n\n"
                "El bot se encuentra en modo soporte temporalmente.\n"
                "Por favor, intenta nuevamente más tarde.\n\n"
                "Para consultas, contacta a los administradores."
            )
            return
        
        if db.usuario_esta_baneado(user_id):
            await mensaje.reply_text(
                "**Acceso Denegado**\n\n"
                "Tu cuenta ha sido baneada de este bot.\n"
                "Si crees que esto es un error, contacta a los administradores."
            )
            return
        
        db.agregar_actualizar_usuario({
            'user_id': user_id,
            'username': mensaje.from_user.username,
            'first_name': mensaje.from_user.first_name,
            'last_name': mensaje.from_user.last_name,
            'language_code': mensaje.from_user.language_code
        })
        
        return await func(cliente, mensaje)
    return wrapper

@app.on_message(filters.video | filters.document)
@verificar_soporte_y_baneo
async def manejar_video(cliente: Client, mensaje: Message):
    user_id = mensaje.from_user.id
    
    if es_administrador(user_id):
        if user_id in estado_importacion_db:
            await procesar_importacion_db_documento(cliente, mensaje, user_id)
            return
        if user_id in estado_broadcast:
            return
    
    try:
        if mensaje.document:
            mime_type = (mensaje.document.mime_type or "").lower()
            file_name = mensaje.document.file_name or ""
            video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.3gpp', '.ts', '.mts', '.m2ts', '.ogv', '.vob']
            tiene_extension_video = any(file_name.lower().endswith(ext) for ext in video_extensions)
            tiene_mime_video = mime_type.startswith('video/')

            if not tiene_mime_video and not tiene_extension_video:
                await mensaje.reply_text(
                    "**Formato No Soportado**\n\n"
                    "Por favor, envía un archivo de video válido.\n"
                    "Formatos aceptados: MP4, AVI, MKV, MOV, WMV, FLV, WebM, TS, 3GP, OGV, VOB, etc."
                )
                return

        limite_bytes = Config.MAX_FILE_SIZE_MB * 1024 * 1024
        if mensaje.video:
            tamano_video = mensaje.video.file_size
        else:
            tamano_video = mensaje.document.file_size
            
        if tamano_video > limite_bytes and not es_administrador(user_id):
            await mensaje.reply_text(
                "**Límite de Tamaño Excedido**\n\n"
                f"**Tu archivo:** `{formatear_tamano(tamano_video)}`\n"
                f"**Límite permitido:** `{Config.MAX_FILE_SIZE_MB} MB`\n\n"
                "Por favor, reduce el tamaño del video antes de enviarlo."
            )
            return

        ruta_video = await descargar_video_seguro(mensaje, user_id)
        ruta_convertido = os.path.join(Config.TEMP_DIR, f"convertido_{user_id}_{int(time.time())}_{uuid.uuid4().hex}.mp4")

        trabajo = {
            "cliente": cliente,
            "mensaje": mensaje,
            "ruta_video": ruta_video,
            "ruta_convertido": ruta_convertido,
            "user_id": user_id
        }

        estado = sistema_colas.agregar_trabajo(user_id, trabajo)
        estadisticas = sistema_colas.obtener_estadisticas()
        
        if estado == "procesando":
            mensaje_estado = await mensaje.reply_text(
                "**Video Recibido**\n\n"
                f"Tu video `{obtener_nombre_archivo_mensaje(mensaje)[:30]}...` ha sido recibido.\n\n"
                "**Por favor espera mientras se procesa tu video...**\n\n"
                f"**Procesos activos:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
                f"**En espera:** `{estadisticas['en_espera']}`\n\n"
                "Recibirás una notificación cuando comience la conversión.",
                reply_markup=teclado_cancelar_conversion()
            )
            
            trabajo["mensaje_estado"] = mensaje_estado
            sistema_colas.procesos_activos[user_id] = trabajo
            
            asyncio.create_task(
                procesar_y_limpiar(cliente, mensaje, ruta_video, ruta_convertido, user_id, mensaje_estado)
            )
        elif estado == "usuario_ocupado":
            await mensaje.reply_text(
                "**Usuario Ocupado**\n\n"
                "Ya tienes un video en proceso de conversión.\n"
                "Por favor, espera a que termine antes de enviar otro."
            )
            if os.path.exists(ruta_video):
                os.remove(ruta_video)
        else:
            posicion = estado.split('_')[1]
            mensaje_estado = await mensaje.reply_text(
                "**Video Encolado**\n\n"
                f"**Posición en cola:** `#{posicion}`\n"
                f"**Procesos activos:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
                f"**Personas en espera:** `{estadisticas['en_espera']}`\n\n"
                "Tu video será procesado en orden de llegada.\n\n"
                "**Pulsa Cancelar o usa /cancelar si ya no quieres procesarlo.**",
                reply_markup=teclado_cancelar_conversion()
            )
            trabajo["mensaje_estado"] = mensaje_estado
        
    except Exception as e:
        logger.error(f"Error al procesar video: {e}")
        await mensaje.reply_text(
            "**Error al Procesar**\n\n"
            f"**Detalles:** `{str(e)}`\n\n"
            "Usa el comando /help si el problema persiste."
        )

async def procesar_y_limpiar(cliente, mensaje, ruta_video, ruta_convertido, user_id, mensaje_estado=None):
    exito = False
    tiempo_procesamiento = 0
    try:
        resultado = await procesar_video(cliente, mensaje, ruta_video, ruta_convertido, user_id, mensaje_estado)
        if isinstance(resultado, tuple):
            exito, tiempo_procesamiento = resultado
    except Exception as e:
        logger.error(f"Error en procesamiento: {e}")
    finally:
        archivos_a_eliminar = []
        if ruta_video and os.path.exists(ruta_video):
            archivos_a_eliminar.append(ruta_video)
        if ruta_convertido and os.path.exists(ruta_convertido):
            archivos_a_eliminar.append(ruta_convertido)
        
        for archivo in archivos_a_eliminar:
            try:
                os.remove(archivo)
                logger.info(f"Archivo temporal eliminado: {archivo}")
            except Exception as e:
                logger.error(f"Error eliminando archivo temporal {archivo}: {e}")
        
        sistema_colas.limpiar_cancelacion(user_id)
        eliminados = db.eliminar_videos_antiguos(7)
        if eliminados > 0:
            logger.info(f"Eliminados {eliminados} registros antiguos de la base de datos")
        
        siguiente_user_id, siguiente_trabajo = sistema_colas.trabajo_completado(user_id, exito, tiempo_procesamiento)
        if siguiente_trabajo:
            asyncio.create_task(
                procesar_y_limpiar(
                    siguiente_trabajo["cliente"],
                    siguiente_trabajo["mensaje"],
                    siguiente_trabajo["ruta_video"],
                    siguiente_trabajo["ruta_convertido"],
                    siguiente_user_id,
                    siguiente_trabajo.get("mensaje_estado")
                )
            )

@app.on_message(filters.command("start"))
@verificar_soporte_y_baneo
async def comando_inicio(cliente: Client, mensaje: Message):
    estadisticas = sistema_colas.obtener_estadisticas()
    estadisticas_bot = db.obtener_estadisticas_generales()
    
    texto = (
        "**Conversor de Videos Pro**\n\n"
        f"**Hola {mensaje.from_user.first_name}!**\n\n"
        "**Características principales:**\n"
        "• Conversión a MP4 HD\n"
        "• Compresión inteligente\n"
        "• Sistema de colas avanzado\n"
        "• Barra de progreso en tiempo real\n\n"
        f"**Límite por archivo:** `{Config.MAX_FILE_SIZE_MB} MB`\n"
        f"**Procesos simultáneos:** `{estadisticas['max_concurrente']}`\n"
        f"**Videos convertidos:** `{estadisticas_bot['total_videos']}`\n\n"
        "**¿Cómo usar?**\n"
        "Simplemente envía cualquier video que desees convertir."
    )
    
    await mensaje.reply_text(texto)

@app.on_message(filters.command("help"))
@verificar_soporte_y_baneo
async def comando_ayuda(cliente: Client, mensaje: Message):
    texto = (
        "**Centro de Ayuda - Conversor de Videos**\n\n"
        
        "**Descripción General**\n"
        "Este bot convierte y comprime videos a formato MP4 con calidad optimizada.\n\n"
        
        "**Proceso de Conversión**\n"
        "1. Envía cualquier archivo de video\n"
        "2. El bot procesa automáticamente el video\n"
        "3. Recibe barra de progreso en tiempo real\n"
        "4. Obtén el video convertido en MP4\n\n"
        
        "**Comandos Disponibles**\n"
        "• `/start` - Iniciar el bot\n"
        "• `/help` - Mostrar esta ayuda\n"
        "• `/info` - Estado del sistema y estadísticas\n"
        "• `/cola` - Ver tu posición en la cola\n"
        "• `/historial` - Tu historial de conversiones\n"
        "• `/calidad` - Configurar calidad personalizada\n\n"
        
        "**Formatos soportados**\n"
        "MP4, AVI, MKV, MOV, WMV, FLV, WebM\n\n"
        
        "**Límites actuales**\n"
        f"• **Tamaño máximo:** `{Config.MAX_FILE_SIZE_MB} MB`\n"
        f"• **Resolución:** `{Config.DEFAULT_QUALITY['resolution']}`\n"
        f"• **Calidad CRF:** `{Config.DEFAULT_QUALITY['crf']}`\n\n"
        
        "Para más información, contacta a los administradores."
    )
    
    await mensaje.reply_text(texto)

@app.on_message(filters.command("info"))
@verificar_soporte_y_baneo
async def comando_info(cliente: Client, mensaje: Message):
    try:
        uso_cpu = psutil.cpu_percent()
        memoria = psutil.virtual_memory()
        disco = psutil.disk_usage('/')
        
        estadisticas = sistema_colas.obtener_estadisticas()
        estadisticas_bot = db.obtener_estadisticas_generales()
        es_admin_user = es_administrador(mensaje.from_user.id)
        
        texto_info = (
            "**Estado Completo del Sistema**\n\n"
            
            "**Información de Usuario**\n"
            f"• **Nombre:** {mensaje.from_user.first_name}\n"
            f"• **ID:** `{mensaje.from_user.id}`\n"
            f"• **Tipo:** {'Administrador' if es_admin_user else 'Usuario'}\n\n"
            
            "**Estadísticas Globales**\n"
            f"• **Usuarios registrados:** `{estadisticas_bot['total_usuarios']}`\n"
            f"• **Videos convertidos:** `{estadisticas_bot['total_videos']}`\n"
            f"• **Espacio ahorrado:** `{formatear_tamano(estadisticas_bot['espacio_ahorrado'])}`\n"
            f"• **Usuarios baneados:** `{estadisticas_bot['total_baneados']}`\n"
            f"• **Administradores:** `{estadisticas_bot['total_administradores']}`\n\n"
            
            "**Sistema de Colas**\n"
            f"• **Procesando ahora:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
            f"• **En espera:** `{estadisticas['en_espera']}`\n"
            f"• **Completados:** `{estadisticas['completados']}`\n"
            f"• **Tiempo promedio:** `{formatear_tiempo(estadisticas['tiempo_promedio'])}`\n\n"
            
            "**Configuración Actual**\n"
            f"• **Resolución:** `{Config.DEFAULT_QUALITY['resolution']}`\n"
            f"• **Calidad CRF:** `{Config.DEFAULT_QUALITY['crf']}`\n"
            f"• **Bitrate de audio:** `{Config.DEFAULT_QUALITY['audio_bitrate']}`\n"
            f"• **FPS:** `{Config.DEFAULT_QUALITY['fps']}`\n\n"
            
            "**Estado del Servidor**\n"
            f"• **Uso de CPU:** `{uso_cpu:.1f}%`\n"
            f"• **Uso de memoria:** `{memoria.percent:.1f}%`\n"
            f"• **Espacio libre:** `{formatear_tamano(disco.free)}`\n"
        )
        
    except Exception as e:
        logger.error(f"Error en info: {e}")
        estadisticas = sistema_colas.obtener_estadisticas()
        texto_info = (
            "**Información del Sistema**\n\n"
            f"**Usuario:** {mensaje.from_user.first_name}\n"
            f"**Límite:** {Config.MAX_FILE_SIZE_MB}MB\n"
            f"**Procesos activos:** {estadisticas['procesando']}/{estadisticas['max_concurrente']}\n"
            f"**En cola:** {estadisticas['en_espera']}\n"
            f"**Completados:** {estadisticas['completados']}\n"
        )
    
    await mensaje.reply_text(texto_info)

@app.on_message(filters.command("cola"))
@verificar_soporte_y_baneo
async def comando_cola(cliente: Client, mensaje: Message):
    estadisticas = sistema_colas.obtener_estadisticas()
    estado_usuario = sistema_colas.obtener_estado(mensaje.from_user.id)
    
    if estado_usuario == "procesando":
        emoji_estado = "⚡"
        texto_estado = "Procesando ahora"
        tiempo_estimado = f"Tiempo estimado: `{formatear_tiempo(estadisticas['tiempo_promedio'])}`"
    elif estado_usuario.startswith("encolado"):
        posicion = estado_usuario.split('_')[1]
        emoji_estado = "📥"
        texto_estado = f"En cola (posición #{posicion})"
        tiempo_estimado = f"Tiempo estimado: `{formatear_tiempo(int(posicion) * estadisticas['tiempo_promedio'])}`"
    else:
        emoji_estado = "✅"
        texto_estado = "Sin procesos activos"
        tiempo_estimado = "Puedes enviar un video para comenzar"
    
    texto = (
        "**Estado de la Cola de Procesamiento**\n\n"
        f"{emoji_estado} **Tu estado:** {texto_estado}\n"
        f"{tiempo_estimado}\n\n"
        
        "**Estadísticas de la Cola**\n"
        f"• **Procesos activos:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
        f"• **Videos en espera:** `{estadisticas['en_espera']}`\n"
        f"• **Completados en esta sesión:** `{estadisticas['completados']}`\n"
        f"• **Tiempo promedio:** `{formatear_tiempo(estadisticas['tiempo_promedio'])}`\n\n"
        
        "**Información adicional**\n"
        "• El sistema procesa videos por orden de llegada\n"
        "• Solo puedes tener un video en proceso a la vez\n"
        "• Los tiempos son estimados y pueden variar\n"
    )
    
    await mensaje.reply_text(texto)

@app.on_message(filters.command("historial"))
@verificar_soporte_y_baneo
async def comando_historial(cliente: Client, mensaje: Message):
    user_id = mensaje.from_user.id
    historial = db.obtener_historial_usuario(user_id, limite=10)
    usuario = db.obtener_usuario(user_id)
    
    if not historial:
        await mensaje.reply_text(
            "**Historial de Conversiones**\n\n"
            "Aún no has convertido videos.\n\n"
            "**Para comenzar:**\n"
            "1. Envía cualquier video al bot\n"
            "2. Espera el procesamiento automático\n"
            "3. Recibe tu video convertido\n\n"
            "¡Tu historial aparecerá aquí después de tu primera conversión!"
        )
        return
    
    texto = f"**Historial de Conversiones**\n\n"
    texto += f"**Usuario:** {mensaje.from_user.first_name}\n"
    texto += f"**Total de conversiones:** `{usuario['total_conversiones'] if usuario else len(historial)}`\n\n"
    
    total_ahorro = 0
    for i, conversion in enumerate(historial, 1):
        reduccion = conversion['tamano_original'] - conversion['tamano_convertido']
        porcentaje = (reduccion / conversion['tamano_original']) * 100 if conversion['tamano_original'] > 0 else 0
        total_ahorro += max(0, reduccion)
        
        emoji = "📉" if reduccion > 0 else "📈" if reduccion < 0 else "⚖️"
        
        texto += (
            f"**{i}. {conversion['nombre_archivo'][:25]}...**\n"
            f"   **Tamaños:** `{formatear_tamano(conversion['tamano_original'])}` → `{formatear_tamano(conversion['tamano_convertido'])}`\n"
            f"   **Cambio:** `{abs(porcentaje):.1f}%` ({'+' if reduccion < 0 else '-'}{formatear_tamano(abs(reduccion))})\n"
            f"   **Duración:** `{formatear_tiempo(conversion['tiempo_procesamiento'])}`\n"
            f"   **Fecha:** `{conversion['fecha_conversion'][:16]}`\n\n"
        )
    
    texto += f"**Espacio total ahorrado:** `{formatear_tamano(total_ahorro)}`\n\n"
    texto += "*Mostrando las 10 conversiones más recientes*"
    
    await mensaje.reply_text(texto)

@app.on_message(filters.command("calidad"))
@verificar_soporte_y_baneo
async def comando_calidad(cliente: Client, mensaje: Message):
    user_id = mensaje.from_user.id
    es_admin = es_administrador(user_id)
    texto = mensaje.text.split()
    
    if len(texto) == 1:
        config_usuario = db.obtener_configuracion_usuario(user_id)
        config_actual = config_usuario if config_usuario else Config.DEFAULT_QUALITY
        
        tipo_config = "personalizada" if config_usuario else "por defecto"
        
        mensaje_info = (
            f"**Configuración de Calidad ({tipo_config})**\n\n"
            f"**Resolución actual:** `{config_actual['resolution']}`\n"
            f"**CRF actual:** `{config_actual['crf']}` (0-51, menor es mejor)\n"
            f"**Audio actual:** `{config_actual['audio_bitrate']}`\n"
            f"**FPS actual:** `{config_actual['fps']}`\n"
            f"**Preset actual:** `{config_actual['preset']}`\n"
            f"**Codec actual:** `{config_actual['codec']}`\n\n"
            "**Para modificar:**\n"
            "`/calidad parametro=valor`\n\n"
            "**Ejemplos:**\n"
            "• `/calidad resolution=1920x1080`\n"
            "• `/calidad crf=18 audio_bitrate=192k`\n"
            "• `/calidad preset=fast fps=24`\n\n"
            "**Parámetros disponibles:**\n"
            "• `resolution` - Ej: 1280x720, 1920x1080\n"
            "• `crf` - Calidad (0-51, 23 por defecto)\n"
            "• `audio_bitrate` - Ej: 128k, 192k, 256k\n"
            "• `fps` - Cuadros por segundo\n"
            "• `preset` - ultrafast, fast, medium, slow\n"
            "• `codec` - libx264, libx265\n\n"
        )
        
        if es_admin:
            mensaje_info += "**Nota:** Como administrador, los cambios afectarán a TODOS los usuarios (configuración por defecto)."
        else:
            mensaje_info += "**Nota:** Los cambios solo afectan tus conversiones personales."
        
        await mensaje.reply_text(mensaje_info)
        return
    
    try:
        parametros = " ".join(texto[1:]).split()
        cambios = []
        
        if es_admin:
            config_actual = Config.DEFAULT_QUALITY.copy()
            config_nueva = config_actual.copy()
        else:
            config_actual = db.obtener_configuracion_usuario(user_id) or Config.DEFAULT_QUALITY.copy()
            config_nueva = config_actual.copy()
        
        for param in parametros:
            if '=' in param:
                key, value = param.split('=', 1)
                if key in config_nueva:
                    valor_anterior = config_nueva[key]
                    config_nueva[key] = value
                    cambios.append(f"• **{key}:** `{valor_anterior}` → `{value}`")
        
        if cambios:
            if es_admin:
                if db.actualizar_configuracion('calidad_default', json.dumps(config_nueva)):
                    Config.DEFAULT_QUALITY = config_nueva
                    respuesta = (
                        "**✅ Configuración Por Defecto Actualizada**\n\n"
                        "**Cambios realizados:**\n" + "\n".join(cambios) + "\n\n"
                        "**Alcance:** TODOS los usuarios\n"
                        "**Estado:** Aplicado inmediatamente\n\n"
                        "La nueva configuración será usada por todos los usuarios que no tengan configuración personalizada."
                    )
                else:
                    respuesta = "**❌ Error:** No se pudo guardar la configuración por defecto en la base de datos."
            else:
                if db.actualizar_configuracion_usuario(user_id, config_nueva):
                    respuesta = (
                        "**✅ Configuración Personal Actualizada**\n\n"
                        "**Cambios realizados:**\n" + "\n".join(cambios) + "\n\n"
                        "**Alcance:** Solo tus conversiones\n"
                        "**Estado:** Aplicado inmediatamente\n\n"
                        "La nueva configuración será usada en tus próximas conversiones."
                    )
                else:
                    respuesta = "**❌ Error:** No se pudo guardar tu configuración personal."
        else:
            respuesta = (
                "**⚠️ Sin Cambios Válidos**\n\n"
                "No se encontraron parámetros válidos para modificar.\n\n"
                "**Parámetros aceptados:**\n"
                "`resolution`, `crf`, `audio_bitrate`, `fps`, `preset`, `codec`\n\n"
                "**Ejemplo correcto:**\n"
                "`/calidad resolution=1920x1080 crf=18`"
            )
        
        await mensaje.reply_text(respuesta)
        
    except Exception as e:
        logger.error(f"Error en comando calidad: {e}")
        await mensaje.reply_text(
            f"**❌ Error en la Configuración**\n\n"
            f"**Detalles del error:**\n`{str(e)}`\n\n"
            "Verifica la sintaxis y vuelve a intentar."
        )

async def procesar_importacion_db_documento(cliente: Client, mensaje: Message, admin_id=None):
    user_id = admin_id or mensaje.from_user.id

    if not mensaje.document:
        await mensaje.reply_text(
            "**Importar Base de Datos**\n\n"
            "Envía un archivo `.json` válido con la base de datos.\n\n"
            "**Para cancelar:** `/cancelar`"
        )
        return

    nombre_archivo = mensaje.document.file_name or ""
    if not nombre_archivo.lower().endswith(".json"):
        await mensaje.reply_text("**❌ Error:** El archivo de importación debe ser `.json`.")
        return

    ruta_importacion = os.path.join(Config.TEMP_DIR, f"db_import_{user_id}_{int(time.time())}_{uuid.uuid4().hex}.json")

    try:
        os.makedirs(Config.TEMP_DIR, exist_ok=True)
        ruta_descargada = await mensaje.download(file_name=ruta_importacion)
        exito, resultado = db.importar_base_datos(ruta_descargada, admin_id=user_id, hacer_backup=True)

        if exito:
            estado_importacion_db.pop(user_id, None)
            estadisticas = db.obtener_estadisticas_generales()
            await mensaje.reply_text(
                "**✅ Base de Datos Importada**\n\n"
                f"**Usuarios:** `{estadisticas.get('total_usuarios', 0)}`\n"
                f"**Videos:** `{estadisticas.get('total_videos', 0)}`\n"
                f"**Administradores:** `{estadisticas.get('total_administradores', 0)}`\n\n"
                f"**Backup anterior:** `{resultado or 'No creado'}`\n\n"
                "La nueva configuración fue cargada correctamente."
            )
        else:
            await mensaje.reply_text(
                "**❌ Error al Importar Base de Datos**\n\n"
                f"**Detalles:** `{resultado}`\n\n"
                "Verifica que el JSON tenga la estructura correcta."
            )
    except Exception as e:
        await mensaje.reply_text(f"**❌ Error al importar:** `{str(e)}`")
    finally:
        if os.path.exists(ruta_importacion):
            try:
                os.remove(ruta_importacion)
            except Exception:
                pass


@app.on_message(filters.command("exportdb"))
async def comando_exportdb(cliente: Client, mensaje: Message):
    if not es_administrador(mensaje.from_user.id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return

    try:
        os.makedirs(Config.TEMP_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta_exportacion = os.path.join(Config.TEMP_DIR, f"bot_database_export_{timestamp}.json")
        ruta_exportada = db.exportar_base_datos(ruta_exportacion)

        if not ruta_exportada:
            await mensaje.reply_text("**❌ Error:** No se pudo exportar la base de datos.")
            return

        await mensaje.reply_document(
            document=ruta_exportada,
            caption=(
                "**📦 Exportación de Base de Datos**\n\n"
                f"**Fecha:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"**Archivo:** `{os.path.basename(ruta_exportada)}`"
            )
        )
    except Exception as e:
        await mensaje.reply_text(f"**❌ Error exportando base de datos:** `{str(e)}`")
    finally:
        if 'ruta_exportacion' in locals() and os.path.exists(ruta_exportacion):
            try:
                os.remove(ruta_exportacion)
            except Exception:
                pass


@app.on_message(filters.command("importdb"))
async def comando_importdb(cliente: Client, mensaje: Message):
    user_id = mensaje.from_user.id
    if not es_administrador(user_id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return

    if mensaje.reply_to_message and mensaje.reply_to_message.document:
        await procesar_importacion_db_documento(cliente, mensaje.reply_to_message, user_id)
        return

    estado_importacion_db[user_id] = "esperando_archivo_db"
    await mensaje.reply_text(
        "**Importar Base de Datos**\n\n"
        "Envía ahora el archivo `.json` exportado previamente.\n\n"
        "**También puedes:** responder a un archivo JSON con `/importdb`.\n"
        "**Para cancelar:** `/cancelar`"
    )

@app.on_message(filters.command("max"))
async def comando_max(cliente: Client, mensaje: Message):
    if not es_administrador(mensaje.from_user.id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return
    
    texto = mensaje.text.split()
    
    if len(texto) != 2:
        await mensaje.reply_text(
            "**Gestión de Límites**\n\n"
            f"**Límite actual:** `{Config.MAX_FILE_SIZE_MB} MB`\n\n"
            "**Para modificar:**\n"
            "`/max <nuevo_límite_en_MB>`\n\n"
            "**Ejemplos:**\n"
            "• `/max 500` - Establece 500 MB\n"
            "• `/max 100` - Establece 100 MB\n\n"
            "**Límites permitidos:**\n"
            "• **Mínimo:** 10 MB\n"
            "• **Máximo:** 5000 MB\n\n"
            "Este cambio afecta a todos los usuarios."
        )
        return
    
    try:
        nuevo_limite = int(texto[1])
        
        if nuevo_limite < 10:
            await mensaje.reply_text("**Error:** El mínimo permitido es 10 MB.")
            return
            
        if nuevo_limite > 5000:
            await mensaje.reply_text("**Error:** El máximo permitido es 5000 MB.")
            return
        
        if db.actualizar_configuracion('limite_peso_mb', str(nuevo_limite)):
            Config.MAX_FILE_SIZE_MB = nuevo_limite
            await mensaje.reply_text(
                "**✅ Límite Actualizado**\n\n"
                f"**Cambios realizados:**\n"
                f"• **Límite anterior:** `{Config.MAX_FILE_SIZE_MB} MB`\n"
                f"• **Nuevo límite:** `{nuevo_limite} MB`\n\n"
                f"**Alcance:** Todos los usuarios\n"
                f"**Estado:** Aplicado inmediatamente"
            )
        else:
            await mensaje.reply_text("**❌ Error:** No se pudo actualizar el límite en la base de datos.")
        
    except ValueError:
        await mensaje.reply_text(
            "**❌ Error de Formato**\n\n"
            "El límite debe ser un número entero.\n\n"
            "**Ejemplo correcto:**\n"
            "`/max 500`"
        )

@app.on_message(filters.command("modosoporte"))
async def comando_modo_soporte(cliente: Client, mensaje: Message):
    if not es_administrador(mensaje.from_user.id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return
    
    texto = mensaje.text.split()
    
    if len(texto) != 2 or texto[1].lower() not in ['on', 'off', 'activar', 'desactivar']:
        estado_actual = db.obtener_configuracion('modo_soporte')
        estado_texto = "ACTIVADO" if estado_actual and estado_actual.lower() == 'true' else "DESACTIVADO"
        
        await mensaje.reply_text(
            f"**Modo Soporte**\n\n"
            f"**Estado actual:** {estado_texto}\n\n"
            "**Uso:**\n"
            "`/modosoporte on` - Activar modo soporte\n"
            "`/modosoporte off` - Desactivar modo soporte\n\n"
            "**Descripción:**\n"
            "Cuando el modo soporte está activado, solo los administradores pueden usar el bot.\n"
            "Los usuarios regulares recibirán un mensaje indicando que el bot está en mantenimiento."
        )
        return
    
    accion = texto[1].lower()
    nuevo_valor = 'true' if accion in ['on', 'activar'] else 'false'
    
    if db.actualizar_configuracion('modo_soporte', nuevo_valor):
        estado_texto = "ACTIVADO" if nuevo_valor == 'true' else "DESACTIVADO"
        await mensaje.reply_text(
            f"**✅ Modo Soporte {estado_texto}**\n\n"
            f"El modo soporte ha sido {estado_texto.lower()} correctamente.\n\n"
            "**Efecto:**\n"
            f"{'Los usuarios regulares no podrán usar el bot hasta que se desactive el modo soporte.' if nuevo_valor == 'true' else 'Todos los usuarios pueden usar el bot normalmente.'}"
        )
    else:
        await mensaje.reply_text("**❌ Error:** No se pudo cambiar el modo soporte.")

@app.on_message(filters.command("ban"))
async def comando_ban(cliente: Client, mensaje: Message):
    if not es_administrador(mensaje.from_user.id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return
    
    texto = mensaje.text.split()
    
    if len(texto) < 2:
        usuarios_baneados = db.obtener_usuarios_baneados()
        
        if not usuarios_baneados:
            await mensaje.reply_text(
                "**Gestión de Baneos**\n\n"
                "**Usuarios baneados actualmente:** Ninguno\n\n"
                "**Uso:**\n"
                "`/ban <ID_usuario>` - Banear usuario\n"
                "`/ban @username` - Banear por username\n"
                "`/unban <ID_usuario>` - Desbanear usuario\n\n"
                "**Ejemplos:**\n"
                "• `/ban 123456789`\n"
                "• `/ban @username`\n"
                "• `/unban 123456789`"
            )
        else:
            lista_baneados = "\n".join([f"{i+1}. ID: `{u['user_id']}` - {u['first_name']} ({u['username'] or 'Sin username'})" for i, u in enumerate(usuarios_baneados[:10])])
            texto_respuesta = f"**Usuarios baneados ({len(usuarios_baneados)}):**\n\n{lista_baneados}"
            if len(usuarios_baneados) > 10:
                texto_respuesta += f"\n\n...y {len(usuarios_baneados) - 10} más"
            await mensaje.reply_text(texto_respuesta)
        return
    
    objetivo = texto[1]
    
    try:
        if objetivo.startswith('@'):
            usuario = await cliente.get_users(objetivo)
            user_id = usuario.id
            username = usuario.username
            first_name = usuario.first_name
        else:
            user_id = int(objetivo)
            usuario = await cliente.get_users(user_id)
            username = usuario.username
            first_name = usuario.first_name
        
        if user_id == mensaje.from_user.id:
            await mensaje.reply_text("**❌ Error:** No puedes banearte a ti mismo.")
            return
        
        if es_administrador(user_id):
            await mensaje.reply_text("**❌ Error:** No puedes banear a otro administrador.")
            return
        
        if db.usuario_esta_baneado(user_id):
            await mensaje.reply_text(f"**❌ Error:** El usuario `{user_id}` ya está baneado.")
            return
        
        if db.banear_usuario(user_id, mensaje.from_user.id):
            try:
                await cliente.send_message(
                    user_id,
                    "**🔨 Has sido baneado del bot**\n\n"
                    "Tu acceso al bot ha sido revocado por un administrador.\n"
                    "Si crees que esto es un error, contacta con los administradores."
                )
            except Exception as e:
                logger.warning(f"No se pudo notificar al usuario {user_id} sobre su baneo: {e}")
            
            await mensaje.reply_text(
                f"**✅ Usuario Baneado**\n\n"
                f"El usuario **{first_name}** (@{username}) ha sido baneado exitosamente.\n"
                f"**ID:** `{user_id}`"
            )
        else:
            await mensaje.reply_text("**❌ Error:** No se pudo banear al usuario.")
        
    except ValueError:
        await mensaje.reply_text("**❌ Error de Formato**\n\nEl ID de usuario debe ser un número o un @username.")
    except Exception as e:
        await mensaje.reply_text(f"**❌ Error:** No se pudo encontrar al usuario.\n\nDetalles: `{str(e)}`")

@app.on_message(filters.command("unban"))
async def comando_unban(cliente: Client, mensaje: Message):
    if not es_administrador(mensaje.from_user.id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return
    
    texto = mensaje.text.split()
    
    if len(texto) < 2:
        await mensaje.reply_text(
            "**Desbanear Usuario**\n\n"
            "**Uso:**\n"
            "`/unban <ID_usuario>` - Desbanear usuario\n"
            "`/unban @username` - Desbanear por username\n\n"
            "**Ejemplos:**\n"
            "• `/unban 123456789`\n"
            "• `/unban @username`"
        )
        return
    
    objetivo = texto[1]
    
    try:
        if objetivo.startswith('@'):
            usuario = await cliente.get_users(objetivo)
            user_id = usuario.id
            username = usuario.username
            first_name = usuario.first_name
        else:
            user_id = int(objetivo)
            usuario = await cliente.get_users(user_id)
            username = usuario.username
            first_name = usuario.first_name
        
        if not db.usuario_esta_baneado(user_id):
            await mensaje.reply_text(f"**❌ Error:** El usuario `{user_id}` no está baneado.")
            return
        
        if db.desbanear_usuario(user_id):
            try:
                await cliente.send_message(
                    user_id,
                    "**✅ Has sido desbaneado del bot**\n\n"
                    "Tu acceso al bot ha sido restaurado.\n"
                    "Ahora puedes volver a usar el bot normalmente."
                )
            except Exception as e:
                logger.warning(f"No se pudo notificar al usuario {user_id} sobre su desbaneo: {e}")
            
            await mensaje.reply_text(
                f"**✅ Usuario Desbaneado**\n\n"
                f"El usuario **{first_name}** (@{username}) ha sido desbaneado exitosamente.\n"
                f"**ID:** `{user_id}`"
            )
        else:
            await mensaje.reply_text("**❌ Error:** No se pudo desbanear al usuario.")
        
    except ValueError:
        await mensaje.reply_text("**❌ Error de Formato**\n\nEl ID de usuario debe ser un número o un @username.")
    except Exception as e:
        await mensaje.reply_text(f"**❌ Error:** No se pudo encontrar al usuario.\n\nDetalles: `{str(e)}`")

@app.on_message(filters.command("addadmin"))
async def comando_addadmin(cliente: Client, mensaje: Message):
    if not es_administrador(mensaje.from_user.id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return
    
    texto = mensaje.text.split()
    
    if len(texto) < 2:
        administradores = db.obtener_administradores()
        
        lista_admins = "\n".join([f"{i+1}. ID: `{a['user_id']}` - {a['first_name']} ({a['username'] or 'Sin username'})" for i, a in enumerate(administradores)])
        
        await mensaje.reply_text(
            f"**Gestión de Administradores**\n\n"
            f"**Administradores actuales ({len(administradores)}):**\n\n"
            f"{lista_admins}\n\n"
            "**Uso:**\n"
            "`/addadmin <ID_usuario>` - Agregar administrador\n"
            "`/addadmin @username` - Agregar por username\n"
            "`/deladmin <ID_usuario>` - Eliminar administrador\n\n"
            "**Ejemplos:**\n"
            "• `/addadmin 123456789`\n"
            "• `/addadmin @username`\n"
            "• `/deladmin 123456789`"
        )
        return
    
    objetivo = texto[1]
    
    try:
        if objetivo.startswith('@'):
            usuario = await cliente.get_users(objetivo)
            user_id = usuario.id
            username = usuario.username
            first_name = usuario.first_name
        else:
            user_id = int(objetivo)
            usuario = await cliente.get_users(user_id)
            username = usuario.username
            first_name = usuario.first_name
        
        if es_administrador(user_id):
            await mensaje.reply_text(f"**❌ Error:** El usuario `{user_id}` ya es administrador.")
            return
        
        if db.agregar_administrador(user_id, username, first_name, mensaje.from_user.id):
            try:
                await cliente.send_message(
                    user_id,
                    "**👑 Has sido agregado como administrador**\n\n"
                    "Ahora tienes permisos de administrador en el bot.\n"
                    "Puedes usar los comandos de administración para gestionar el bot."
                )
            except Exception as e:
                logger.warning(f"No se pudo notificar al usuario {user_id} sobre su nuevo rol de administrador: {e}")
            
            await mensaje.reply_text(
                f"**✅ Administrador Agregado**\n\n"
                f"**Usuario:** {first_name} (@{username})\n"
                f"**ID:** `{user_id}`\n"
                f"**Agregado por:** `{mensaje.from_user.id}`\n\n"
                f"El usuario ahora tiene permisos de administrador."
            )
        else:
            await mensaje.reply_text("**❌ Error:** No se pudo agregar al administrador.")
        
    except ValueError:
        await mensaje.reply_text("**❌ Error de Formato**\n\nEl ID de usuario debe ser un número o un @username.")
    except Exception as e:
        await mensaje.reply_text(f"**❌ Error:** No se pudo encontrar al usuario.\n\nDetalles: `{str(e)}`")

@app.on_message(filters.command("deladmin"))
async def comando_deladmin(cliente: Client, mensaje: Message):
    if not es_administrador(mensaje.from_user.id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return
    
    texto = mensaje.text.split()
    
    if len(texto) < 2:
        await mensaje.reply_text(
            "**Eliminar Administrador**\n\n"
            "**Uso:**\n"
            "`/deladmin <ID_usuario>` - Eliminar administrador\n"
            "`/deladmin @username` - Eliminar por username\n\n"
            "**Ejemplos:**\n"
            "• `/deladmin 123456789`\n"
            "• `/deladmin @username`"
        )
        return
    
    objetivo = texto[1]
    
    try:
        if objetivo.startswith('@'):
            usuario = await cliente.get_users(objetivo)
            user_id = usuario.id
            username = usuario.username
            first_name = usuario.first_name
        else:
            user_id = int(objetivo)
            usuario = await cliente.get_users(user_id)
            username = usuario.username
            first_name = usuario.first_name
        
        if user_id == mensaje.from_user.id:
            await mensaje.reply_text("**❌ Error:** No puedes eliminarte a ti mismo como administrador.")
            return
        
        if not es_administrador(user_id):
            await mensaje.reply_text(f"**❌ Error:** El usuario `{user_id}` no es administrador.")
            return
        
        if db.eliminar_administrador(user_id):
            try:
                await cliente.send_message(
                    user_id,
                    "**👑 Has sido eliminado como administrador**\n\n"
                    "Tus permisos de administrador en el bot han sido revocados.\n"
                    "Ya no podrás usar los comandos de administración."
                )
            except Exception as e:
                logger.warning(f"No se pudo notificar al usuario {user_id} sobre la eliminación de su rol de administrador: {e}")
            
            await mensaje.reply_text(
                f"**✅ Administrador Eliminado**\n\n"
                f"**Usuario:** {first_name} (@{username})\n"
                f"**ID:** `{user_id}`\n\n"
                f"El usuario ha sido eliminado como administrador."
            )
        else:
            await mensaje.reply_text("**❌ Error:** No se pudo eliminar al administrador.")
        
    except ValueError:
        await mensaje.reply_text("**❌ Error de Formato**\n\nEl ID de usuario debe ser un número o un @username.")
    except Exception as e:
        await mensaje.reply_text(f"**❌ Error:** No se pudo encontrar al usuario.\n\nDetalles: `{str(e)}`")

@app.on_message(filters.command("broadcast"))
async def comando_broadcast(cliente: Client, mensaje: Message):
    if not es_administrador(mensaje.from_user.id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Enviar a todos los usuarios", callback_data="broadcast_all")],
        [InlineKeyboardButton("👤 Enviar a usuario específico", callback_data="broadcast_user")],
        [InlineKeyboardButton("📊 Estadísticas de usuarios", callback_data="broadcast_stats")]
    ])
    
    await mensaje.reply_text(
        "**Sistema de Mensajes**\n\n"
        "Selecciona una opción para enviar mensajes:\n\n"
        "• **📢 Enviar a todos:** Mensaje global a todos los usuarios\n"
        "• **👤 Enviar a usuario:** Mensaje privado a un usuario específico\n"
        "• **📊 Estadísticas:** Ver estadísticas de usuarios",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^broadcast_"))
async def manejar_broadcast_callback(cliente: Client, callback_query: CallbackQuery):
    if not es_administrador(callback_query.from_user.id):
        await callback_query.answer("Acceso denegado", show_alert=True)
        return
    
    accion = callback_query.data
    user_id = callback_query.from_user.id
    
    if accion == "broadcast_all":
        estado_broadcast[user_id] = "esperando_mensaje_global"
        await callback_query.message.edit_text(
            "**📢 Enviar Mensaje a Todos los Usuarios**\n\n"
            "Por favor, envía el mensaje que deseas enviar a todos los usuarios.\n"
            "Puedes incluir texto, imágenes, videos o cualquier tipo de contenido.\n\n"
            "**Nota:** Este mensaje será enviado a todos los usuarios registrados.\n\n"
            "**Para cancelar,** envía /cancelar"
        )
        await callback_query.answer()
        
    elif accion == "broadcast_user":
        estado_broadcast[user_id] = "esperando_usuario_especifico"
        await callback_query.message.edit_text(
            "**👤 Enviar Mensaje a Usuario Específico**\n\n"
            "Por favor, envía el ID del usuario al que quieres enviar el mensaje.\n\n"
            "**Formato:**\n"
            "`123456789` o `@username`\n\n"
            "**Para cancelar,** envía /cancelar"
        )
        await callback_query.answer()
        
    elif accion == "broadcast_stats":
        usuarios = db.obtener_todos_usuarios()
        usuarios_baneados = db.obtener_usuarios_baneados()
        administradores = db.obtener_administradores()
        
        estadisticas = db.obtener_estadisticas_generales()
        
        texto = (
            f"**📊 Estadísticas de Usuarios**\n\n"
            f"**Usuarios totales:** `{len(usuarios)}`\n"
            f"**Usuarios baneados:** `{len(usuarios_baneados)}`\n"
            f"**Administradores:** `{len(administradores)}`\n"
            f"**Usuarios activos:** `{estadisticas.get('total_usuarios', 0)}`\n"
            f"**Conversiones totales:** `{estadisticas.get('total_videos', 0)}`\n\n"
        )
        
        if len(usuarios) > 0:
            ultimos_usuarios = usuarios[:5]
            texto += "**Últimos 5 usuarios registrados:**\n"
            for i, usuario in enumerate(ultimos_usuarios, 1):
                estado = "🚫 BANEADO" if usuario.get('esta_baneado') else "✅ ACTIVO"
                texto += f"{i}. ID: `{usuario['user_id']}` - {usuario['first_name']} - {estado}\n"
        
        await callback_query.message.edit_text(texto)
        await callback_query.answer()

@app.on_message(filters.command("sendto"))
async def comando_sendto(cliente: Client, mensaje: Message):
    if not es_administrador(mensaje.from_user.id):
        await mensaje.reply_text("**Acceso Denegado**\nEste comando es solo para administradores.")
        return
    
    texto = mensaje.text.split('\n', 1)
    
    if len(texto) < 2:
        await mensaje.reply_text(
            "**Enviar Mensaje a Usuario**\n\n"
            "**Uso:**\n"
            "`/sendto ID_USUARIO\nTu mensaje aquí`\n\n"
            "**Ejemplo:**\n"
            "`/sendto 123456789\nHola, este es un mensaje personalizado.`\n\n"
            "También puedes responder a un mensaje con `/sendto` para enviar ese mensaje."
        )
        return
    
    primera_linea = texto[0].split()
    
    if len(primera_linea) < 2:
        await mensaje.reply_text("**Error:** Debes especificar el ID del usuario.")
        return
    
    try:
        user_id = int(primera_linea[1])
        mensaje_texto = texto[1]
        
        try:
            await cliente.send_message(user_id, mensaje_texto)
            await mensaje.reply_text(f"**✅ Mensaje Enviado**\n\nMensaje enviado exitosamente al usuario `{user_id}`.")
        except Exception as e:
            await mensaje.reply_text(f"**❌ Error al Enviar**\n\nNo se pudo enviar el mensaje al usuario `{user_id}`.\n\nError: `{str(e)}`")
            
    except ValueError:
        await mensaje.reply_text("**Error de Formato**\n\nEl ID de usuario debe ser un número.")
    except Exception as e:
        await mensaje.reply_text(f"**Error:** {str(e)}")

async def enviar_mensaje_global(cliente: Client, admin_id: int, mensaje: Message):
    try:
        usuarios = db.obtener_todos_usuarios()
        usuarios_activos = [u for u in usuarios if not u.get('esta_baneado')]
        
        total_usuarios = len(usuarios_activos)
        enviados = 0
        fallados = 0
        
        mensaje_estado = await cliente.send_message(admin_id, f"**Iniciando envío global**\n\n**Total de usuarios:** {total_usuarios}\n**Enviados:** 0\n**Fallados:** 0\n\n**Progreso:** 0%")
        
        for i, usuario in enumerate(usuarios_activos):
            try:
                if usuario['user_id'] == admin_id:
                    continue
                    
                await mensaje.copy(usuario['user_id'])
                enviados += 1
                
            except Exception:
                fallados += 1
            
            if i % 10 == 0 or i == total_usuarios - 1:
                porcentaje = ((i + 1) / total_usuarios) * 100
                await mensaje_estado.edit_text(
                    f"**Envío global en progreso**\n\n"
                    f"**Total de usuarios:** {total_usuarios}\n"
                    f"**Enviados:** {enviados}\n"
                    f"**Fallados:** {fallados}\n\n"
                    f"**Progreso:** {porcentaje:.1f}%"
                )
        
        await mensaje_estado.edit_text(
            f"**✅ Envío Global Completado**\n\n"
            f"**Resultados:**\n"
            f"• **Total de usuarios:** {total_usuarios}\n"
            f"• **Mensajes enviados:** {enviados}\n"
            f"• **Mensajes fallidos:** {fallados}\n"
            f"• **Tasa de éxito:** {(enviados/total_usuarios*100):.1f}%\n\n"
            f"El mensaje ha sido enviado a todos los usuarios activos."
        )
        
    except Exception as e:
        await cliente.send_message(admin_id, f"**❌ Error en envío global**\n\nError: `{str(e)}`")

def es_administrador_filtro(_, __, message: Message):
    return es_administrador(message.from_user.id)

filtro_admin = filters.create(es_administrador_filtro)

@app.on_message(filters.private & filtro_admin)
async def manejar_mensaje_admin(cliente: Client, mensaje: Message):
    user_id = mensaje.from_user.id
    
    if mensaje.text and mensaje.text.startswith("/cancelar"):
        if user_id in estado_broadcast:
            del estado_broadcast[user_id]
            await mensaje.reply_text("**Operación de broadcast cancelada.**")
            return
        if user_id in estado_importacion_db:
            del estado_importacion_db[user_id]
            await mensaje.reply_text("**Importación de base de datos cancelada.**")
            return

    if user_id in estado_importacion_db and mensaje.document:
        await procesar_importacion_db_documento(cliente, mensaje, user_id)
        return
    
    if user_id in estado_broadcast:
        estado = estado_broadcast[user_id]
        
        if estado == "esperando_mensaje_global":
            del estado_broadcast[user_id]
            await enviar_mensaje_global(cliente, user_id, mensaje)
            return
            
        elif estado == "esperando_usuario_especifico":
            try:
                if mensaje.text:
                    if mensaje.text.startswith('@'):
                        usuario = await cliente.get_users(mensaje.text)
                        user_id_destino = usuario.id
                    else:
                        user_id_destino = int(mensaje.text)
                    
                    del estado_broadcast[user_id]
                    
                    estado_broadcast[user_id] = f"esperando_mensaje_para_{user_id_destino}"
                    await mensaje.reply_text(
                        f"**Usuario seleccionado:** `{user_id_destino}`\n\n"
                        "Ahora envía el mensaje que quieres enviar a este usuario.\n\n"
                        "**Para cancelar,** envía /cancelar"
                    )
                    return
                else:
                    await mensaje.reply_text("**❌ Error:** Debes enviar el ID o username del usuario.")
                    return
                
            except Exception as e:
                await mensaje.reply_text(f"**Error:** No se pudo encontrar al usuario.\n\nDetalles: `{str(e)}`")
            return
            
        elif estado.startswith("esperando_mensaje_para_"):
            try:
                user_id_destino = int(estado.split('_')[-1])
                del estado_broadcast[user_id]
                
                await mensaje.copy(user_id_destino)
                await mensaje.reply_text(f"**✅ Mensaje Enviado**\n\nMensaje enviado exitosamente al usuario `{user_id_destino}`.")
                
            except Exception as e:
                await mensaje.reply_text(f"**❌ Error al Enviar**\n\nNo se pudo enviar el mensaje.\n\nError: `{str(e)}`")
            return

async def cancelar_trabajo_usuario(user_id: int, mensaje_respuesta=None, callback_query: CallbackQuery = None):
    estado, trabajo = sistema_colas.solicitar_cancelacion(user_id)

    if estado == "procesando":
        texto = "**Cancelación Solicitada**\n\nEl proceso activo se detendrá en unos segundos."
        if callback_query:
            await callback_query.answer("Cancelación solicitada", show_alert=False)
            try:
                await callback_query.message.edit_text(texto)
            except Exception:
                pass
        elif mensaje_respuesta:
            await mensaje_respuesta.reply_text(texto)
        return True

    if estado == "encolado":
        limpiar_archivos_trabajo(trabajo)
        texto = "**Conversión Cancelada**\n\nTu video fue eliminado de la cola correctamente."
        if callback_query:
            await callback_query.answer("Video eliminado de la cola", show_alert=False)
            try:
                await callback_query.message.edit_text(texto)
            except Exception:
                pass
        elif mensaje_respuesta:
            await mensaje_respuesta.reply_text(texto)
        return True

    texto = "**No hay operación pendiente para cancelar.**"
    if callback_query:
        await callback_query.answer("No tienes procesos pendientes", show_alert=True)
    elif mensaje_respuesta:
        await mensaje_respuesta.reply_text(texto)
    return False


@app.on_callback_query(filters.regex("^cancelar_conversion$"))
async def callback_cancelar_conversion(cliente: Client, callback_query: CallbackQuery):
    await cancelar_trabajo_usuario(callback_query.from_user.id, callback_query=callback_query)


@app.on_message(filters.command(["cancelar", "cancel"]))
async def comando_cancelar(cliente: Client, mensaje: Message):
    user_id = mensaje.from_user.id
    if user_id in estado_broadcast:
        del estado_broadcast[user_id]
        await mensaje.reply_text("**Operación de broadcast cancelada.**")
        return

    if user_id in estado_importacion_db:
        del estado_importacion_db[user_id]
        await mensaje.reply_text("**Importación de base de datos cancelada.**")
        return

    await cancelar_trabajo_usuario(user_id, mensaje_respuesta=mensaje)

def inicializar_sistema():
    try:
        Config.validar_configuracion()
    except ValueError as e:
        logger.error(f"Error de configuración: {e}")
        raise
    
    db.cargar_configuracion_desde_db()
    
    os.makedirs(Config.TEMP_DIR, exist_ok=True)
    
    logger.info("Bot de Conversión de Videos - INICIADO")
    logger.info(f"Administradores: {len(Config.ADMINISTRADORES)}")
    logger.info(f"Límite de peso: {Config.MAX_FILE_SIZE_MB}MB")
    logger.info(f"Procesos concurrentes: {Config.MAX_CONCURRENT_PROCESSES}")
    logger.info(f"Calidad: {Config.DEFAULT_QUALITY['resolution']} CRF{Config.DEFAULT_QUALITY['crf']}")
    logger.info("Base de datos JSON inicializada y configurada")
    logger.info("Sistema listo y operativo")

if __name__ == "__main__":
    inicializar_sistema()
    app.run()
