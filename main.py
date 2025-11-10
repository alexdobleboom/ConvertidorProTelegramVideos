import os
import asyncio
import shutil
import json
import time
import math
import datetime
import subprocess
import re
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from collections import deque
import threading
import psutil
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# ==================== CONFIGURACIÓN ====================
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

# Configurar logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== BASE DE DATOS ====================
class DatabaseManager:
    def __init__(self, archivo_db="bot_database.db"):
        self.archivo_db = archivo_db
        self.inicializar_base_datos()
    
    def obtener_conexion(self):
        """Obtiene conexión a la base de datos"""
        conn = sqlite3.connect(self.archivo_db)
        conn.row_factory = sqlite3.Row
        return conn
    
    def inicializar_base_datos(self):
        """Inicializa la base de datos con las tablas necesarias"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            # Tabla de usuarios
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                    fecha_ultimo_uso DATETIME DEFAULT CURRENT_TIMESTAMP,
                    total_conversiones INTEGER DEFAULT 0,
                    es_activo BOOLEAN DEFAULT 1
                )
            ''')
            
            # Tabla de administradores
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS administradores (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    nivel_permisos INTEGER DEFAULT 1,
                    fecha_agregado DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla de videos convertidos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS videos_convertidos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    nombre_archivo TEXT,
                    tamano_original INTEGER,
                    tamano_convertido INTEGER,
                    duracion_original TEXT,
                    duracion_convertido TEXT,
                    calidad_config TEXT,
                    tiempo_procesamiento REAL,
                    fecha_conversion DATETIME DEFAULT CURRENT_TIMESTAMP,
                    estado TEXT DEFAULT 'completado',
                    mensaje_error TEXT,
                    FOREIGN KEY (user_id) REFERENCES usuarios (user_id)
                )
            ''')
            
            # Tabla de grupos autorizados
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS grupos_autorizados (
                    chat_id INTEGER PRIMARY KEY,
                    titulo_grupo TEXT,
                    total_miembros INTEGER,
                    fecha_agregado DATETIME DEFAULT CURRENT_TIMESTAMP,
                    fecha_ultimo_uso DATETIME DEFAULT CURRENT_TIMESTAMP,
                    es_activo BOOLEAN DEFAULT 1
                )
            ''')
            
            # Tabla de configuración del sistema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS configuracion_sistema (
                    clave TEXT PRIMARY KEY,
                    valor TEXT,
                    descripcion TEXT,
                    fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insertar configuración por defecto
            configuracion_por_defecto = [
                ('limite_peso_mb', str(Config.MAX_FILE_SIZE_MB), 'Límite máximo de tamaño de archivo en MB'),
                ('max_concurrente', str(Config.MAX_CONCURRENT_PROCESSES), 'Máximo de procesos concurrentes'),
                ('calidad_default', json.dumps(Config.DEFAULT_QUALITY), 'Configuración de calidad por defecto'),
                ('mantenimiento', 'false', 'Modo mantenimiento del bot')
            ]
            
            cursor.executemany('''
                INSERT OR IGNORE INTO configuracion_sistema (clave, valor, descripcion)
                VALUES (?, ?, ?)
            ''', configuracion_por_defecto)
            
            # Insertar administradores por defecto
            for admin_id in Config.ADMINISTRADORES:
                cursor.execute('''
                    INSERT OR IGNORE INTO administradores (user_id, username, first_name)
                    VALUES (?, ?, ?)
                ''', (admin_id, "Administrador", "Admin"))
            
            conn.commit()
            logger.info("✅ Base de datos inicializada correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando base de datos: {e}")
            raise
        finally:
            conn.close()
    
    def agregar_actualizar_usuario(self, datos_usuario):
        """Agrega o actualiza un usuario en la base de datos"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO usuarios 
                (user_id, username, first_name, last_name, language_code, fecha_ultimo_uso)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                datos_usuario['user_id'],
                datos_usuario.get('username'),
                datos_usuario.get('first_name'),
                datos_usuario.get('last_name'),
                datos_usuario.get('language_code')
            ))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Error agregando usuario: {e}")
            return False
        finally:
            conn.close()
    
    def incrementar_conversion_usuario(self, user_id):
        """Incrementa el contador de conversiones de un usuario"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE usuarios 
                SET total_conversiones = total_conversiones + 1,
                    fecha_ultimo_uso = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (user_id,))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Error incrementando conversiones: {e}")
            return False
        finally:
            conn.close()
    
    def obtener_usuario(self, user_id):
        """Obtiene información de un usuario"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM usuarios WHERE user_id = ?', (user_id,))
            usuario = cursor.fetchone()
            
            return dict(usuario) if usuario else None
        except Exception as e:
            logger.error(f"❌ Error obteniendo usuario: {e}")
            return None
        finally:
            conn.close()
    
    def obtener_usuarios_activos(self):
        """Obtiene todos los usuarios activos"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('SELECT user_id FROM usuarios WHERE es_activo = 1')
            usuarios = [row['user_id'] for row in cursor.fetchall()]
            
            return set(usuarios)
        except Exception as e:
            logger.error(f"❌ Error obteniendo usuarios activos: {e}")
            return set()
        finally:
            conn.close()
    
    def agregar_video_convertido(self, datos_video):
        """Registra un video convertido en la base de datos"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO videos_convertidos 
                (user_id, nombre_archivo, tamano_original, tamano_convertido, 
                 duracion_original, duracion_convertido, calidad_config, tiempo_procesamiento)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datos_video['user_id'],
                datos_video['nombre_archivo'],
                datos_video['tamano_original'],
                datos_video['tamano_convertido'],
                datos_video.get('duracion_original', ''),
                datos_video.get('duracion_convertido', ''),
                datos_video.get('calidad_config', ''),
                datos_video.get('tiempo_procesamiento', 0)
            ))
            
            self.incrementar_conversion_usuario(datos_video['user_id'])
            
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Error agregando video: {e}")
            return None
        finally:
            conn.close()
    
    def obtener_historial_usuario(self, user_id, limite=10):
        """Obtiene el historial de conversiones de un usuario"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT nombre_archivo, tamano_original, tamano_convertido, 
                       fecha_conversion, tiempo_procesamiento
                FROM videos_convertidos 
                WHERE user_id = ? 
                ORDER BY fecha_conversion DESC 
                LIMIT ?
            ''', (user_id, limite))
            
            historial = []
            for row in cursor.fetchall():
                historial.append({
                    'nombre_archivo': row['nombre_archivo'],
                    'tamano_original': row['tamano_original'],
                    'tamano_convertido': row['tamano_convertido'],
                    'fecha_conversion': row['fecha_conversion'],
                    'tiempo_procesamiento': row['tiempo_procesamiento']
                })
            
            return historial
        except Exception as e:
            logger.error(f"❌ Error obteniendo historial: {e}")
            return []
        finally:
            conn.close()
    
    def agregar_actualizar_grupo(self, chat_id, titulo_grupo, total_miembros=0):
        """Agrega o actualiza un grupo en la base de datos"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO grupos_autorizados 
                (chat_id, titulo_grupo, total_miembros, fecha_ultimo_uso)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (chat_id, titulo_grupo, total_miembros))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Error agregando grupo: {e}")
            return False
        finally:
            conn.close()
    
    def obtener_estadisticas_generales(self):
        """Obtiene estadísticas generales del bot"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE es_activo = 1')
            total_usuarios = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM videos_convertidos')
            total_videos = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM grupos_autorizados WHERE es_activo = 1')
            total_grupos = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT SUM(tamano_original - tamano_convertido) 
                FROM videos_convertidos 
                WHERE tamano_original > tamano_convertido
            ''')
            espacio_ahorrado = cursor.fetchone()[0] or 0
            
            cursor.execute('SELECT SUM(tiempo_procesamiento) FROM videos_convertidos')
            tiempo_total = cursor.fetchone()[0] or 0
            
            cursor.execute('''
                SELECT first_name, total_conversiones 
                FROM usuarios 
                WHERE es_activo = 1 
                ORDER BY total_conversiones DESC 
                LIMIT 5
            ''')
            top_usuarios = [dict(row) for row in cursor.fetchall()]
            
            return {
                "total_usuarios": total_usuarios,
                "total_videos": total_videos,
                "total_grupos": total_grupos,
                "espacio_ahorrado": espacio_ahorrado,
                "tiempo_total_procesamiento": tiempo_total,
                "top_usuarios": top_usuarios
            }
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {}
        finally:
            conn.close()
    
    def obtener_configuracion(self, clave):
        """Obtiene una configuración del sistema"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('SELECT valor FROM configuracion_sistema WHERE clave = ?', (clave,))
            resultado = cursor.fetchone()
            
            return resultado['valor'] if resultado else None
        except Exception as e:
            logger.error(f"❌ Error obteniendo configuración: {e}")
            return None
        finally:
            conn.close()
    
    def actualizar_configuracion(self, clave, valor):
        """Actualiza una configuración del sistema"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE configuracion_sistema 
                SET valor = ?, fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE clave = ?
            ''', (valor, clave))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error actualizando configuración: {e}")
            return False
        finally:
            conn.close()

# ==================== SISTEMA DE COLAS ====================
class SistemaColas:
    def __init__(self, max_concurrente=3):
        self.cola_espera = deque()
        self.procesos_activos = {}
        self.max_concurrente = max_concurrente
        self.lock = threading.Lock()
        self.procesos_por_usuario = {}
        self.estadisticas = {
            "procesos_completados": 0,
            "errores": 0,
            "total_tiempo": 0,
            "inicio_sistema": time.time()
        }
        
    def agregar_trabajo(self, user_id, trabajo):
        with self.lock:
            if user_id in self.procesos_por_usuario:
                return "usuario_ocupado"
                
            if len(self.procesos_activos) < self.max_concurrente:
                self.procesos_activos[user_id] = trabajo
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
            if user_id in self.procesos_por_usuario:
                del self.procesos_por_usuario[user_id]
            
            if exito:
                self.estadisticas["procesos_completados"] += 1
            else:
                self.estadisticas["errores"] += 1
            self.estadisticas["total_tiempo"] += tiempo
            
            if self.cola_espera and len(self.procesos_activos) < self.max_concurrente:
                siguiente_user_id, siguiente_trabajo = self.cola_espera.popleft()
                self.procesos_activos[siguiente_user_id] = siguiente_trabajo
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

# ==================== INICIALIZACIÓN ====================
db = DatabaseManager()
sistema_colas = SistemaColas(max_concurrente=Config.MAX_CONCURRENT_PROCESSES)
app = Client("video_converter_bot", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN)

# ==================== FUNCIONES UTILITARIAS ====================
def obtener_duracion_video(ruta_video):
    """Obtiene la duración del video en segundos usando ffprobe."""
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
    """Formatea segundos a formato HH:MM:SS o MM:SS"""
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
        return f"📉 **Reducción:** `{reduccion:.1f}%`"
    elif reduccion < 0:
        return f"📈 **Aumento:** `{abs(reduccion):.1f}%`"
    else:
        return "⚖️ **Sin cambios**"

def tiene_acceso(user_id, tipo_chat=None):
    """Verifica si el usuario tiene acceso al bot"""
    if user_id in Config.ADMINISTRADORES:
        return True
    
    # Si es un grupo, todos los usuarios tienen acceso
    if tipo_chat in ["group", "supergroup"]:
        return True
    
    # Para chats privados, verificar en la base de datos
    usuarios_activos = db.obtener_usuarios_activos()
    return user_id in usuarios_activos

def generar_thumbnail(ruta_video, ruta_salida, tiempo='00:00:05'):
    """Genera un thumbnail del video"""
    try:
        duracion = obtener_duracion_video(ruta_video)
        if duracion <= 0:
            logger.error("No se pudo obtener la duración del video.")
            return False

        # Calcular el segundo de captura (1 segundo o la mitad del video)
        ss = min(1, duracion / 2)

        # Crear el comando ffmpeg
        comando = [
            "ffmpeg",
            "-ss", str(ss),
            "-i", ruta_video,
            "-vframes", "1",
            "-q:v", "2",  # calidad buena
            "-vf", "scale=320:240",
            ruta_salida,
            "-y"  # sobrescribir si ya existe
        ]
        
        subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return os.path.exists(ruta_salida)
    except Exception as e:
        logger.error(f"Error generando thumbnail: {e}")
        return False

def obtener_emoji_estado(porcentaje):
    if porcentaje < 50:
        return "🟢"
    elif porcentaje < 80:
        return "🟡"
    else:
        return "🔴"

def crear_barra_progreso(porcentaje, longitud=20):
    """Crea una barra de progreso visual"""
    bloques_llenos = int(porcentaje * longitud / 100)
    bloques_vacios = longitud - bloques_llenos
    return "█" * bloques_llenos + "░" * bloques_vacios

def extraer_error_ffmpeg(salida_error):
    """Extrae el mensaje de error real de la salida de FFmpeg"""
    lineas = salida_error.split('\n')
    for linea in reversed(lineas):
        linea = linea.strip()
        if linea and not linea.startswith('ffmpeg version') and not linea.startswith('built with') and not linea.startswith('configuration:'):
            if 'Error' in linea or 'error' in linea.lower() or 'failed' in linea.lower():
                return linea
    return '\n'.join(lineas[-3:]) if len(lineas) > 3 else salida_error

def parsear_tiempo_ffmpeg(cadena_tiempo):
    """Convierte el formato de tiempo de FFmpeg (HH:MM:SS.ms) a segundos"""
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

# ==================== CONVERSIÓN CON BARRA DE PROGRESO ====================
async def convertir_video_con_progreso(ruta_entrada, ruta_salida, duracion_total, actualizar_progreso):
    """Convierte video mostrando progreso en tiempo real"""
    try:
        if not shutil.which("ffmpeg"):
            return False, "FFmpeg no disponible"
        
        config_calidad = Config.DEFAULT_QUALITY
        
        comando = [
            'ffmpeg',
            '-i', ruta_entrada,
            '-c:v', config_calidad["codec"],
            '-preset', config_calidad["preset"],
            '-crf', config_calidad["crf"],
            '-r', config_calidad["fps"],
            '-c:a', 'aac',
            '-b:a', config_calidad["audio_bitrate"],
            '-movflags', '+faststart',
            '-threads', '0',
            '-max_muxing_queue_size', '1024',
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
            chunk = await proceso.stderr.read(1024)
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
        
        if proceso.returncode == 0 and os.path.exists(ruta_salida) and os.path.getsize(ruta_salida) > 0:
            return True, "Conversión completada"
        else:
            error_real = extraer_error_ffmpeg(buffer_error)
            return False, f"FFmpeg error: {error_real}"
            
    except asyncio.TimeoutError:
        return False, "Tiempo de conversión excedido"
    except Exception as e:
        return False, f"Error del sistema: {str(e)}"

async def procesar_video(cliente, mensaje, ruta_video, ruta_convertido, user_id):
    """Procesa el video con barra de progreso en tiempo real"""
    tiempo_inicio = time.time()
    mensaje_estado = None
    ruta_thumbnail = None
    
    async def actualizar_progreso(porcentaje, tiempo_actual=""):
        nonlocal mensaje_estado
        try:
            barra = crear_barra_progreso(porcentaje)
            texto_progreso = (
                f"🎬 **Convirtiendo Video**\n\n"
                f"📊 **Progreso:** {porcentaje:.1f}%\n"
                f"`{barra}`\n"
                f"⏱️ **Tiempo:** `{tiempo_actual}`\n\n"
                f"🔄 **Procesando...**"
            )
            if mensaje_estado:
                await mensaje_estado.edit_text(texto_progreso)
        except Exception:
            pass
    
    try:
        tamano_original = os.path.getsize(ruta_video)
        nombre_original = mensaje.video.file_name if mensaje.video else mensaje.document.file_name or "video"
        duracion_total = obtener_duracion_video(ruta_video)
        
        estadisticas = sistema_colas.obtener_estadisticas()
        
        mensaje_estado = await mensaje.reply_text(
            "🎬 **Iniciando Conversión**\n\n"
            f"📁 **Archivo:** `{nombre_original[:30]}...`\n"
            f"📊 **Tamaño:** `{formatear_tamano(tamano_original)}`\n"
            f"⏱️ **Duración:** `{formatear_tiempo(duracion_total)}`\n"
            f"⚡ **Procesos Activos:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n\n"
            "🔄 **Preparando...**"
        )
        
        await actualizar_progreso(5, "00:00:00")
        
        exito, log = await convertir_video_con_progreso(
            ruta_video, ruta_convertido, duracion_total, actualizar_progreso
        )
        
        tiempo_procesamiento = time.time() - tiempo_inicio

        if not exito:
            mensaje_error = ""
            if "Permission denied" in log:
                mensaje_error = "❌ **Error de Permisos**\nNo se puede acceder a los archivos temporales."
            elif "Invalid data" in log or "Unsupported codec" in log:
                mensaje_error = "❌ **Formato No Soportado**\nEl formato de video no es compatible."
            elif "Cannot allocate memory" in log:
                mensaje_error = "❌ **Memoria Insuficiente**\nEl sistema no tiene suficiente memoria."
            else:
                mensaje_error = f"❌ **Error en Conversión**\n\n`{log}`"
            
            await mensaje_estado.edit_text(
                f"{mensaje_error}\n\n"
                "💡 **Soluciones:**\n"
                "• Verifica el formato del archivo\n"
                "• Intenta con un video más pequeño\n"
                "• Usa `/soporte` para ayuda"
            )
            sistema_colas.trabajo_completado(user_id, False, tiempo_procesamiento)
            return

        await actualizar_progreso(100, "Completado")
        
        tamano_convertido = os.path.getsize(ruta_convertido)
        duracion_convertido = obtener_duracion_formateada(ruta_convertido)
        reduccion = calcular_reduccion(tamano_original, tamano_convertido)

        await mensaje_estado.edit_text(
            "✅ **Conversión Exitosa**\n\n"
            "📤 **Subiendo resultado...**\n"
            "🎉 **¡Casi listo!**"
        )

        db.agregar_video_convertido({
            'user_id': user_id,
            'nombre_archivo': nombre_original,
            'tamano_original': tamano_original,
            'tamano_convertido': tamano_convertido,
            'duracion_original': formatear_tiempo(duracion_total),
            'duracion_convertido': duracion_convertido,
            'calidad_config': json.dumps(Config.DEFAULT_QUALITY),
            'tiempo_procesamiento': tiempo_procesamiento
        })

        caption = (
            "✨ **Conversión Completada** ✨\n\n"
            f"📁 **Archivo:** `{nombre_original[:30]}...`\n"
            f"📊 **Original:** `{formatear_tamano(tamano_original)}`\n"
            f"🔄 **Convertido:** `{formatear_tamano(tamano_convertido)}`\n"
            f"{reduccion}\n"
            f"⏱️ **Tiempo:** `{formatear_tiempo(tiempo_procesamiento)}`\n"
            f"🎯 **Duración:** `{duracion_convertido}`\n"
            f"⚙️ **Calidad:** `{Config.DEFAULT_QUALITY['resolution']}`\n\n"
            f"🤖 **@{cliente.me.username}**"
        )

        if tamano_convertido > 10 * 1024 * 1024:
            ruta_thumbnail = f"thumb_{user_id}_{int(time.time())}.jpg"
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
        sistema_colas.trabajo_completado(user_id, True, tiempo_procesamiento)

    except Exception as e:
        mensaje_error = (
            "❌ **Error en Procesamiento**\n\n"
            f"**Detalles:** `{str(e)}`\n\n"
            "🆘 **Usa** `/soporte` **para reportar**"
        )
        try:
            if mensaje_estado:
                await mensaje_estado.edit_text(mensaje_error)
            else:
                await mensaje.reply_text(mensaje_error)
        except:
            pass
        sistema_colas.trabajo_completado(user_id, False, time.time() - tiempo_inicio)
    finally:
        if ruta_thumbnail and os.path.exists(ruta_thumbnail):
            try:
                os.remove(ruta_thumbnail)
            except:
                pass

# ==================== DECORADORES ====================
def verificar_acceso(func):
    async def wrapper(cliente, mensaje):
        user_id = mensaje.from_user.id
        tipo_chat = mensaje.chat.type
        
        db.agregar_actualizar_usuario({
            'user_id': user_id,
            'username': mensaje.from_user.username,
            'first_name': mensaje.from_user.first_name,
            'last_name': mensaje.from_user.last_name,
            'language_code': mensaje.from_user.language_code
        })
        
        if tipo_chat in ["group", "supergroup"]:
            db.agregar_actualizar_grupo(
                mensaje.chat.id,
                mensaje.chat.title,
                getattr(mensaje.chat, 'members_count', 0)
            )
        
        if not tiene_acceso(user_id, tipo_chat):
            await mensaje.reply_text(
                "🚫 **Acceso Restringido**\n\n"
                "📞 **Contacta al administrador**\n"
                "para solicitar acceso al bot."
            )
            return
        
        if tipo_chat in ["group", "supergroup"]:
            try:
                miembro_bot = await mensaje.chat.get_member(cliente.me.id)
                if not miembro_bot.status in ["administrator", "creator"]:
                    await mensaje.reply_text(
                        "🤖 **Se requieren privilegios de administrador**\n\n"
                        "Para usar el bot en grupos, debo ser administrador.\n"
                        "Por favor, otórgame permisos de administrador."
                    )
                    return
            except Exception as e:
                logger.error(f"Error verificando permisos de administrador: {e}")
                await mensaje.reply_text(
                    "❌ **Error verificando permisos**\n\n"
                    "No pude verificar mis permisos en este grupo."
                )
                return
        
        return await func(cliente, mensaje)
    return wrapper

# ==================== MANEJADOR DE VIDEOS ====================
@app.on_message(filters.video | filters.document)
@verificar_acceso
async def manejar_video(cliente: Client, mensaje: Message):
    user_id = mensaje.from_user.id
    
    try:
        if mensaje.document and not mensaje.document.mime_type.startswith('video'):
            await mensaje.reply_text(
                "❌ **Formato No Soportado**\n\n"
                "📁 **Envía un archivo de video válido**\n"
                "(MP4, AVI, MKV, MOV, etc.)"
            )
            return

        limite_bytes = Config.MAX_FILE_SIZE_MB * 1024 * 1024
        if mensaje.video:
            tamano_video = mensaje.video.file_size
        else:
            tamano_video = mensaje.document.file_size
            
        if tamano_video > limite_bytes:
            await mensaje.reply_text(
                "📏 **Límite Excedido**\n\n"
                f"📊 **Tu archivo:** `{formatear_tamano(tamano_video)}`\n"
                f"⚖️ **Límite permitido:** `{Config.MAX_FILE_SIZE_MB} MB`\n\n"
                "💡 **Reduce el tamaño del video**"
            )
            return

        ruta_video = await mensaje.download()
        ruta_convertido = f"convertido_{user_id}_{int(time.time())}.mp4"

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
            await mensaje.reply_text(
                "⚡ **Procesamiento Inmediato**\n\n"
                f"🎬 **Tu video ha comenzado a procesarse**\n"
                f"⚡ **Procesos activos:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
                f"📊 **En espera:** `{estadisticas['en_espera']}`\n\n"
                "⏳ **Recibirás el resultado pronto...**"
            )
            asyncio.create_task(
                procesar_y_limpiar(cliente, mensaje, ruta_video, ruta_convertido, user_id)
            )
        elif estado == "usuario_ocupado":
            await mensaje.reply_text(
                "⏳ **Usuario Ocupado**\n\n"
                "📨 **Ya tienes un video en proceso**\n"
                "🕐 **Espera a que termine antes de enviar otro**"
            )
            if os.path.exists(ruta_video):
                os.remove(ruta_video)
        else:
            posicion = estado.split('_')[1]
            await mensaje.reply_text(
                "📥 **Video Encolado**\n\n"
                f"🎯 **Posición en cola:** `#{posicion}`\n"
                f"⚡ **Procesos activos:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
                f"📊 **Personas en espera:** `{estadisticas['en_espera']}`\n\n"
                "🕐 **Será procesado en orden de llegada**"
            )
        
    except Exception as e:
        await mensaje.reply_text(
            "❌ **Error al Procesar**\n\n"
            f"**Detalles:** `{str(e)}`\n\n"
            "🆘 **Usa** `/soporte` **si el problema persiste**"
        )

async def procesar_y_limpiar(cliente, mensaje, ruta_video, ruta_convertido, user_id):
    try:
        await procesar_video(cliente, mensaje, ruta_video, ruta_convertido, user_id)
    except Exception as e:
        logger.error(f"Error en procesamiento: {e}")
    finally:
        for archivo in [ruta_video, ruta_convertido]:
            if archivo and os.path.exists(archivo):
                try:
                    os.remove(archivo)
                except:
                    pass
        
        siguiente_user_id, siguiente_trabajo = sistema_colas.trabajo_completado(user_id)
        if siguiente_trabajo:
            asyncio.create_task(
                procesar_y_limpiar(
                    siguiente_trabajo["cliente"],
                    siguiente_trabajo["mensaje"],
                    siguiente_trabajo["ruta_video"],
                    siguiente_trabajo["ruta_convertido"],
                    siguiente_user_id
                )
            )

# ==================== COMANDOS BÁSICOS ====================
@app.on_message(filters.command("start"))
@verificar_acceso
async def comando_inicio(cliente: Client, mensaje: Message):
    estadisticas = sistema_colas.obtener_estadisticas()
    estadisticas_bot = db.obtener_estadisticas_generales()
    
    texto = (
        "🤖 **Conversor de Videos Pro**\n\n"
        f"👋 **Hola {mensaje.from_user.first_name}!**\n\n"
        "🎯 **Características:**\n"
        "• Conversión a MP4 HD\n"
        "• Compresión inteligente\n"
        "• Sistema de colas avanzado\n"
        "• Barra de progreso en tiempo real\n"
        "• Base de datos integral\n\n"
        f"📏 **Límite por archivo:** `{Config.MAX_FILE_SIZE_MB} MB`\n"
        f"⚡ **Procesos simultáneos:** `{estadisticas['max_concurrente']}`\n"
        f"📊 **Videos convertidos:** `{estadisticas_bot['total_videos']}`\n\n"
        "🚀 **¿Cómo usar?**\n"
        "Simplemente envía cualquier video"
    )
    
    await mensaje.reply_text(texto)

@app.on_message(filters.command("help"))
@verificar_acceso
async def comando_ayuda(cliente: Client, mensaje: Message):
    texto = (
        "📚 **Centro de Ayuda**\n\n"
        "🎯 **Comandos Disponibles:**\n"
        "• `/start` - Iniciar el bot\n"
        "• `/help` - Mostrar ayuda\n"
        "• `/info` - Estado del sistema\n"
        "• `/cola` - Ver cola actual\n"
        "• `/historial` - Tu historial\n"
        "• `/estadisticas` - Stats del bot\n"
        "• `/soporte` - Reportar problema\n\n"
        "🔄 **Proceso Simple:**\n"
        "1. 📤 Envía el video\n"
        "2. ⚙️ Procesamiento automático\n"
        "3. 📥 Recibe el resultado\n\n"
        "📊 **Barra de Progreso:**\n"
        "• Progreso en tiempo real\n"
        "• Tiempo estimado\n"
        "• Estado actual\n\n"
        "🆘 **Soporte:**\n"
        "Usa `/soporte <mensaje>`\npara ayuda inmediata"
    )
    
    await mensaje.reply_text(texto)

@app.on_message(filters.command("info"))
@verificar_acceso
async def comando_info(cliente: Client, mensaje: Message):
    try:
        uso_cpu = psutil.cpu_percent()
        memoria = psutil.virtual_memory()
        disco = psutil.disk_usage('/')
        
        estadisticas = sistema_colas.obtener_estadisticas()
        estadisticas_bot = db.obtener_estadisticas_generales()
        es_admin = mensaje.from_user.id in Config.ADMINISTRADORES
        
        texto_info = (
            "📊 **Estado del Sistema**\n\n"
            
            "👤 **INFORMACIÓN DE USUARIO:**\n"
            f"• **Nombre:** {mensaje.from_user.first_name}\n"
            f"• **ID:** `{mensaje.from_user.id}`\n"
            f"• **Tipo:** {'👑 Administrador' if es_admin else '👤 Usuario'}\n\n"
            
            "🤖 **ESTADÍSTICAS DEL BOT:**\n"
            f"• **Usuarios activos:** `{estadisticas_bot['total_usuarios']}`\n"
            f"• **Grupos autorizados:** `{estadisticas_bot['total_grupos']}`\n"
            f"• **Videos convertidos:** `{estadisticas_bot['total_videos']}`\n"
            f"• **Espacio ahorrado:** `{formatear_tamano(estadisticas_bot['espacio_ahorrado'])}`\n"
            f"• **Límite actual:** `{Config.MAX_FILE_SIZE_MB} MB`\n"
            f"• **Procesos completados:** `{estadisticas['completados']}`\n"
            f"• **Tiempo promedio:** `{formatear_tiempo(estadisticas['tiempo_promedio'])}`\n\n"
            
            "⚡ **SISTEMA DE COLAS:**\n"
            f"• **Procesando ahora:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
            f"• **En espera:** `{estadisticas['en_espera']}`\n"
            f"• **Errores totales:** `{estadisticas['errores']}`\n\n"
            
            "⚙️ **CONFIGURACIÓN ACTUAL:**\n"
            f"• **Resolución:** `{Config.DEFAULT_QUALITY['resolution']}`\n"
            f"• **Calidad CRF:** `{Config.DEFAULT_QUALITY['crf']}`\n"
            f"• **Audio:** `{Config.DEFAULT_QUALITY['audio_bitrate']}`\n"
            f"• **FPS:** `{Config.DEFAULT_QUALITY['fps']}`\n\n"
            
            "🖥️ **ESTADO DEL SERVIDOR:**\n"
            f"{obtener_emoji_estado(uso_cpu)} **CPU:** `{uso_cpu}%`\n"
            f"{obtener_emoji_estado(memoria.percent)} **Memoria:** `{memoria.percent}%`\n"
            f"{obtener_emoji_estado(disco.percent)} **Almacenamiento:** `{disco.percent}%`\n"
            f"💾 **Libre:** `{formatear_tamano(disco.free)}`"
        )
        
    except Exception as e:
        logger.error(f"Error en info: {e}")
        estadisticas = sistema_colas.obtener_estadisticas()
        texto_info = (
            "📊 **Información del Sistema**\n\n"
            f"👤 **Usuario:** {mensaje.from_user.first_name}\n"
            f"📏 **Límite:** {Config.MAX_FILE_SIZE_MB}MB\n"
            f"⚡ **Procesos:** {estadisticas['procesando']}/{estadisticas['max_concurrente']}\n"
            f"📥 **En cola:** {estadisticas['en_espera']}\n"
            f"✅ **Completados:** {estadisticas['completados']}\n\n"
            "🟢 **Sistema operativo**"
        )
    
    await mensaje.reply_text(texto_info)

@app.on_message(filters.command("cola"))
@verificar_acceso
async def comando_cola(cliente: Client, mensaje: Message):
    estadisticas = sistema_colas.obtener_estadisticas()
    estado_usuario = sistema_colas.obtener_estado(mensaje.from_user.id)
    
    if estado_usuario == "procesando":
        emoji_estado = "⚡"
        texto_estado = "Procesando ahora"
    elif estado_usuario.startswith("encolado"):
        posicion = estado_usuario.split('_')[1]
        emoji_estado = "📥"
        texto_estado = f"En cola (posición #{posicion})"
    else:
        emoji_estado = "✅"
        texto_estado = "Sin procesos activos"
    
    texto = (
        "📊 **Estado de la Cola**\n\n"
        f"{emoji_estado} **Tu estado:** {texto_estado}\n\n"
        f"⚡ **Procesos activos:** `{estadisticas['procesando']}/{estadisticas['max_concurrente']}`\n"
        f"📥 **En espera:** `{estadisticas['en_espera']}`\n"
        f"✅ **Completados hoy:** `{estadisticas['completados']}`\n"
        f"⏱️ **Tiempo promedio:** `{formatear_tiempo(estadisticas['tiempo_promedio'])}`\n\n"
        "🔄 **El sistema procesa automáticamente**\n"
        "los videos por orden de llegada."
    )
    
    await mensaje.reply_text(texto)

# ==================== NUEVOS COMANDOS DE BASE DE DATOS ====================
@app.on_message(filters.command("historial"))
@verificar_acceso
async def comando_historial(cliente: Client, mensaje: Message):
    user_id = mensaje.from_user.id
    historial = db.obtener_historial_usuario(user_id, limite=5)
    
    if not historial:
        await mensaje.reply_text(
            "📝 **Historial de Conversiones**\n\n"
            "📭 **Aún no has convertido videos**\n"
            "Envía un video para comenzar!"
        )
        return
    
    texto = "📝 **Tus Últimas Conversiones**\n\n"
    
    for i, conversion in enumerate(historial, 1):
        reduccion = ((conversion['tamano_original'] - conversion['tamano_convertido']) / conversion['tamano_original']) * 100 if conversion['tamano_original'] > 0 else 0
        emoji = "📉" if reduccion > 0 else "📈" if reduccion < 0 else "⚖️"
        
        texto += (
            f"**{i}. {conversion['nombre_archivo'][:20]}...**\n"
            f"   📊 {formatear_tamano(conversion['tamano_original'])} → {formatear_tamano(conversion['tamano_convertido'])}\n"
            f"   {emoji} {abs(reduccion):.1f}% - {conversion['fecha_conversion'][:16]}\n\n"
        )
    
    await mensaje.reply_text(texto)

@app.on_message(filters.command("estadisticas"))
@verificar_acceso
async def comando_estadisticas(cliente: Client, mensaje: Message):
    estadisticas = db.obtener_estadisticas_generales()
    estadisticas_colas = sistema_colas.obtener_estadisticas()
    
    texto = (
        "📈 **Estadísticas del Bot**\n\n"
        "👥 **USUARIOS:**\n"
        f"• **Total usuarios:** `{estadisticas['total_usuarios']}`\n"
        f"• **Grupos activos:** `{estadisticas['total_grupos']}`\n\n"
        
        "🎬 **CONVERSIONES:**\n"
        f"• **Videos convertidos:** `{estadisticas['total_videos']}`\n"
        f"• **Espacio ahorrado:** `{formatear_tamano(estadisticas['espacio_ahorrado'])}`\n"
        f"• **Procesos exitosos:** `{estadisticas_colas['completados']}`\n"
        f"• **Errores:** `{estadisticas_colas['errores']}`\n\n"
        
        "⚡ **RENDIMIENTO:**\n"
        f"• **Tiempo promedio:** `{formatear_tiempo(estadisticas_colas['tiempo_promedio'])}`\n"
        f"• **Uptime:** `{formatear_tiempo(estadisticas_colas['uptime'])}`\n"
        f"• **Eficiencia:** `{(estadisticas_colas['completados'] / (estadisticas_colas['completados'] + estadisticas_colas['errores']) * 100) if (estadisticas_colas['completados'] + estadisticas_colas['errores']) > 0 else 0:.1f}%`"
    )
    
    await mensaje.reply_text(texto)

# ==================== COMANDOS DE SOPORTE ====================
@app.on_message(filters.command("soporte"))
@verificar_acceso
async def comando_soporte(cliente: Client, mensaje: Message):
    texto = mensaje.text.split(" ", 1)
    
    if len(texto) < 2:
        await mensaje.reply_text(
            "🆘 **Centro de Soporte**\n\n"
            "📝 **¿Necesitas ayuda?**\n\n"
            "**Uso correcto:**\n"
            "`/soporte <tu mensaje>`\n\n"
            "**Ejemplos:**\n"
            "• `/soporte El video no se convierte`\n"
            "• `/soporte Error con archivo MP4`\n"
            "• `/soporte La calidad es baja`\n\n"
            "⏰ **Respuesta rápida garantizada**"
        )
        return
    
    problema = texto[1]
    usuario = mensaje.from_user
    
    reporte = (
        "🆘 **Nuevo Reporte de Soporte**\n\n"
        f"👤 **Usuario:** {usuario.first_name}\n"
        f"🆔 **ID:** `{usuario.id}`\n"
        f"📅 **Hora:** {datetime.datetime.now().strftime('%H:%M')}\n\n"
        f"📝 **Problema:**\n{problema}\n\n"
        f"💬 **Mensaje original:**\n`{mensaje.text}`"
    )
    
    enviado = False
    for admin_id in Config.ADMINISTRADORES:
        try:
            await cliente.send_message(admin_id, reporte)
            enviado = True
        except Exception:
            continue
    
    if enviado:
        await mensaje.reply_text(
            "✅ **Reporte Enviado**\n\n"
            "📞 **Tu solicitud ha sido recibida**\n"
            "• Administradores notificados\n"
            "• Respuesta pronto\n"
            "• Ticket generado\n\n"
            "⏰ **Gracias por tu paciencia**"
        )
    else:
        await mensaje.reply_text(
            "❌ **Error al Enviar**\n\n"
            "No se pudo enviar tu reporte.\n"
            "Intenta nuevamente más tarde."
        )

# ==================== COMANDOS DE ADMINISTRADOR ====================
@app.on_message(filters.command("max"))
@verificar_acceso
async def comando_max(cliente: Client, mensaje: Message):
    if mensaje.from_user.id not in Config.ADMINISTRADORES:
        await mensaje.reply_text("🚫 **Solo administradores**")
        return
    
    texto = mensaje.text.split()
    
    if len(texto) != 2:
        await mensaje.reply_text(
            "📏 **Gestión de Límites**\n\n"
            f"⚖️ **Límite actual:** `{Config.MAX_FILE_SIZE_MB} MB`\n\n"
            "🔄 **Para modificar:**\n"
            "`/max <nuevo_límite_en_MB>`\n\n"
            "💡 **Ejemplos:**\n"
            "• `/max 500` - 500 MB\n"
            "• `/max 100` - 100 MB\n"
            "• `/max 2000` - 2 GB\n\n"
            "⚠️ **Límites:** 10MB - 5000MB"
        )
        return
    
    try:
        nuevo_limite = int(texto[1])
        
        if nuevo_limite < 10:
            await mensaje.reply_text("❌ **Mínimo 10MB**")
            return
            
        if nuevo_limite > 5000:
            await mensaje.reply_text("❌ **Máximo 5000MB**")
            return
        
        db.actualizar_configuracion('limite_peso_mb', str(nuevo_limite))
        
        await mensaje.reply_text(
            "✅ **Límite Actualizado**\n\n"
            f"📊 **Cambios realizados:**\n"
            f"• **Antes:** `{Config.MAX_FILE_SIZE_MB} MB`\n"
            f"• **Ahora:** `{nuevo_limite} MB`\n\n"
            f"👥 **Afecta a todos los usuarios**\n"
            f"🎯 **Aplicable inmediatamente**"
        )
        
    except ValueError:
        await mensaje.reply_text(
            "❌ **Error de Formato**\n\n"
            "El límite debe ser un número.\n\n"
            "📝 **Ejemplo correcto:**\n"
            "`/max 500`"
        )

@app.on_message(filters.command("calidad"))
@verificar_acceso
async def comando_calidad(cliente: Client, mensaje: Message):
    if mensaje.from_user.id not in Config.ADMINISTRADORES:
        await mensaje.reply_text("🚫 **Solo administradores**")
        return
    
    texto = mensaje.text.split()
    
    if len(texto) == 1:
        await mensaje.reply_text(
            f"⚙️ **Calidad Actual**\n\n"
            f"🖼️ **Resolución:** `{Config.DEFAULT_QUALITY['resolution']}`\n"
            f"🎯 **CRF:** `{Config.DEFAULT_QUALITY['crf']}` (0-51, menor es mejor)\n"
            f"🔊 **Audio:** `{Config.DEFAULT_QUALITY['audio_bitrate']}`\n"
            f"📺 **FPS:** `{Config.DEFAULT_QUALITY['fps']}`\n"
            f"⚡ **Preset:** `{Config.DEFAULT_QUALITY['preset']}`\n"
            f"🔧 **Codec:** `{Config.DEFAULT_QUALITY['codec']}`\n\n"
            "🔄 **Para modificar:**\n"
            "`/calidad parametro=valor`\n\n"
            "💡 **Ejemplo:**\n"
            "`/calidad resolution=1920x1080 crf=18`"
        )
        return
    
    try:
        parametros = " ".join(texto[1:]).split()
        cambios = []
        
        for param in parametros:
            if '=' in param:
                key, value = param.split('=', 1)
                if key in Config.DEFAULT_QUALITY:
                    valor_anterior = Config.DEFAULT_QUALITY[key]
                    Config.DEFAULT_QUALITY[key] = value
                    cambios.append(f"• **{key}:** `{valor_anterior}` → `{value}`")
        
        if cambios:
            db.actualizar_configuracion('calidad_default', json.dumps(Config.DEFAULT_QUALITY))
            respuesta = "✅ **Configuración Actualizada**\n\n" + "\n".join(cambios)
        else:
            respuesta = "❌ **Sin cambios**\nNo se encontraron parámetros válidos."
        
        await mensaje.reply_text(respuesta)
        
    except Exception as e:
        await mensaje.reply_text(f"❌ **Error**\n`{str(e)}`")

@app.on_message(filters.command("add"))
@verificar_acceso
async def comando_add(cliente: Client, mensaje: Message):
    if mensaje.from_user.id not in Config.ADMINISTRADORES:
        await mensaje.reply_text("🚫 **Solo administradores**")
        return
    
    texto = mensaje.text.split()
    
    if len(texto) != 2:
        await mensaje.reply_text(
            "👥 **Agregar Usuario**\n\n"
            "**Uso:** `/add @usuario`\n"
            "**Ejemplo:** `/add @nombreusuario`\n\n"
            "📝 **También puedes usar ID:**\n"
            "`/add 123456789`"
        )
        return
    
    objetivo = texto[1]
    
    try:
        if objetivo.startswith('@'):
            user = await cliente.get_users(objetivo)
        else:
            user = await cliente.get_users(int(objetivo))
        
        db.agregar_actualizar_usuario({
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        })
        
        await mensaje.reply_text(f"✅ **{user.first_name} agregado**")
        
    except Exception as e:
        await mensaje.reply_text(f"❌ **Error**\n`{str(e)}`")

@app.on_message(filters.command("usuarios"))
@verificar_acceso
async def comando_usuarios(cliente: Client, mensaje: Message):
    if mensaje.from_user.id not in Config.ADMINISTRADORES:
        await mensaje.reply_text("🚫 **Solo administradores**")
        return
    
    usuarios_activos = db.obtener_usuarios_activos()
    
    if not usuarios_activos:
        await mensaje.reply_text("👥 **Lista vacía**")
        return
    
    texto = "👥 **Usuarios Permitidos**\n\n"
    for i, user_id in enumerate(list(usuarios_activos)[:15], 1):
        try:
            user = await cliente.get_users(user_id)
            texto += f"• {user.first_name} - `{user_id}`\n"
        except:
            texto += f"• `{user_id}`\n"
    
    texto += f"\n**Total:** {len(usuarios_activos)}"
    
    await mensaje.reply_text(texto)

# ==================== INICIALIZACIÓN ====================
def inicializar_sistema():
    # Validar configuración
    try:
        Config.validar_configuracion()
    except ValueError as e:
        logger.error(f"❌ Error de configuración: {e}")
        raise
    
    # Crear directorio temporal si no existe
    os.makedirs(Config.TEMP_DIR, exist_ok=True)
    
    logger.info("🎬 Bot de Conversión de Videos - INICIADO")
    logger.info(f"👑 Administradores: {len(Config.ADMINISTRADORES)}")
    logger.info(f"📏 Límite de peso: {Config.MAX_FILE_SIZE_MB}MB")
    logger.info(f"⚡ Procesos concurrentes: {Config.MAX_CONCURRENT_PROCESSES}")
    logger.info("🗄️ Base de datos inicializada")
    logger.info("🟢 Sistema listo y operativo")

if __name__ == "__main__":
    inicializar_sistema()
    app.run()
