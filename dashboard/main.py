import os
import json
import random
import logging
import hashlib
import secrets
import time
import requests
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session, render_template_string, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from functools import wraps
from collections import defaultdict

# Logging más detallado para debug
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths y constantes
BASE_DIR      = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'videos')
CONFIG_FILE   = os.path.join(BASE_DIR, 'config.json')
ALLOWED_EXT   = {'mp4', 'webm', 'mov', 'avi', 'mkv'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# ================================
# CONFIGURACIÓN DEL BACKEND PISCINA
# ================================
PISCINA_API_URL = os.environ.get('PISCINA_API_URL', 'http://45.157.200.7:8080/piscina')
PISCINA_API_KEY = os.environ.get('PISCINA_API_KEY', 'SmartCity_GO_2025_Secret_X99')

# Asegurarse de que existan los directorios
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'static'), exist_ok=True)

# Crear la aplicación Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_urlsafe(32))
app.config['UPLOAD_FOLDER']       = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH']  = MAX_FILE_SIZE

# Log de configuración inicial
logger.info(f"📁 BASE_DIR: {BASE_DIR}")
logger.info(f"📁 UPLOAD_FOLDER: {UPLOAD_FOLDER}")
logger.info(f"📋 CONFIG_FILE: {CONFIG_FILE}")
logger.info(f"🏊 PISCINA_API_URL: {PISCINA_API_URL}")

# ================================
# CONFIGURACIÓN DE SEGURIDAD ADMIN
# ================================

# ¡IMPORTANTE! Cambia esta password por la tuya
ADMIN_PASSWORD = "admin2024"  # <-- CAMBIAR ESTA PASSWORD
ADMIN_PASSWORD_HASH = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
SESSION_TIMEOUT = 3600  # 1 hora en segundos

# Control de intentos fallidos
failed_attempts = defaultdict(int)
lockout_until = defaultdict(float)

def admin_required(f):
    """Decorador para proteger rutas admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.debug(f"🔒 Verificando acceso admin para: {request.path}")
        
        # Verificar si está logueado
        if not session.get('admin_logged_in'):
            logger.warning(f"❌ Acceso denegado a {request.path} - No logueado")
            flash('Debes iniciar sesión para acceder al panel de administración.', 'error')
            return redirect(url_for('admin_login'))
        
        # Verificar si la sesión no ha expirado
        login_time = session.get('login_time', 0)
        if time.time() - login_time > SESSION_TIMEOUT:
            logger.warning(f"⏰ Sesión expirada para {request.path}")
            session.clear()
            flash('Tu sesión ha expirado. Por favor, inicia sesión nuevamente.', 'error')
            return redirect(url_for('admin_login'))
        
        logger.debug(f"✅ Acceso autorizado a {request.path}")
        return f(*args, **kwargs)
    return decorated_function

def check_lockout(client_ip):
    """Verificar si la IP está bloqueada por intentos fallidos"""
    if client_ip in lockout_until:
        if time.time() < lockout_until[client_ip]:
            return True
        else:
            # Limpiar bloqueo expirado
            del lockout_until[client_ip]
            failed_attempts[client_ip] = 0
    return False

def record_failed_attempt(client_ip):
    """Registrar intento fallido y bloquear si es necesario"""
    failed_attempts[client_ip] += 1
    
    if failed_attempts[client_ip] >= 3:  # Máximo 3 intentos
        lockout_until[client_ip] = time.time() + (15 * 60)  # Bloquear 15 minutos
        logger.warning(f"🚫 IP {client_ip} bloqueada por 15 minutos tras {failed_attempts[client_ip]} intentos fallidos")

def log_admin_access(client_ip, action):
    """Registrar accesos al panel de administración"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] IP: {client_ip} - Action: {action}\n"
    
    try:
        log_dir = os.path.join(BASE_DIR, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, 'admin_access.log'), 'a') as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"❌ Error escribiendo log: {e}")
        print(f"📝 Admin access: {log_entry.strip()}")

# ================================
# FUNCIONES AUXILIARES
# ================================

def ensure_config_exists():
    """Crear config.json con valores por defecto si no existe"""
    if not os.path.exists(CONFIG_FILE):
        default = {"slides":[{"id":1,"type":"data","enabled":True,"duration":30}]}
        save_config(default)
        logger.info("📋 config.json creado con valores por defecto")

def load_config():
    """Cargar configuración desde config.json"""
    ensure_config_exists()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.debug(f"📋 Config cargado: {len(config.get('slides', []))} slides")
            return config
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"❌ Error cargando config.json: {e}")
        return {"slides":[]}

def save_config(conf):
    """Guardar configuración en config.json"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(conf, f, indent=2, ensure_ascii=False)
        logger.info("💾 Configuración guardada correctamente")
    except Exception as e:
        logger.error(f"❌ Error guardando config.json: {e}")

def allowed_file(filename):
    """Verificar si el archivo tiene una extensión permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def get_next_slide_id():
    """Obtener el siguiente ID disponible para un slide"""
    config = load_config()
    if not config['slides']:
        return 1
    return max(slide['id'] for slide in config['slides']) + 1

# =======================================================
# OBTENCIÓN DE DATOS (HÍBRIDO: API REAL + MOCK FALLBACK)
# =======================================================

# --- Funciones Mock (Fallback cuando la API no responde) ---

def _generate_mock_pool():
    """Datos mock de piscina - Solo se usa si la API real falla"""
    return {
        "ph": round(random.uniform(7.2, 7.6), 2),
        "cloro_libre": round(random.uniform(1.0, 1.5), 2),
        "cloro_total": round(random.uniform(1.2, 1.8), 2),
        "turbidez_ntu": round(random.uniform(0.1, 0.5), 2),
        "temperatura_agua": round(random.uniform(26.0, 28.5), 1),
        "source": "mock",
        "ultimo_dato": None
    }

def _generate_mock_people():
    return {"total_complejo": random.randint(80, 150), "sala_gimnasio": random.randint(15, 40)}

def _generate_mock_solar():
    hour = datetime.now().hour
    g = random.randint(3000, 5500) if 6 <= hour <= 18 else 0
    c = random.randint(2800, 4800)
    return {"generated_kwh": g, "consumed_kwh": c, "import_export_ratio": round(g/c, 2) if c > 0 else 0}

def _generate_mock_air():
    return {"no2": random.randint(15, 45), "o3": random.randint(50, 120), "source": "mock"}

def _generate_mock_co2():
    return {"co2": random.randint(400, 800), "time": datetime.now().isoformat(), "source": "mock"}

def _generate_mock_thr():
    return {"temperature": round(random.uniform(20, 26), 1), "humidity": round(random.uniform(0.4, 0.7), 2), "source": "mock"}

# --- Helper genérico para peticiones API ---

def fetch_api_data(url, fallback_func, timeout=5, headers=None):
    """Helper genérico para peticiones seguras con fallback"""
    try:
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        if isinstance(data, dict):
            data['source'] = 'api_real'
            
        logger.info(f"✅ Datos obtenidos OK de: {url}")
        return data
        
    except requests.Timeout:
        logger.warning(f"⏱️ Timeout conectando a API ({url}). USANDO FALLBACK.")
        return fallback_func()
    except requests.ConnectionError:
        logger.warning(f"🔌 Error de conexión a API ({url}). USANDO FALLBACK.")
        return fallback_func()
    except requests.HTTPError as e:
        logger.warning(f"❌ HTTP Error {e.response.status_code} de API ({url}). USANDO FALLBACK.")
        return fallback_func()
    except json.JSONDecodeError:
        logger.warning(f"📄 Respuesta no es JSON válido de ({url}). USANDO FALLBACK.")
        return fallback_func()
    except Exception as e:
        logger.warning(f"⚠️ Error inesperado conectando a API ({url}): {str(e)}. USANDO FALLBACK.")
        return fallback_func()

# --- Funciones Principales de Obtención de Datos ---

def get_air_quality():
    """Obtener datos de calidad del aire desde API municipal"""
    url = "https://app.alcoi.org/iot/api/v1/tiempo_real/Alcoy_AQPMNGPRS_01"
    return fetch_api_data(url, _generate_mock_air)

def get_co2():
    """Obtener datos de CO2 desde API municipal"""
    url = "https://app.alcoi.org/iot/api/v1/tiempo_real/CF1_Sonda1_CO2"
    return fetch_api_data(url, _generate_mock_co2)

def get_thr():
    """Obtener datos de temperatura/humedad desde API municipal"""
    url = "https://app.alcoi.org/iot/api/v1/tiempo_real/CF1_Sonda1_THR"
    return fetch_api_data(url, _generate_mock_thr)

def get_pool_data():
    """
    ✅ NUEVO: Obtener datos REALES de la piscina desde tu backend Node.js
    
    Conecta con: http://45.157.200.7:8080/piscina
    Autenticación: x-api-key header
    """
    headers = {"x-api-key": PISCINA_API_KEY}
    
    try:
        response = requests.get(PISCINA_API_URL, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # Mapear los nombres de tu API al formato esperado por el dashboard
        pool_data = {
            "ph": data.get("ph"),
            "cloro_libre": data.get("cloro_libre"),
            "cloro_total": data.get("cloro_total"),
            "turbidez_ntu": data.get("turbidez"),
            "temperatura_agua": data.get("temp"),
            "source": "api_real",
            "ultimo_dato": data.get("ultimo_dato"),
            "serial_device": data.get("serial_device")
        }
        
        logger.info(f"✅ Datos de piscina obtenidos desde backend: pH={pool_data['ph']}, Temp={pool_data['temperatura_agua']}°C")
        return pool_data
        
    except requests.Timeout:
        logger.warning(f"⏱️ Timeout conectando a backend piscina ({PISCINA_API_URL}). USANDO FALLBACK.")
        return _generate_mock_pool()
    except requests.ConnectionError:
        logger.warning(f"🔌 No se pudo conectar al backend piscina ({PISCINA_API_URL}). USANDO FALLBACK.")
        return _generate_mock_pool()
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            logger.error(f"🔐 API Key inválida para backend piscina. Verifica PISCINA_API_KEY.")
        else:
            logger.warning(f"❌ HTTP Error {e.response.status_code} del backend piscina. USANDO FALLBACK.")
        return _generate_mock_pool()
    except Exception as e:
        logger.warning(f"⚠️ Error inesperado obteniendo datos de piscina: {str(e)}. USANDO FALLBACK.")
        return _generate_mock_pool()

def get_people_count():
    """Obtener conteo de personas - Actualmente mock (pendiente de integración)"""
    return _generate_mock_people()

def get_solar_data():
    """Obtener datos solares - Actualmente mock (pendiente de integración)"""
    return _generate_mock_solar()

# ================================
# MIDDLEWARE DE DEBUG
# ================================

@app.before_request
def log_request_info():
    """Log detallado de todas las peticiones para debug"""
    logger.debug(f"🌐 {request.method} {request.path} - IP: {request.remote_addr}")
    if request.method == 'POST':
        logger.debug(f"🌐 Form data: {dict(request.form)}")
        logger.debug(f"🌐 Files: {list(request.files.keys())}")

@app.after_request
def log_response_info(response):
    """Log respuestas para debug"""
    logger.debug(f"📤 Response: {response.status_code} for {request.path}")
    return response

# ================================
# RUTAS PÚBLICAS (SIN AUTENTICACIÓN)
# ================================

@app.route('/data')
def data():
    """Endpoint para obtener datos en tiempo real (API Real o Fallback)"""
    logger.debug("📊 Solicitando datos unificados...")
    
    payload = {
        "air": get_air_quality(),
        "co2": get_co2(),
        "thr": get_thr(),
        "pool": get_pool_data(),  # ← Ahora conecta con tu backend real
        "people": get_people_count(),
        "solar": get_solar_data(),
        "timestamp": datetime.now().isoformat()
    }
    
    # Log del source de cada dato para debug
    sources = {k: v.get('source', 'unknown') for k, v in payload.items() if isinstance(v, dict)}
    logger.info(f"📊 Fuentes de datos: {sources}")
    
    return jsonify(payload)

@app.route('/config')
def config():
    """Endpoint para obtener configuración de slides"""
    logger.debug("📋 Enviando configuración de slides...")
    config_data = load_config()
    return jsonify(config_data)

@app.route('/health')
def health():
    """Endpoint de estado del sistema"""
    logger.debug("🏥 Verificando estado del sistema...")
    config = load_config()
    video_files = []
    
    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            if allowed_file(filename):
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                size = os.path.getsize(filepath)
                video_files.append({
                    'filename': filename,
                    'size_mb': round(size / (1024*1024), 2)
                })
    
    # Verificar conectividad con backend piscina
    piscina_status = "unknown"
    try:
        headers = {"x-api-key": PISCINA_API_KEY}
        resp = requests.get(PISCINA_API_URL, headers=headers, timeout=3)
        piscina_status = "ok" if resp.status_code == 200 else f"error_{resp.status_code}"
    except:
        piscina_status = "unreachable"
    
    health_data = {
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'slides_count': len(config.get('slides', [])),
        'enabled_slides': len([s for s in config.get('slides', []) if s.get('enabled', False)]),
        'video_files': video_files,
        'upload_folder': UPLOAD_FOLDER,
        'backend_piscina': {
            'url': PISCINA_API_URL,
            'status': piscina_status
        }
    }
    
    logger.debug(f"🏥 Health data: {health_data}")
    return jsonify(health_data)

@app.route('/')
def index():
    """Página principal del dashboard"""
    logger.debug("🏠 Sirviendo página principal...")
    return render_template('index.html')

@app.route('/static/videos/<filename>')
def serve_video(filename):
    """Servir archivos de video estáticamente"""
    logger.debug(f"🎥 Solicitado video: {filename}")
    try:
        video_path = os.path.join(UPLOAD_FOLDER, filename)
        
        if not os.path.exists(video_path):
            logger.error(f"❌ Video no encontrado: {video_path}")
            return "Video no encontrado", 404
            
        if not allowed_file(filename):
            logger.error(f"❌ Tipo de archivo no permitido: {filename}")
            return "Tipo de archivo no permitido", 403
        
        logger.info(f"✅ Sirviendo video: {filename}")
        return send_from_directory(UPLOAD_FOLDER, filename)
        
    except Exception as e:
        logger.error(f"❌ Error sirviendo video {filename}: {e}")
        return f"Error sirviendo video: {str(e)}", 500

# ================================
# RUTAS DE AUTENTICACIÓN ADMIN
# ================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Página de login del administrador"""
    logger.debug(f"🔐 Login admin - Método: {request.method}")
    client_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
    
    if check_lockout(client_ip):
        remaining_time = int((lockout_until[client_ip] - time.time()) / 60)
        logger.warning(f"🚫 IP bloqueada: {client_ip}, quedan {remaining_time} minutos")
        return render_template_string(LOCKOUT_TEMPLATE, remaining_time=remaining_time), 429
    
    if session.get('admin_logged_in'):
        logger.debug("✅ Ya logueado, redirigiendo al panel")
        return redirect(url_for('admin_panel'))
    
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        
        if password:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            if password_hash == ADMIN_PASSWORD_HASH:
                session['admin_logged_in'] = True
                session['login_time'] = time.time()
                session['admin_ip'] = client_ip
                
                failed_attempts[client_ip] = 0
                if client_ip in lockout_until:
                    del lockout_until[client_ip]
                
                flash('¡Bienvenido al panel de administración!', 'success')
                log_admin_access(client_ip, 'LOGIN_SUCCESS')
                logger.info(f"✅ Login exitoso desde IP: {client_ip}")
                
                return redirect(url_for('admin_panel'))
            else:
                record_failed_attempt(client_ip)
                log_admin_access(client_ip, 'LOGIN_FAILED')
                logger.warning(f"❌ Login fallido desde IP: {client_ip}")
                
                remaining_attempts = 3 - failed_attempts[client_ip]
                if remaining_attempts > 0:
                    flash(f'Contraseña incorrecta. Te quedan {remaining_attempts} intentos.', 'error')
                else:
                    flash('Demasiados intentos fallidos. Acceso bloqueado por 15 minutos.', 'error')
        else:
            flash('Por favor, introduce una contraseña.', 'error')
    
    return render_template_string(LOGIN_TEMPLATE, 
                                attempts=failed_attempts[client_ip],
                                max_attempts=3)

@app.route('/admin/logout')
def admin_logout():
    """Cerrar sesión del administrador"""
    client_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
    log_admin_access(client_ip, 'LOGOUT')
    logger.info(f"👋 Logout desde IP: {client_ip}")
    
    session.clear()
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('admin_login'))

# ================================
# RUTAS ADMIN PROTEGIDAS
# ================================

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin_panel():
    """Panel principal de administración"""
    logger.debug(f"🎛️ Accediendo al panel admin con método: {request.method}")
    
    if request.method == 'POST':
        return admin_config()
    
    conf = load_config()
    login_time = session.get('login_time', 0)
    session_duration = int((time.time() - login_time) / 60)
    
    # Obtener estado del backend piscina para mostrarlo en el panel
    piscina_status = "checking..."
    try:
        headers = {"x-api-key": PISCINA_API_KEY}
        resp = requests.get(PISCINA_API_URL, headers=headers, timeout=3)
        if resp.status_code == 200:
            piscina_data = resp.json()
            piscina_status = f"✅ Conectado (Último dato: {piscina_data.get('ultimo_dato', 'N/A')})"
        else:
            piscina_status = f"❌ Error HTTP {resp.status_code}"
    except requests.Timeout:
        piscina_status = "⏱️ Timeout"
    except requests.ConnectionError:
        piscina_status = "🔌 Sin conexión"
    except Exception as e:
        piscina_status = f"⚠️ Error: {str(e)}"
    
    return render_template('admin.html', 
                         config=conf, 
                         allowed_ext_str=','.join('.'+e for e in ALLOWED_EXT),
                         session_duration=session_duration,
                         client_ip=session.get('admin_ip'),
                         piscina_api_url=PISCINA_API_URL,
                         piscina_status=piscina_status)

@app.route('/admin/config', methods=['POST'])
@admin_required
def admin_config():
    """Actualizar configuración del sistema"""
    logger.debug("⚙️ Actualizando configuración...")
    
    try:
        conf = load_config()
        
        for slide in conf['slides']:
            sid = str(slide['id'])
            slide['enabled'] = (request.form.get(f'enabled_{sid}') == 'on')
            
            if slide['type'] == 'data':
                try:
                    duration = int(request.form.get(f'duration_{sid}', 30))
                    slide['duration'] = max(10, min(300, duration))
                except (ValueError, TypeError):
                    slide['duration'] = 30
        
        save_config(conf)
        log_admin_access(session.get('admin_ip'), 'CONFIG_UPDATE')
        flash('Configuración guardada correctamente.', 'success')
        logger.info("✅ Configuración actualizada exitosamente")
        
    except Exception as e:
        logger.error(f"❌ Error actualizando configuración: {e}")
        flash('Error al guardar la configuración.', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/upload', methods=['POST'])
@admin_required
def upload_video():
    """Subir nuevo video"""
    logger.debug("📤 Iniciando upload de video...")
    
    try:
        if 'file' not in request.files:
            flash('No se seleccionó ningún archivo.', 'error')
            return redirect(url_for('admin_panel'))
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No se seleccionó ningún archivo.', 'error')
            return redirect(url_for('admin_panel'))
        
        if not allowed_file(file.filename):
            flash(f'Tipo de archivo no permitido. Use: {", ".join(ALLOWED_EXT)}', 'error')
            return redirect(url_for('admin_panel'))
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if os.path.exists(filepath):
            flash(f'Ya existe un archivo con el nombre "{filename}".', 'error')
            return redirect(url_for('admin_panel'))
        
        file.save(filepath)
        logger.info(f"✅ Video guardado: {filename}")
        
        if not os.path.exists(filepath):
            flash('Error: El archivo no se pudo guardar.', 'error')
            return redirect(url_for('admin_panel'))
        
        config = load_config()
        new_slide = {
            "id": get_next_slide_id(),
            "type": "video",
            "enabled": True,
            "filename": filename
        }
        config['slides'].append(new_slide)
        save_config(config)
        
        log_admin_access(session.get('admin_ip'), f'VIDEO_UPLOAD:{filename}')
        flash(f'Video "{filename}" subido y configurado correctamente.', 'success')
        
    except RequestEntityTooLarge:
        flash(f'El archivo es demasiado grande. Máximo: {MAX_FILE_SIZE // (1024*1024)}MB', 'error')
    except Exception as e:
        logger.error(f"❌ Error subiendo video: {e}")
        flash('Error al subir el video. Inténtelo de nuevo.', 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete/<int:slide_id>', methods=['POST'])
@admin_required
def delete_slide(slide_id):
    """Eliminar slide (y archivo de video si aplica)"""
    logger.debug(f"🗑️ Eliminando slide: {slide_id}")
    
    try:
        config = load_config()
        
        slide_to_delete = None
        for slide in config['slides']:
            if slide['id'] == slide_id:
                slide_to_delete = slide
                break
        
        if not slide_to_delete:
            flash('Slide no encontrado.', 'error')
            return redirect(url_for('admin_panel'))
        
        data_slides = [s for s in config['slides'] if s['type'] == 'data']
        if slide_to_delete['type'] == 'data' and len(data_slides) == 1:
            flash('No se puede eliminar el único slide de datos.', 'error')
            return redirect(url_for('admin_panel'))
        
        if slide_to_delete['type'] == 'video':
            filename = slide_to_delete.get('filename')
            if filename:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                        logger.info(f"✅ Archivo eliminado: {filename}")
                    except Exception as e:
                        logger.error(f"❌ Error eliminando archivo {filename}: {e}")
                        flash(f'Slide eliminado pero error al borrar archivo: {e}', 'warning')
        
        config['slides'] = [s for s in config['slides'] if s['id'] != slide_id]
        save_config(config)
        
        log_admin_access(session.get('admin_ip'), f'SLIDE_DELETE:{slide_id}')
        slide_type = "video" if slide_to_delete['type'] == 'video' else "datos"
        flash(f'Slide de {slide_type} eliminado correctamente.', 'success')
        
    except Exception as e:
        logger.error(f"❌ Error eliminando slide {slide_id}: {e}")
        flash('Error al eliminar el slide.', 'error')
    
    return redirect(url_for('admin_panel'))

# ================================
# ENDPOINT DE TEST PARA PISCINA
# ================================

@app.route('/test/piscina')
def test_piscina():
    """
    Endpoint de diagnóstico para verificar la conexión con el backend de piscina.
    Útil para debugging sin necesidad de autenticación admin.
    """
    result = {
        "url": PISCINA_API_URL,
        "api_key_configured": bool(PISCINA_API_KEY),
        "api_key_length": len(PISCINA_API_KEY) if PISCINA_API_KEY else 0,
        "test_time": datetime.now().isoformat()
    }
    
    try:
        headers = {"x-api-key": PISCINA_API_KEY}
        response = requests.get(PISCINA_API_URL, headers=headers, timeout=5)
        
        result["http_status"] = response.status_code
        result["response_time_ms"] = response.elapsed.total_seconds() * 1000
        
        if response.status_code == 200:
            data = response.json()
            result["connection"] = "SUCCESS"
            result["data"] = data
            result["has_real_data"] = data.get("ultimo_dato") is not None
        elif response.status_code == 401:
            result["connection"] = "AUTH_FAILED"
            result["error"] = "API Key rechazada por el backend"
        else:
            result["connection"] = "HTTP_ERROR"
            result["error"] = f"HTTP {response.status_code}"
            
    except requests.Timeout:
        result["connection"] = "TIMEOUT"
        result["error"] = "El backend no respondió en 5 segundos"
    except requests.ConnectionError as e:
        result["connection"] = "CONNECTION_ERROR"
        result["error"] = f"No se pudo conectar: {str(e)}"
    except Exception as e:
        result["connection"] = "ERROR"
        result["error"] = str(e)
    
    return jsonify(result)

# ================================
# TEMPLATES HTML (LOGIN Y LOCKOUT)
# ================================

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - Centro Deportivo</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 400px;
            text-align: center;
        }
        .login-header h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .login-header p {
            color: #666;
            font-size: 16px;
        }
        .raspberry-badge {
            display: inline-block;
            background: #e8f5e8;
            color: #4caf50;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 12px;
            margin-top: 10px;
            font-weight: 500;
        }
        .form-group {
            margin-bottom: 25px;
            text-align: left;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }
        .form-group input[type="password"] {
            width: 100%;
            padding: 15px;
            border: 2px solid #e1e5e9;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s ease;
            background: #f8f9fa;
        }
        .form-group input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
            background: white;
        }
        .login-btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease;
        }
        .login-btn:hover {
            transform: translateY(-2px);
        }
        .alert {
            padding: 12px 15px;
            margin-bottom: 20px;
            border-radius: 8px;
            font-size: 14px;
        }
        .alert-error {
            background: #fee;
            color: #c33;
            border-left: 4px solid #f56565;
        }
        .alert-success {
            background: #efe;
            color: #2d5a27;
            border-left: 4px solid #48bb78;
        }
        .attempts-info {
            font-size: 12px;
            color: #e53e3e;
            margin-top: 10px;
            font-weight: 500;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1><i class="fas fa-shield-alt"></i> Panel de Administración</h1>
            <p>Centro Deportivo Municipal Eduardo Latorre</p>
            <div class="raspberry-badge">
                <i class="fas fa-microchip"></i> Raspberry Pi Dashboard
            </div>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">
                        <i class="fas fa-{% if category == 'error' %}exclamation-triangle{% else %}check-circle{% endif %}"></i>
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <form method="POST">
            <div class="form-group">
                <label for="password">
                    <i class="fas fa-lock"></i> Contraseña de Administrador
                </label>
                <input type="password" id="password" name="password" required autofocus
                       placeholder="Introduce tu contraseña">
            </div>

            <button type="submit" class="login-btn">
                <i class="fas fa-sign-in-alt"></i> Acceder al Panel
            </button>

            {% if attempts > 0 %}
                <div class="attempts-info">
                    <i class="fas fa-exclamation-triangle"></i>
                    Intentos fallidos: {{ attempts }}/{{ max_attempts }}
                </div>
            {% endif %}
        </form>
    </div>
</body>
</html>
'''

LOCKOUT_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Acceso Bloqueado - Centro Deportivo</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .lockout-container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 400px;
        }
        .lockout-icon {
            font-size: 64px;
            color: #e53e3e;
            margin-bottom: 20px;
        }
        .countdown {
            font-size: 24px;
            color: #e53e3e;
            font-weight: bold;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="lockout-container">
        <div class="lockout-icon">🚫</div>
        <h1>Acceso Bloqueado</h1>
        <div class="countdown">{{ remaining_time }} minutos restantes</div>
        <p>Demasiados intentos fallidos. Acceso bloqueado temporalmente.</p>
    </div>
</body>
</html>
'''

# ================================
# MANEJO DE ERRORES
# ================================

@app.errorhandler(405)
def method_not_allowed(e):
    logger.error(f"❌ Error 405 - Método no permitido: {request.method} {request.path}")
    return jsonify({
        'error': 'Método no permitido',
        'method': request.method,
        'path': request.path
    }), 405

@app.errorhandler(413)
def too_large(e):
    logger.error(f"❌ Error 413 - Archivo demasiado grande")
    flash(f'Archivo demasiado grande. Máximo: {MAX_FILE_SIZE // (1024*1024)}MB', 'error')
    return redirect(url_for('admin_panel'))

@app.errorhandler(404)
def not_found(e):
    logger.warning(f"⚠️ Error 404 - No encontrado: {request.path}")
    return jsonify({'error': 'Endpoint no encontrado', 'path': request.path}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"❌ Error 500 - Error interno: {e}")
    return jsonify({'error': 'Error interno del servidor'}), 500

# ================================
# RUTAS DE DEBUG
# ================================

@app.route('/debug/routes')
def debug_routes():
    """Mostrar todas las rutas registradas"""
    if not app.debug:
        return "Debug no habilitado", 403
    
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': str(rule)
        })
    
    return jsonify({
        'total_routes': len(routes),
        'routes': sorted(routes, key=lambda x: x['rule'])
    })

@app.route('/debug/config')
def debug_config():
    """Debug de configuración"""
    config = load_config()
    return jsonify({
        'config_file': CONFIG_FILE,
        'config_exists': os.path.exists(CONFIG_FILE),
        'upload_folder': UPLOAD_FOLDER,
        'upload_folder_exists': os.path.exists(UPLOAD_FOLDER),
        'config_data': config,
        'video_files': os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else [],
        'piscina_api': {
            'url': PISCINA_API_URL,
            'key_configured': bool(PISCINA_API_KEY)
        }
    })

# ================================
# CONFIGURACIÓN INICIAL
# ================================

def setup_admin_security():
    """Configurar directorios y archivos necesarios"""
    try:
        log_dir = os.path.join(BASE_DIR, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, 'admin_access.log')
        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write(f"# Admin Access Log - Created {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        logger.info("✅ Configuración de seguridad completada")
        logger.info(f"📁 Logs en: {log_file}")
        logger.info(f"🔑 Password actual: {ADMIN_PASSWORD}")
        logger.info("⚠️  IMPORTANTE: Cambia la password en el código antes de usar en producción")
        
    except Exception as e:
        logger.error(f"⚠️ Error en configuración: {e}")

if __name__ == '__main__':
    ensure_config_exists()
    setup_admin_security()
    
    logger.info("🚀 Iniciando servidor Dashboard...")
    logger.info(f"📁 Carpeta de videos: {UPLOAD_FOLDER}")
    logger.info(f"📋 Archivo de configuración: {CONFIG_FILE}")
    logger.info(f"🏊 Backend piscina: {PISCINA_API_URL}")
    logger.info("🔒 Sistema de login admin configurado")
    logger.info("📍 Admin login: http://localhost:5000/admin/login")
    logger.info("🧪 Test piscina: http://localhost:5000/test/piscina")
    logger.info("🐛 Debug routes: http://localhost:5000/debug/routes")
    
    app.run(host='0.0.0.0', port=5000, debug=True)