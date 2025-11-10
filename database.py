import sqlite3
import logging
import json
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)

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
                ('limite_peso_mb', str(config.MAX_FILE_SIZE_MB), 'Límite máximo de tamaño de archivo en MB'),
                ('max_concurrente', str(config.MAX_CONCURRENT_PROCESSES), 'Máximo de procesos concurrentes'),
                ('calidad_default', json.dumps(config.DEFAULT_QUALITY), 'Configuración de calidad por defecto'),
                ('mantenimiento', 'false', 'Modo mantenimiento del bot')
            ]
            
            cursor.executemany('''
                INSERT OR IGNORE INTO configuracion_sistema (clave, valor, descripcion)
                VALUES (?, ?, ?)
            ''', configuracion_por_defecto)
            
            # Insertar administradores por defecto
            for admin_id in config.ADMINISTRADORES:
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
    
    # ==================== MÉTODOS PARA USUARIOS ====================
    
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
    
    # ==================== MÉTODOS PARA VIDEOS ====================
    
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
            
            # Actualizar estadística de usuario
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
    
    # ==================== MÉTODOS PARA GRUPOS ====================
    
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
    
    # ==================== MÉTODOS PARA ESTADÍSTICAS ====================
    
    def obtener_estadisticas_generales(self):
        """Obtiene estadísticas generales del bot"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            # Total usuarios activos
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE es_activo = 1')
            total_usuarios = cursor.fetchone()[0]
            
            # Total videos convertidos
            cursor.execute('SELECT COUNT(*) FROM videos_convertidos')
            total_videos = cursor.fetchone()[0]
            
            # Total grupos autorizados
            cursor.execute('SELECT COUNT(*) FROM grupos_autorizados WHERE es_activo = 1')
            total_grupos = cursor.fetchone()[0]
            
            # Espacio ahorrado
            cursor.execute('''
                SELECT SUM(tamano_original - tamano_convertido) 
                FROM videos_convertidos 
                WHERE tamano_original > tamano_convertido
            ''')
            espacio_ahorrado = cursor.fetchone()[0] or 0
            
            # Tiempo total de procesamiento
            cursor.execute('SELECT SUM(tiempo_procesamiento) FROM videos_convertidos')
            tiempo_total = cursor.fetchone()[0] or 0
            
            # Usuarios más activos
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
