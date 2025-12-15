import streamlit as st
import pandas as pd
from datetime import date
import os
import json 
import time 
import plotly.express as px
import numpy as np 
import sqlite3 # <--- ¡NUEVO!

# ===============================================
# 1. CONFIGURACIÓN Y BASES DE DATOS (MAESTRAS)
# ===============================================

# CAMBIAMOS DATA_FILE por DB_FILE para SQLite
DB_FILE = 'tesoro_datos.db' # <--- NUEVO ARCHIVO DE BASE DE DATOS
PRECIOS_FILE = 'precios_base.json'
DESCUENTOS_FILE = 'descuentos_lugar.json'
COMISIONES_FILE = 'comisiones_pago.json'
REGLAS_FILE = 'descuentos_reglas.json' 

def save_config(data, filename):
    """Guarda la configuración a un archivo JSON."""
    try:
        # Usamos sort_keys=True para mantener el orden consistente si Python lo permite
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4, sort_keys=True)
    except Exception as e:
        st.error(f"Error al guardar el archivo {filename}: {e}")

def load_config(filename):
    """
    Carga la configuración desde un archivo JSON, creando el archivo si no existe 
    y manejando la carga de datos maestros para la interfaz.
    """
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            return data
            
    except FileNotFoundError:
        # --- Configuración por defecto para inicialización ---
        if filename == PRECIOS_FILE:
            default_data = {
                'ALERCE': {'Item1': 30000, 'Item2': 40000}, 
                'AMAR AUSTRAL': {'ADIR+ADOS2': 30000, '4 SABADOS': 25000, '5 SABADOS': 30000, 'PACIENTE': 30000}
            }
        elif filename == DESCUENTOS_FILE:
            default_data = {'ALERCE': 5000, 'AMAR AUSTRAL': 7000}
        elif filename == COMISIONES_FILE:
            default_data = {'EFECTIVO': 0.00, 'TRANSFERENCIA': 0.00, 'TARJETA': 0.03, 'AMAR AUSTRAL': 0.00}
        elif filename == REGLAS_FILE:
            # Los montos están en int para ser consistentes con la corrección
            default_data = {'AMAR AUSTRAL': {'LUNES': 0, 'MARTES': 8000, 'VIERNES': 6500}} 
        else:
            default_data = {}
            
        save_config(default_data, filename)
        return default_data
        
    except json.JSONDecodeError as e:
        st.error(f"Error: El archivo {filename} tiene un formato JSON inválido. Revisa su contenido. Detalle: {e}")
        return {} 

def sanitize_number_input(value):
    """
    Convierte un valor de input de tabla (que puede ser NaN, string o float) a int. 
    """
    # 1. Tratar valores nulos o vacíos
    if pd.isna(value) or value is None or value == "":
        return 0
    
    # 2. Convertir a float primero y luego a int 
    try:
        return int(float(value))
    except (ValueError, TypeError):
        # 3. Si no es un número válido, devolver 0
        return 0 

def re_load_global_config():
    """Recarga todas las variables de configuración global y las listas derivadas, FORZANDO MAYÚSCULAS en las claves de Lugar y Método de Pago."""
    global PRECIOS_BASE_CONFIG, DESCUENTOS_LUGAR, COMISIONES_PAGO, DESCUENTOS_REGLAS
    global LUGARES, METODOS_PAGO
    
    # --- Cargar Configuración Bruta ---
    precios_raw = load_config(PRECIOS_FILE)
    descuentos_raw = load_config(DESCUENTOS_FILE)
    comisiones_raw = load_config(COMISIONES_FILE)
    reglas_raw = load_config(REGLAS_FILE)

    # --- Procesar y Forzar MAYÚSCULAS para asegurar consistencia ---
    
    PRECIOS_BASE_CONFIG = {k.upper(): v for k, v in precios_raw.items()}
    DESCUENTOS_LUGAR = {k.upper(): v for k, v in descuentos_raw.items()}
    COMISIONES_PAGO = {k.upper(): v for k, v in comisiones_raw.items()}

    DESCUENTOS_REGLAS = {}
    for lugar, reglas in reglas_raw.items():
        lugar_upper = lugar.upper()
        # LA LLAMADA A sanitize_number_input AHORA FUNCIONA
        reglas_upper = {dia.upper(): sanitize_number_input(monto) for dia, monto in reglas.items()} 
        DESCUENTOS_REGLAS[lugar_upper] = reglas_upper

    # Recrear las listas dinámicas
    LUGARES = sorted(list(PRECIOS_BASE_CONFIG.keys())) if PRECIOS_BASE_CONFIG else []
    METODOS_PAGO = list(COMISIONES_PAGO.keys()) if COMISIONES_PAGO else []

# Llamar la función al inicio del script para inicializar todo
re_load_global_config() 

DIAS_SEMANA = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO', 'DOMINGO']


# ===============================================
# 2. FUNCIONES DE PERSISTENCIA (MIGRADO A SQLite)
# ===============================================

def get_db_connection():
    """Establece la conexión a la base de datos y asegura la existencia de la tabla."""
    # Conexión al archivo SQLite (se crea si no existe)
    conn = sqlite3.connect(DB_FILE)
    
    # Aseguramos la existencia de la tabla 'atenciones', agregando la columna 'id'
    conn.execute("""
        CREATE TABLE IF NOT EXISTS atenciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Fecha TEXT,
            Lugar TEXT,
            Item TEXT,
            Paciente TEXT,
            "Método Pago" TEXT,
            "Valor Bruto" INTEGER,
            "Desc. Fijo Lugar" INTEGER,
            "Desc. Tarjeta" INTEGER,
            "Desc. Adicional" INTEGER,
            "Total Recibido" INTEGER
        )
    """)
    conn.commit()
    return conn

# Reemplazo de load_data() por carga desde BD con caché
@st.cache_data(show_spinner=False)
def load_data_from_db():
    """Carga los datos desde SQLite a un DataFrame."""
    conn = get_db_connection()
    # Leemos la tabla, ordenando por ID descendente
    df = pd.read_sql_query("SELECT * FROM atenciones ORDER BY id DESC", conn)
    conn.close()
    
    # Aseguramos que la fecha sea datetime si hay datos
    if not df.empty:
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce', format='%Y-%m-%d')
    
    return df

# Reemplazo de save_data() por función de inserción en BD
def insert_new_record(record_dict):
    """Inserta un nuevo registro en la tabla de atenciones."""
    conn = get_db_connection()
    
    # Preparamos la consulta SQL
    cols = ", ".join(f'"{k}"' for k in record_dict.keys())
    placeholders = ", ".join("?" * len(record_dict))
    
    query = f"INSERT INTO atenciones ({cols}) VALUES ({placeholders})"
    
    conn.execute(query, list(record_dict.values()))
    conn.commit()
    conn.close()
    return True

# Función de actualización para el modo edición
def update_existing_record(record_dict):
    """Actualiza un registro existente usando su 'id' como clave."""
    conn = get_db_connection()
    
    # El ID es necesario para el WHERE, lo separamos
    record_id = record_dict.pop('id') 
    
    # Construimos la parte SET de la consulta (col1=?, col2=?)
    set_clauses = [f'"{k}" = ?' for k in record_dict.keys()]
    set_clause = ", ".join(set_clauses)
    
    query = f"UPDATE atenciones SET {set_clause} WHERE id = ?"
    
    # Los valores son (valores a actualizar) + (el id para el WHERE)
    values = list(record_dict.values()) + [record_id]
    
    try:
        conn.execute(query, values)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error al actualizar la BD: {e}")
        return False
    finally:
        conn.close()


# --- EL RESTO DE LAS FUNCIONES DE CÁLCULO Y ESTILO PERMANECEN IGUAL ---

def calcular_ingreso(lugar, item, metodo_pago, desc_adicional_manual, fecha_atencion, valor_bruto_override=None):
    """Calcula el ingreso final líquido."""
    
    lugar_upper = lugar.upper() if lugar else ''
    metodo_pago_upper = metodo_pago.upper() if metodo_pago else ''
    
    if not lugar_upper or not PRECIOS_BASE_CONFIG or not metodo_pago_upper:
          return {
              'valor_bruto': 0,
              'desc_fijo_lugar': 0,
              'desc_tarjeta': 0,
              'total_recibido': 0
          }
    
    precio_base = PRECIOS_BASE_CONFIG.get(lugar_upper, {}).get(item, 0)
    valor_bruto = valor_bruto_override if valor_bruto_override is not None else precio_base
    
    # 2. LÓGICA DE DESCUENTO FIJO CONDICIONAL (Tributo)
    
    # *** REGLA ESPECIAL PARA CPM: 48.7% DEL VALOR BRUTO ***
    if lugar_upper == 'CPM':
        # El descuento fijo es el 48.7% del valor bruto
        desc_fijo_lugar = valor_bruto * 0.487 
    # ******************************************************
    else:
        # Si no es CPM, se aplica el descuento fijo normal (base o por regla diaria)
        desc_fijo_lugar = DESCUENTOS_LUGAR.get(lugar_upper, 0) 
    
        # 2.1. Revisar si existe una regla especial para el día (Solo si NO es CPM)
        if lugar_upper in DESCUENTOS_REGLAS:
            try:
                # Asegurarse de que el objeto fecha sea una instancia de date
                if isinstance(fecha_atencion, pd.Timestamp):
                    fecha_obj = fecha_atencion.date()
                elif isinstance(fecha_atencion, date):
                    fecha_obj = fecha_atencion
                else:
                    fecha_obj = date.today()
                
                dia_semana_num = fecha_obj.weekday()
                
                dia_nombre = DIAS_SEMANA[dia_semana_num].upper() 
                regla_especial = DESCUENTOS_REGLAS[lugar_upper].get(dia_nombre)
                
                if regla_especial is not None:
                    desc_fijo_lugar = regla_especial 
            except Exception:
                    pass

    # 3. Aplicar Comisión de Tarjeta
    comision_pct = COMISIONES_PAGO.get(metodo_pago_upper, 0.00) 
    desc_tarjeta = valor_bruto * comision_pct
    
    # 4. Cálculo final
    total_recibido = (
        valor_bruto 
        - desc_fijo_lugar 
        - desc_tarjeta 
        - desc_adicional_manual
    )
    
    return {
        'valor_bruto': int(valor_bruto),
        'desc_fijo_lugar': int(desc_fijo_lugar), # Se redondea el resultado del 48.7%
        'desc_tarjeta': int(desc_tarjeta),
        'total_recibido': int(total_recibido)
    }

# --- Funciones de Reactividad y Reinicio (SIN CAMBIOS) ---

def update_price_from_item_or_lugar():
    """Callback para actualizar precio y estado al cambiar Lugar o Ítem."""
    lugar_key_current = st.session_state.get('form_lugar', '').upper()
    
    items_disponibles = list(PRECIOS_BASE_CONFIG.get(lugar_key_current, {}).keys())

    current_item = st.session_state.get('form_item')
    
    item_calc_for_price = None
    
    if not items_disponibles:
        st.session_state.form_item = ''
        st.session_state.form_valor_bruto = 0
        st.session_state.form_desc_adic_input = 0 
        return
        
    if current_item not in items_disponibles:
        st.session_state.form_item = items_disponibles[0]
        item_calc_for_price = items_disponibles[0]
    else:
        item_calc_for_price = current_item
        
    if not lugar_key_current or not item_calc_for_price:
        st.session_state.form_valor_bruto = 0
        st.session_state.form_desc_adic_input = 0
        return
        
    precio_base_sugerido = PRECIOS_BASE_CONFIG.get(lugar_key_current, {}).get(item_calc_for_price, 0)
    
    st.session_state.form_valor_bruto = int(precio_base_sugerido)
    
def force_recalculate():
    """Función de callback simple para forzar actualización del estado."""
    pass

def update_edit_price():
    """Callback para actualizar precio sugerido en el modal de edición."""
    lugar_key_edit = st.session_state.get('edit_lugar', '').upper()
    item_key_edit = st.session_state.get('edit_item', '')
    
    if not lugar_key_edit or not item_key_edit:
        st.session_state.edit_valor_bruto = 0
        return
        
    precio_base_sugerido_edit = PRECIOS_BASE_CONFIG.get(lugar_key_edit, {}).get(item_key_edit, 0)
    
    st.session_state.edit_valor_bruto = int(precio_base_sugerido_edit)

# --------------------------------------------------------------------------
# --- NUEVAS FUNCIONES DE GUARDADO Y LIMPIEZA PARA EL MODO EDICIÓN ---
# Lógica modificada para usar UPDATE en la BD
def save_edit_state_to_df():
    """
    Guarda el estado actual de los inputs de edición (st.session_state) 
    DIRECTAMENTE en la base de datos SQLite.
    """
    if st.session_state.edit_index is None:
        return 0
        
    # El ID de la BD está almacenado en 'edited_record_id' (necesario para el UPDATE)
    record_id = st.session_state.get('edited_record_id')
    if record_id is None:
        st.error("Error: ID de registro para edición no encontrado.")
        return 0
        
    # Se obtienen los valores de la sesión
    valor_bruto_final = st.session_state.edit_valor_bruto
    desc_adicional_final = st.session_state.edit_desc_adic
    
    # Se usan los valores originales/recalculados de descuento (almacenados en los callbacks)
    desc_fijo_final = st.session_state.get('original_desc_fijo_lugar', 0)
    desc_tarjeta_final = st.session_state.get('original_desc_tarjeta', 0)
    
    # 2. Recalcular el total líquido con los valores finales
    total_liquido_final = (
        valor_bruto_final
        - desc_fijo_final
        - desc_tarjeta_final
        - desc_adicional_final
    )
    
    # 3. Preparar el registro para la actualización de la BD
    data_to_update = {
        "id": record_id, # CLAVE para el WHERE de la actualización
        "Fecha": st.session_state.edit_fecha.strftime('%Y-%m-%d'),
        "Lugar": st.session_state.edit_lugar,
        "Ítem": st.session_state.edit_item,
        "Paciente": st.session_state.edit_paciente,
        "Método Pago": st.session_state.edit_metodo,
        "Valor Bruto": valor_bruto_final,
        "Desc. Fijo Lugar": desc_fijo_final,
        "Desc. Tarjeta": desc_tarjeta_final,
        "Desc. Adicional": desc_adicional_final,
        "Total Recibido": total_liquido_final
    }
    
    # 4. Actualizar la fila en la BASE DE DATOS y forzar la recarga del DataFrame
    if update_existing_record(data_to_update): # <--- LLAMADA A UPDATE SQL
        # Si la actualización fue exitosa, limpiamos la caché y recargamos el DF
        load_data_from_db.clear()
        st.session_state.atenciones_df = load_data_from_db()
        return total_liquido_final
    
    return 0 # Retorna 0 si hubo error.

def _cleanup_edit_state():
    """Limpia las claves de sesión relacionadas con el modo de edición para forzar el cierre del expander."""
    st.session_state.edit_index = None
    st.session_state.edited_lugar_state = None
    st.session_state.edited_record_id = None # <--- LIMPIAMOS EL ID DE LA BD
    # ELIMINAMOS TAMBIÉN LAS CLAVES DE INPUTS PARA FORZAR LA RECARGA EN EL PRÓXIMO OPEN
    if 'edit_valor_bruto' in st.session_state: del st.session_state.edit_valor_bruto
    if 'edit_desc_adic' in st.session_state: del st.session_state.edit_desc_adic
    if 'original_desc_fijo_lugar' in st.session_state: del st.session_state.original_desc_fijo_lugar
    if 'original_desc_tarjeta' in st.session_state: del st.session_state.original_desc_tarjeta


# --------------------------------------------------------------------------


# --- FUNCIONES DE CALLBACK PARA LOS BOTONES DE ACTUALIZACIÓN EN EDICIÓN (CON CIERRE FORZADO Y BANDERA) ---
# Lógica modificada para usar la nueva save_edit_state_to_df()

def update_edit_bruto_price():
    """Callback: Actualiza el Valor Bruto, guarda, notifica Y CIERRA (usando bandera)."""
    lugar_edit = st.session_state.edit_lugar.upper()
    item_edit = st.session_state.edit_item
    
    # 1. Obtener y actualizar el nuevo precio base
    nuevo_precio_base = PRECIOS_BASE_CONFIG.get(lugar_edit, {}).get(item_edit, st.session_state.edit_valor_bruto)
    st.session_state.edit_valor_bruto = int(nuevo_precio_base)
    
    # 2. Guardar en BD y obtener el nuevo total
    new_total = save_edit_state_to_df() # <--- USA LA NUEVA LÓGICA DE BD
    
    if new_total > 0:
        st.success(f"Valor Bruto actualizado y guardado. Nuevo Tesoro Líquido: {format_currency(new_total)}")
        
        # 3. CIERRE FORZADO CON BANDERA
        _cleanup_edit_state()
        st.session_state.rerun_after_edit = True # <-- ACTIVAR BANDERA
    else:
        st.error("Error: No se pudo actualizar el registro en la base de datos.")

def update_edit_desc_tarjeta():
    """Callback: Recalcula y actualiza el Desc. Tarjeta, guarda, notifica Y CIERRA (usando bandera)."""
    comision_pct_actual = COMISIONES_PAGO.get(st.session_state.edit_metodo, 0.00)
    valor_bruto_actual = st.session_state.edit_valor_bruto
    nuevo_desc_tarjeta = int(valor_bruto_actual * comision_pct_actual)
    
    # 1. Actualizar el valor que se usará en el cálculo final al guardar
    st.session_state.original_desc_tarjeta = nuevo_desc_tarjeta
    
    # 2. Guardar en BD y obtener el nuevo total
    new_total = save_edit_state_to_df() # <--- USA LA NUEVA LÓGICA DE BD
    
    if new_total > 0:
        st.success(f"Desc. Tarjeta actualizado y guardado. Nuevo Tesoro Líquido: {format_currency(new_total)}")
        
        # 3. CIERRE FORZADO CON BANDERA
        _cleanup_edit_state()
        st.session_state.rerun_after_edit = True # <-- ACTIVAR BANDERA
    else:
        st.error("Error: No se pudo actualizar el registro en la base de datos.")


def update_edit_tributo():
    """Callback: Recalcula y actualiza el Tributo (Desc. Fijo Lugar), guarda, notifica Y CIERRA (usando bandera)."""
    current_lugar_upper = st.session_state.edit_lugar 
    
    # --- LÓGICA DE CÁLCULO DE TRIBUTO EN EDICIÓN ---
    if current_lugar_upper.upper() == 'CPM':
        # Aplica la regla del 48.7% si es CPM
        desc_fijo_calc = int(st.session_state.edit_valor_bruto * 0.487)
    else:
        # Lógica de cálculo del Tributo normal (base o regla diaria)
        try:
            current_day_name = DIAS_SEMANA[st.session_state.edit_fecha.weekday()]
        except Exception:
            current_day_name = "LUNES" 
        
        desc_fijo_calc = DESCUENTOS_LUGAR.get(current_lugar_upper, 0) # Base
        if current_lugar_upper in DESCUENTOS_REGLAS:
             try: 
                 regla_especial_monto = DESCUENTOS_REGLAS[current_lugar_upper].get(current_day_name.upper())
                 if regla_especial_monto is not None:
                     desc_fijo_calc = regla_especial_monto
             except Exception:
                 pass
             
    # 1. Actualizar el valor que se usará en el cálculo final al guardar
    st.session_state.original_desc_fijo_lugar = desc_fijo_calc
    
    # 2. Guardar en BD y obtener el nuevo total
    new_total = save_edit_state_to_df() # <--- USA LA NUEVA LÓGICA DE BD
    
    if new_total > 0:
        st.success(f"Tributo actualizado y guardado. Nuevo Tesoro Líquido: {format_currency(new_total)}")
        
        # 3. CIERRE FORZADO CON BANDERA
        _cleanup_edit_state()
        st.session_state.rerun_after_edit = True # <-- ACTIVAR BANDERA
    else:
        st.error("Error: No se pudo actualizar el registro en la base de datos.")


# --- Fin de Funciones de Callback para Botones de Edición ---


def submit_and_reset():
    """Ejecuta la lógica de guardado y luego resetea el formulario."""
    
    # 0. Verificación simple del campo obligatorio
    if st.session_state.get('form_paciente', "") == "":
        st.session_state['save_error'] = "Por favor, ingresa el nombre del paciente antes de guardar."
        return 
    
    # Asegurar que la configuración esté disponible
    if not LUGARES or not METODOS_PAGO:
        st.session_state['save_error'] = "Error de configuración: Lugares o Métodos de Pago vacíos. Revisa la pestaña Configuración."
        return 
        
    # --- LÓGICA DE GUARDADO Y CÁLCULO ---
    
    paciente_nombre_guardar = st.session_state.form_paciente 
    
    resultados_finales = calcular_ingreso(
        st.session_state.form_lugar, 
        st.session_state.form_item, 
        st.session_state.form_metodo_pago, 
        st.session_state.form_desc_adic_input, 
        fecha_atencion=st.session_state.form_fecha, 
        valor_bruto_override=st.session_state.form_valor_bruto
    )
    
    # 2. Creación del nuevo registro
    # NO se incluye el ID, la base de datos lo genera automáticamente
    nueva_atencion = {
        "Fecha": st.session_state.form_fecha.strftime('%Y-%m-%d'), 
        "Lugar": st.session_state.form_lugar, 
        "Ítem": st.session_state.form_item, 
        "Paciente": paciente_nombre_guardar, 
        "Método Pago": st.session_state.form_metodo_pago,
        "Valor Bruto": resultados_finales['valor_bruto'],
        "Desc. Fijo Lugar": resultados_finales['desc_fijo_lugar'],
        "Desc. Tarjeta": resultados_finales['desc_tarjeta'],
        "Desc. Adicional": st.session_state.form_desc_adic_input, 
        "Total Recibido": resultados_finales['total_recibido']
    }
    
    # 3. ¡NUEVO! Insertar en la BD en lugar de concatenar el DataFrame
    insert_new_record(nueva_atencion)
    
    # 4. Forzar la recarga del DataFrame desde la BD al limpiar la caché
    load_data_from_db.clear() # Limpia la caché de la función de carga
    st.session_state.atenciones_df = load_data_from_db() # Recarga el DataFrame actualizado
    
    # 5. Mensaje de éxito
    st.session_state['save_status'] = f"🎉 ¡Aventura registrada para {paciente_nombre_guardar}! El tesoro es {format_currency(resultados_finales['total_recibido'])}"

    # --- LÓGICA DE REINICIO MANUAL DE TODOS LOS WIDGETS ---
    
    default_lugar = LUGARES[0] if LUGARES else ''
    items_default = list(PRECIOS_BASE_CONFIG.get(default_lugar, {}).keys())
    default_item = items_default[0] if items_default else ''
    default_valor_bruto = int(PRECIOS_BASE_CONFIG.get(default_lugar, {}).get(default_item, 0))

    # Limpiar/resetear las claves de SESSION_STATE
    if LUGARES: st.session_state.form_lugar = default_lugar
    st.session_state.form_item = default_item
    st.session_state.form_valor_bruto = default_valor_bruto
    st.session_state.form_desc_adic_input = 0
    st.session_state.form_fecha = date.today() 
    if METODOS_PAGO: st.session_state.form_metodo_pago = METODOS_PAGO[0]
    st.session_state.form_paciente = "" 
    
    if 'save_error' in st.session_state:
        del st.session_state['save_error']

def format_currency(value):
    """Función para formatear números como moneda en español con punto y coma."""
    if value is None or not isinstance(value, (int, float)):
          value = 0
    return f"${int(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")

def set_dark_mode_theme():
    """Establece transparencia y ajusta la apariencia para el tema oscuro."""
    dark_mode_css = '''
    <style>
    .stApp, [data-testid="stAppViewBlock"], .main { background-color: transparent !important; background-image: none !important; }
    [data-testid="stSidebarContent"] { background-color: rgba(30, 30, 30, 0.9) !important; color: white; }
    .css-1r6dm1, .streamlit-expander, 
    [data-testid="stMetric"], [data-testid="stVerticalBlock"],
    .stSelectbox > div:first-child, .stDateInput > div:first-child, .stTextInput > div:first-child, .stNumberInput > div:first-child, .stRadio > div { 
        background-color: rgba(10, 10, 10, 0.6) !important; border-radius: 10px; padding: 10px;
    } 
    .stDataFrame, .stTable { background-color: rgba(0, 0, 0, 0.4) !important; }
    h1, h2, h3, h4, h5, h6, label, .css-1d391kg, [data-testid="stSidebarContent"] *, [data-testid="stHeader"] * { color: white !important; }
    .streamlit-expander label, div.stRadio > label { color: white !important; }
    </style>
    '''
    st.markdown(dark_mode_css, unsafe_allow_html=True)


# ===============================================
# 3. INTERFAZ DE USUARIO (FRONTEND)
# ===============================================

# 🚀 Configuración de la Página y Título
st.set_page_config(
    page_title="🏰 Control de Ingresos Mágicos 🪄", 
    layout="wide"
)

set_dark_mode_theme()

# ====================================================================
# *** LÓGICA DE REINICIO DE BANDERA PARA CALLBACKS DE EDICIÓN ***
# ====================================================================
if 'rerun_after_edit' not in st.session_state:
    st.session_state.rerun_after_edit = False

if st.session_state.rerun_after_edit:
    st.session_state.rerun_after_edit = False # Resetea la bandera inmediatamente
    st.rerun() # Ejecuta el reinicio FUERA del callback

# ====================================================================


st.title("🏰 Tesoro de Ingresos Fonoaudiológicos 💰")
st.markdown("✨ ¡Transforma cada atención en un diamante! ✨")

# --- Herramientas de Mantenimiento ---
if st.sidebar.button("🧹 Limpiar Cenicienta (Caché y Config)", type="secondary"):
    st.cache_data.clear() 
    st.cache_resource.clear() 
    
    # 💡 ¡CLAVE! Limpiamos la caché de la función de BD antes de recargar
    load_data_from_db.clear() 
    re_load_global_config() 
    st.session_state.atenciones_df = load_data_from_db() # Recarga desde la BD
    
    submit_and_reset() 
    
    st.success("Caché, Configuración y Datos Recargados. ¡La magia continúa!")
    st.rerun() 

st.sidebar.markdown("---") 

# Cargar los datos y asignarlos al estado de la sesión
# 💡 Usamos la nueva función de BD aquí.
if 'atenciones_df' not in st.session_state:
    st.session_state.atenciones_df = load_data_from_db()
    
if 'edit_index' not in st.session_state:
    st.session_state.edit_index = None 

# Añadimos la clave para guardar el ID de la base de datos para edición
if 'edited_record_id' not in st.session_state:
    st.session_state.edited_record_id = None


# --- Pestañas Principales ---
tab_registro, tab_dashboard, tab_config = st.tabs(["📝 Registrar Aventura", "📊 Mapa del Tesoro", "⚙️ Configuración Maestra"])

with tab_registro:
    # --- FORMULARIO DE INGRESO ---
    st.subheader("🎉 Nueva Aventura de Ingreso (Atención)")
    
    # --- Mostrar mensajes de estado después del rerun ---
    if 'save_status' in st.session_state:
        st.success(st.session_state.save_status)
        del st.session_state.save_status
        
    if 'save_error' in st.session_state:
        st.error(st.session_state.save_error)
        del st.session_state.save_error
    
    if not LUGARES or not METODOS_PAGO:
        st.error("🚨 ¡Fallo de Configuración! La lista de Lugares o Métodos de Pago está vacía. Por favor, revisa la pestaña 'Configuración Maestra'.")
        
    # --- Inicialización de Valores ---
    lugar_key_initial = LUGARES[0] if LUGARES else ''
    if 'form_lugar' not in st.session_state: st.session_state.form_lugar = lugar_key_initial
    
    current_lugar_value_upper = st.session_state.form_lugar 
    items_filtrados_initial = list(PRECIOS_BASE_CONFIG.get(current_lugar_value_upper, {}).keys())
    
    item_key_initial = items_filtrados_initial[0] if items_filtrados_initial else ''
    if 'form_item' not in st.session_state or st.session_state.form_item not in items_filtrados_initial:
        st.session_state.form_item = item_key_initial
    
    precio_base_sugerido = PRECIOS_BASE_CONFIG.get(current_lugar_value_upper, {}).get(st.session_state.form_item, 0)
    
    if 'form_valor_bruto' not in st.session_state: st.session_state.form_valor_bruto = int(precio_base_sugerido)
    if 'form_desc_adic_input' not in st.session_state: st.session_state.form_desc_adic_input = 0
    if 'form_fecha' not in st.session_state: st.session_state.form_fecha = date.today()
    if 'form_metodo_pago' not in st.session_state: st.session_state.form_metodo_pago = METODOS_PAGO[0] if METODOS_PAGO else ''
    if 'form_paciente' not in st.session_state: st.session_state.form_paciente = ""


    # ----------------------------------------------------------------------
    # WIDGETS REACTIVOS (FUERA DEL FORMULARIO) - Diseño de Cabecera
    # ----------------------------------------------------------------------
    st.markdown("### 📝 Datos de la Aventura")
    col_cabecera_1, col_cabecera_2, col_cabecera_3, col_cabecera_4 = st.columns(4)

    # 1. SELECTBOX LUGAR (REACTIVO)
    with col_cabecera_1:
        try:
            lugar_index = LUGARES.index(st.session_state.form_lugar) if st.session_state.form_lugar in LUGARES else 0
        except ValueError:
            lugar_index = 0

        st.selectbox("📍 Castillo/Lugar de Atención", 
                     options=LUGARES, 
                     key="form_lugar",
                     index=lugar_index,
                     on_change=update_price_from_item_or_lugar) 
    
    # 2. SELECTBOX ÍTEM (REACTIVO)
    with col_cabecera_2:
        lugar_key_current = st.session_state.form_lugar 
        items_filtrados_current = list(PRECIOS_BASE_CONFIG.get(lugar_key_current, {}).keys())
        
        item_para_seleccionar = st.session_state.get('form_item', items_filtrados_current[0] if items_filtrados_current else '')
        
        try:
            item_index = items_filtrados_current.index(item_para_seleccionar) if item_para_seleccionar in items_filtrados_current else 0
        except (ValueError, KeyError):
            item_index = 0 
            
        st.selectbox("📋 Poción/Procedimiento", 
                     options=items_filtrados_current, 
                     key="form_item",
                     index=item_index, 
                     on_change=update_price_from_item_or_lugar) 
    
    # 3. VALOR BRUTO (REACTIVO)
    with col_cabecera_3:
        st.number_input(
            "💰 **Valor Bruto (Recompensa)**", 
            min_value=0, 
            step=1000,
            key="form_valor_bruto", 
            on_change=force_recalculate 
        )

    # 4. DESCUENTO ADICIONAL (REACTIVO)
    with col_cabecera_4:
        st.number_input(
            "✂️ **Polvo Mágico Extra (Ajuste)**", 
            min_value=-500000, 
            value=st.session_state.get('form_desc_adic_input', 0), 
            step=1000, 
            key="form_desc_adic_input",
            on_change=force_recalculate, 
            help="Ingresa un valor positivo para descuentos (más magia) o negativo para cargos."
        )
    
    st.markdown("---") 

    # ----------------------------------------------------------------------
    # WIDGETS DE FECHA Y PAGO (MOVIDOS FUERA DEL FORMULARIO - AHORA REACTIVOS)
    # ----------------------------------------------------------------------
    col_c1, col_c2 = st.columns(2)
    
    with col_c1:
        # FECHA DE ATENCIÓN (REACTIVO)
        st.date_input(
            "🗓️ Fecha de Atención", 
            st.session_state.form_fecha, 
            key="form_fecha", 
            on_change=force_recalculate 
        ) 
        
        # MÉTODO DE PAGO (REACTIVO)
        try:
            pago_idx = METODOS_PAGO.index(st.session_state.get('form_metodo_pago', METODOS_PAGO[0]))
        except ValueError:
            pago_idx = 0
        
        st.radio(
            "💳 Método de Pago Mágico", 
            options=METODOS_PAGO, 
            key="form_metodo_pago", 
            index=pago_idx,
            on_change=force_recalculate 
        )
        
        st.markdown("---") 

    # ----------------------------------------------------------------------
    # WIDGETS DE FORMULARIO (DENTRO DEL st.form)
    # ----------------------------------------------------------------------
    
    with st.form("registro_atencion_form"): 
        
        # --- COLUMNA IZQUIERDA (SOLO PACIENTE) ---
        with col_c1: 
            # PACIENTE (SE MANTIENE DENTRO para limpieza fácil)
            paciente = st.text_input("👤 Héroe/Heroína (Paciente/Asociado)", st.session_state.form_paciente, key="form_paciente")

        # --- COLUMNA DERECHA (Cálculos de Salida) ---
        with col_c2:
            
            st.markdown("### Detalles de Reducciones y Tesoro Neto")

            if not LUGARES or not items_filtrados_initial:
                st.info("Configuración de Lugar/Ítem incompleta. Revisa la pestaña de Configuración.")
            else:
                
                desc_adicional_calc = st.session_state.form_desc_adic_input 
                valor_bruto_calc = st.session_state.form_valor_bruto
                
                # Cálculo usando los valores del session_state (todos actualizados al ser reactivos)
                resultados = calcular_ingreso(
                    st.session_state.form_lugar, 
                    st.session_state.form_item, 
                    st.session_state.form_metodo_pago, 
                    desc_adicional_calc,
                    fecha_atencion=st.session_state.form_fecha, 
                    valor_bruto_override=valor_bruto_calc 
                )

                st.warning(f"**Desc. Tarjeta 🧙‍♀️ ({COMISIONES_PAGO.get(st.session_state.form_metodo_pago, 0.00)*100:.0f}%):** {format_currency(resultados['desc_tarjeta'])}")
                
                # LÓGICA DE ETIQUETADO DEL TRIBUTO
                current_lugar_upper = st.session_state.form_lugar 
                
                desc_lugar_label = f"Tributo al Castillo ({current_lugar_upper})"
                
                # AJUSTE DE ETIQUETA PARA CPM
                if current_lugar_upper.upper() == 'CPM':
                    desc_lugar_label = f"Tributo al Castillo (CPM - 48.7% Bruto)"
                else:
                    # LÓGICA DE ETIQUETADO DEL TRIBUTO NORMAL
                    try:
                        current_day_name = DIAS_SEMANA[st.session_state.form_fecha.weekday()] 
                    except Exception:
                        current_day_name = "N/A"
                        
                    is_rule_applied = False
                    if current_lugar_upper in DESCUENTOS_REGLAS:
                        try:
                            # Convertir a mayúsculas para la búsqueda
                            regla_especial_monto = DESCUENTOS_REGLAS[current_lugar_upper].get(current_day_name.upper())
                            
                            if regla_especial_monto is not None:
                                desc_lugar_label += f" (Regla: {current_day_name})"
                                is_rule_applied = True
                        except Exception:
                               pass
    
                    if not is_rule_applied and DESCUENTOS_LUGAR.get(current_lugar_upper, 0) > 0:
                        desc_lugar_label += " (Base)"

                
                st.info(f"**{desc_lugar_label}:** {format_currency(resultados['desc_fijo_lugar'])}")
                
                st.markdown("###")
                st.success(
                    f"## 💎 Tesoro Total (Líquido): {format_currency(resultados['total_recibido'])}"
                )
    
        st.markdown("---") 

        # --- BOTÓN DE ENVÍO DEL FORMULARIO ---
        st.form_submit_button(
            "✅ ¡Guardar Aventura y Tesoro!", 
            use_container_width=True, 
            type="primary",
            on_click=submit_and_reset 
        )

with tab_dashboard:
    # ===============================================
    # 4. DASHBOARD DE RESUMEN
    # ===============================================
    st.header("✨ Mapa y Brújula de Ingresos (Dashboard)")

    df = st.session_state.atenciones_df

    if not df.empty:
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')

        # --- FILTROS DINÁMICOS EN LA BARRA LATERAL (Lugar e Ítem) ---
