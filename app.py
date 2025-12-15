import streamlit as st
import pandas as pd
from datetime import date
import json 
import time 
import plotly.express as px
import numpy as np 
import sqlite3 

# ===============================================
# 1. CONFIGURACIÓN Y BASES DE DATOS (MAESTRAS)
# ===============================================

DB_FILE = 'tesoro_datos.db' # Nombre del archivo de la BD SQLite
PRECIOS_FILE = 'precios_base.json'
DESCUENTOS_FILE = 'descuentos_lugar.json'
COMISIONES_FILE = 'comisiones_pago.json'
REGLAS_FILE = 'descuentos_reglas.json' 

def save_config(data, filename):
    """Guarda la configuración a un archivo JSON."""
    try:
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
            default_data = {'ALERCE': 5000, 'AMAR AUSTRAL': 7000, 'CPM': 0} # CPM se deja en 0 para que la regla del 48.7% aplique
        elif filename == COMISIONES_FILE:
            default_data = {'EFECTIVO': 0.00, 'TRANSFERENCIA': 0.00, 'TARJETA': 0.03}
        elif filename == REGLAS_FILE:
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
    if pd.isna(value) or value is None or value == "":
        return 0
    
    try:
        # Aseguramos que sea un float antes de convertir a int, para manejar decimales en JSON
        return int(float(value)) 
    except (ValueError, TypeError):
        return 0 

def re_load_global_config():
    """Recarga todas las variables de configuración global y las listas derivadas."""
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
        reglas_upper = {dia.upper(): sanitize_number_input(monto) for dia, monto in reglas.items()} 
        DESCUENTOS_REGLAS[lugar_upper] = reglas_upper

    # Recrear las listas dinámicas
    LUGARES = sorted(list(PRECIOS_BASE_CONFIG.keys())) if PRECIOS_BASE_CONFIG else []
    METODOS_PAGO = list(COMISIONES_PAGO.keys()) if COMISIONES_PAGO else []

# Llamar la función al inicio del script para inicializar todo
re_load_global_config() 

DIAS_SEMANA = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO', 'DOMINGO']


# ===============================================
# 2. FUNCIONES DE PERSISTENCIA (SQLite)
# ===============================================

def get_db_connection():
    """Establece la conexión a la base de datos y asegura la existencia de la tabla."""
    conn = sqlite3.connect(DB_FILE)
    
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

@st.cache_data(show_spinner=False)
def load_data_from_db():
    """Carga los datos desde SQLite a un DataFrame. **Ordenado por ID ASC (1, 2, 3...)**."""
    conn = get_db_connection()
    # CORREGIDO: ORDENADO POR ID ASC para mostrar la secuencia correcta (1, 2, 3...)
    df = pd.read_sql_query("SELECT * FROM atenciones ORDER BY id ASC", conn) 
    conn.close()
    
    if not df.empty:
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce', format='%Y-%m-%d')
    
    if 'Item' in df.columns:
        df = df.rename(columns={'Item': 'Ítem'})
        
    return df

def insert_new_record(record_dict):
    """Inserta un nuevo registro en la tabla de atenciones."""
    conn = get_db_connection()
    cols = ", ".join(f'"{k}"' for k in record_dict.keys())
    placeholders = ", ".join("?" * len(record_dict))
    query = f"INSERT INTO atenciones ({cols}) VALUES ({placeholders})"
    conn.execute(query, list(record_dict.values()))
    conn.commit()
    conn.close()
    return True

def update_existing_record(record_dict):
    """Actualiza un registro existente usando su 'id' como clave."""
    conn = get_db_connection()
    record_id = record_dict.pop('id') 
    set_clauses = [f'"{k}" = ?' for k in record_dict.keys()]
    set_clause = ", ".join(set_clauses)
    query = f"UPDATE atenciones SET {set_clause} WHERE id = ?"
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
        
def delete_record(record_id):
    """Elimina un registro de la base de datos por ID."""
    conn = get_db_connection()
    query = "DELETE FROM atenciones WHERE id = ?"
    try:
        conn.execute(query, (record_id,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error al eliminar el registro ID {record_id}: {e}")
        return False
    finally:
        conn.close()


# ===============================================
# 3. FUNCIONES DE CÁLCULO Y LÓGICA DE NEGOCIO
# ===============================================

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
    desc_fijo_lugar = DESCUENTOS_LUGAR.get(lugar_upper, 0) 
    
    # *** REGLA ESPECIAL PARA CPM: 48.7% DEL VALOR BRUTO ***
    if lugar_upper == 'CPM':
        desc_fijo_lugar = valor_bruto * 0.487 
    # ******************************************************
    else:
        # 2.1. Revisar si existe una regla especial para el día
        try:
            if isinstance(fecha_atencion, pd.Timestamp):
                fecha_obj = fecha_atencion.date()
            elif isinstance(fecha_atencion, date):
                fecha_obj = fecha_atencion
            else:
                fecha_obj = date.today()
            
            dia_semana_num = fecha_obj.weekday()
            dia_nombre = DIAS_SEMANA[dia_semana_num].upper() 
            
            if lugar_upper in DESCUENTOS_REGLAS:
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
        'desc_fijo_lugar': int(desc_fijo_lugar), 
        'desc_tarjeta': int(desc_tarjeta),
        'total_recibido': int(total_recibido)
    }

# ===============================================
# 4. FUNCIONES DE CALLBACKS Y UTILIDADES
# ===============================================

def update_price_from_item_or_lugar():
    """Callback para actualizar precio y estado al cambiar Lugar o Ítem en el formulario de registro."""
    lugar_key_current = st.session_state.get('form_lugar', '').upper()
    items_disponibles = list(PRECIOS_BASE_CONFIG.get(lugar_key_current, {}).keys())

    current_item = st.session_state.get('form_item')
    item_calc_for_price = None
    
    if not items_disponibles:
        st.session_state.form_item = ''
        st.session_state.form_valor_bruto = 0
        return
        
    if current_item not in items_disponibles:
        st.session_state.form_item = items_disponibles[0]
        item_calc_for_price = items_disponibles[0]
    else:
        item_calc_for_price = current_item
        
    if not lugar_key_current or not item_calc_for_price:
        st.session_state.form_valor_bruto = 0
        return
        
    precio_base_sugerido = PRECIOS_BASE_CONFIG.get(lugar_key_current, {}).get(item_calc_for_price, 0)
    st.session_state.form_valor_bruto = int(precio_base_sugerido)
    
def force_recalculate():
    """Función de callback simple para forzar actualización del estado (ej: para el Total Líquido) en el formulario de REGISTRO."""
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

def _cleanup_edit_state():
    """Limpia las claves de sesión relacionadas con el modo de edición para forzar el cierre del expander."""
    st.session_state.edit_index = None # Ya no se usa, pero lo mantenemos por si acaso
    st.session_state.edited_record_id = None 
    
    # Eliminamos las claves de inputs para forzar la recarga en el próximo open
    keys_to_delete = [
        'edit_valor_bruto', 'edit_desc_adic', 'original_desc_fijo_lugar', 
        'original_desc_tarjeta', 'edit_lugar', 'edit_item', 'edit_paciente', 
        'edit_metodo', 'edit_fecha'
    ]
    for key in keys_to_delete:
        # Solo eliminamos si existen para evitar un KeyError
        if key in st.session_state: del st.session_state[key] 


def save_edit_state_to_df():
    """Guarda el estado actual de los inputs de edición DIRECTAMENTE en la base de datos SQLite."""
    if st.session_state.edited_record_id is None:
        st.warning("Error: No hay un ID de registro para guardar la edición.")
        return 0
        
    record_id = st.session_state.edited_record_id
        
    # Se usan los valores de sesión (inputs)
    valor_bruto_final = st.session_state.edit_valor_bruto
    desc_adicional_final = st.session_state.edit_desc_adic
    
    # Se usan los valores originales/recalculados (almacenados en los callbacks) para los descuentos
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
        "id": record_id, 
        "Fecha": st.session_state.edit_fecha.strftime('%Y-%m-%d'),
        "Lugar": st.session_state.edit_lugar,
        "Item": st.session_state.edit_item, # USAMOS 'Item' (SIN TILDE) para la BD
        "Paciente": st.session_state.edit_paciente,
        "Método Pago": st.session_state.edit_metodo,
        "Valor Bruto": valor_bruto_final,
        "Desc. Fijo Lugar": desc_fijo_final,
        "Desc. Tarjeta": desc_tarjeta_final,
        "Desc. Adicional": desc_adicional_final,
        "Total Recibido": total_liquido_final
    }
    
    # 4. Actualizar la fila en la BASE DE DATOS y forzar la recarga del DataFrame
    if update_existing_record(data_to_update): 
        load_data_from_db.clear()
        st.session_state.atenciones_df = load_data_from_db()
        return total_liquido_final
    
    return 0 

def update_edit_bruto_price():
    """Callback: Actualiza el Valor Bruto al precio base sugerido (y guarda)."""
    lugar_edit = st.session_state.edit_lugar.upper()
    item_edit = st.session_state.edit_item
    
    # 1. Recalcular el precio sugerido
    nuevo_precio_base = PRECIOS_BASE_CONFIG.get(lugar_edit, {}).get(item_edit, st.session_state.edit_valor_bruto)
    st.session_state.edit_valor_bruto = int(nuevo_precio_base)
    
    # 2. Forzamos un guardado para reflejar el cambio en la BD (y recalculamos en vivo)
    new_total = save_edit_state_to_df() 
    if new_total > 0:
        st.success(f"Valor Bruto actualizado a {format_currency(st.session_state.edit_valor_bruto)}. Nuevo Tesoro Líquido: {format_currency(new_total)}")
        # Forzamos el rerun después de guardar para que el expander refleje el estado
        st.session_state.rerun_after_edit = True 
    else:
        st.error("Error: No se pudo actualizar el registro en la base de datos.")

def update_edit_desc_tarjeta():
    """Callback: Recalcula y actualiza el Desc. Tarjeta (y guarda)."""
    comision_pct_actual = COMISIONES_PAGO.get(st.session_state.edit_metodo, 0.00)
    valor_bruto_actual = st.session_state.edit_valor_bruto
    nuevo_desc_tarjeta = int(valor_bruto_actual * comision_pct_actual)
    
    st.session_state.original_desc_tarjeta = nuevo_desc_tarjeta
    
    new_total = save_edit_state_to_df() 
    if new_total > 0:
        st.success(f"Desc. Tarjeta recalculado a {format_currency(nuevo_desc_tarjeta)}. Nuevo Tesoro Líquido: {format_currency(new_total)}")
        st.session_state.rerun_after_edit = True 
    else:
        st.error("Error: No se pudo actualizar el registro en la base de datos.")

def update_edit_tributo():
    """Callback: Recalcula y actualiza el Tributo (Desc. Fijo Lugar) basado en Lugar y Fecha (y guarda)."""
    current_lugar_upper = st.session_state.edit_lugar.upper()
    desc_fijo_calc = DESCUENTOS_LUGAR.get(current_lugar_upper, 0) # Base
    
    # --- LÓGICA DE CÁLCULO DE TRIBUTO EN EDICIÓN ---
    if current_lugar_upper == 'CPM':
        desc_fijo_calc = int(st.session_state.edit_valor_bruto * 0.487)
    else:
        try:
            # st.session_state.edit_fecha es un objeto date/datetime (del date_input)
            current_day_name = DIAS_SEMANA[st.session_state.edit_fecha.weekday()]
        except Exception:
            current_day_name = "" 
        
        if current_lugar_upper in DESCUENTOS_REGLAS:
             try: 
                 regla_especial_monto = DESCUENTOS_REGLAS[current_lugar_upper].get(current_day_name.upper())
                 if regla_especial_monto is not None:
                     desc_fijo_calc = regla_especial_mount
             except Exception:
                 pass
             
    st.session_state.original_desc_fijo_lugar = desc_fijo_calc
    
    new_total = save_edit_state_to_df() 
    if new_total > 0:
        st.success(f"Tributo recalculado a {format_currency(desc_fijo_calc)}. Nuevo Tesoro Líquido: {format_currency(new_total)}")
        st.session_state.rerun_after_edit = True 
    else:
        st.error("Error: No se pudo actualizar el registro en la base de datos.")

def delete_record_callback(record_id):
    """Callback para eliminar un registro de la base de datos."""
    if delete_record(record_id):
        load_data_from_db.clear()
        st.session_state.atenciones_df = load_data_from_db()
        _cleanup_edit_state() # Limpiar estado de edición si se elimina el registro actual
        st.success(f"Registro ID {record_id} eliminado exitosamente.")
        st.session_state.rerun_after_edit = True 
    else:
        st.error(f"No se pudo eliminar el registro ID {record_id}.")

def edit_record_callback(record_id):
    """Callback para establecer el ID a editar y recargar la página."""
    st.session_state.edited_record_id = record_id
    st.session_state.rerun_after_edit = True # Forzar recarga para abrir el formulario


def submit_and_reset():
    """Ejecuta la lógica de guardado del formulario de registro y luego resetea el formulario."""
    
    if st.session_state.get('form_paciente', "") == "":
        st.session_state['save_error'] = "Por favor, ingresa el nombre del paciente antes de guardar."
        return 
    
    if not LUGARES or not METODOS_PAGO:
        st.session_state['save_error'] = "Error de configuración: Lugares o Métodos de Pago vacíos."
        return 
        
    paciente_nombre_guardar = st.session_state.form_paciente 
    
    resultados_finales = calcular_ingreso(
        st.session_state.form_lugar, 
        st.session_state.form_item, 
        st.session_state.form_metodo_pago, 
        st.session_state.form_desc_adic_input, 
        fecha_atencion=st.session_state.form_fecha, 
        valor_bruto_override=st.session_state.form_valor_bruto
    )
    
    nueva_atencion = {
        "Fecha": st.session_state.form_fecha.strftime('%Y-%m-%d'), 
        "Lugar": st.session_state.form_lugar, 
        "Item": st.session_state.form_item, # USAMOS 'Item' (SIN TILDE)
        "Paciente": paciente_nombre_guardar, 
        "Método Pago": st.session_state.form_metodo_pago,
        "Valor Bruto": resultados_finales['valor_bruto'],
        "Desc. Fijo Lugar": resultados_finales['desc_fijo_lugar'],
        "Desc. Tarjeta": resultados_finales['desc_tarjeta'],
        "Desc. Adicional": st.session_state.form_desc_adic_input, 
        "Total Recibido": resultados_finales['total_recibido']
    }
    
    insert_new_record(nueva_atencion)
    
    load_data_from_db.clear() 
    st.session_state.atenciones_df = load_data_from_db() 
    
    st.session_state['save_status'] = f"🎉 ¡Aventura registrada para {paciente_nombre_guardar}! El tesoro es {format_currency(resultados_finales['total_recibido'])}"

    # --- LÓGICA DE REINICIO MANUAL DE TODOS LOS WIDGETS ---
    default_lugar = LUGARES[0] if LUGARES else ''
    items_default = list(PRECIOS_BASE_CONFIG.get(default_lugar, {}).keys())
    default_item = items_default[0] if items_default else ''
    default_valor_bruto = int(PRECIOS_BASE_CONFIG.get(default_lugar, {}).get(default_item, 0))

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
    # Usamos la técnica de replace para simular el formato de miles con punto y decimal con coma (CLP)
    return f"${int(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")

def set_dark_mode_theme():
    """Establece transparencia y ajusta la apariencia para el tema oscuro."""
    # CORRECCIÓN EN CSS: row-header para quitar el fondo feo
    dark_mode_css = '''
    <style>
    .stApp, [data-testid="stAppViewBlock"], .main { background-color: transparent !important; background-image: none !important; }
    [data-testid="stSidebarContent"] { background-color: rgba(30, 30, 30, 0.9) !important; color: white; }
    /* Ajustes para el tema oscuro para mejor visibilidad */
    .css-1r6dm1, .streamlit-expander, 
    [data-testid="stMetric"], [data-testid="stVerticalBlock"],
    .stSelectbox > div:first-child, .stDateInput > div:first-child, .stTextInput > div:first-child, .stNumberInput > div:first-child, .stRadio > div,
    .stSelectbox, .stDateInput, .stTextInput, .stNumberInput, .stRadio { 
        background-color: rgba(10, 10, 10, 0.6) !important; border-radius: 10px; padding: 10px;
        color: white;
    } 
    /* Estilo para los botones en las filas */
    .stButton > button {
        background-color: #4CAF50; /* Green */
        color: white;
        padding: 5px 10px;
        text-align: center;
        text-decoration: none;
        display: inline-block;
        font-size: 12px;
        margin: 4px 2px;
        cursor: pointer;
        border-radius: 8px;
        border: none;
    }
    .stButton > button:hover {
        background-color: #45a049;
    }
    /* Estilo para la tabla (DataFrame simulado con columnas) */
    .row-header {
        font-weight: bold;
        background-color: transparent; /* AHORA TRANSPARENTE */
        padding: 8px 0;
        border-bottom: 2px solid rgba(80, 80, 80, 0.5);
    }
    .data-row {
        border-bottom: 1px solid rgba(80, 80, 80, 0.5);
        padding: 4px 0;
    }

    h1, h2, h3, h4, h5, h6, label, .css-1d391kg, [data-testid="stSidebarContent"] *, [data-testid="stHeader"] * { color: white !important; }
    .streamlit-expander label, div.stRadio > label { color: white !important; }
    </style>
    '''
    st.markdown(dark_mode_css, unsafe_allow_html=True)


# ===============================================
# 5. INTERFAZ DE USUARIO (FRONTEND)
# ===============================================

# 🚀 Configuración de la Página y Título
st.set_page_config(
    page_title="🏰 Control de Ingresos Mágicos 🪄", 
    layout="wide"
)

set_dark_mode_theme()

# *** LÓGICA DE REINICIO DE BANDERA PARA CALLBACKS DE EDICIÓN ***
if 'rerun_after_edit' not in st.session_state:
    st.session_state.rerun_after_edit = False

if st.session_state.rerun_after_edit:
    st.session_state.rerun_after_edit = False 
    st.rerun() 

# --- Inicialización de Estado ---
if 'atenciones_df' not in st.session_state:
    st.session_state.atenciones_df = load_data_from_db()
    
# Mantenemos solo el ID que se va a editar (el índice de la fila ya no es tan crítico)
if 'edited_record_id' not in st.session_state:
    st.session_state.edited_record_id = None

# --- INICIALIZACIÓN ROBUSTA DE VARIABLES DE EDICIÓN (PREVENIR ATTRIBUTEERROR) ---
# Se inicializan a valores seguros para que Streamlit no falle si intenta leerlas 
# cuando la edición no está activa.
if 'edit_lugar' not in st.session_state: st.session_state.edit_lugar = LUGARES[0] if LUGARES else ""
if 'edit_item' not in st.session_state: st.session_state.edit_item = "" 
if 'edit_paciente' not in st.session_state: st.session_state.edit_paciente = ""
if 'edit_metodo' not in st.session_state: st.session_state.edit_metodo = METODOS_PAGO[0] if METODOS_PAGO else ""
if 'edit_valor_bruto' not in st.session_state: st.session_state.edit_valor_bruto = 0
if 'edit_desc_adic' not in st.session_state: st.session_state.edit_desc_adic = 0
if 'original_desc_fijo_lugar' not in st.session_state: st.session_state.original_desc_fijo_lugar = 0
if 'original_desc_tarjeta' not in st.session_state: st.session_state.original_desc_tarjeta = 0
if 'edit_fecha' not in st.session_state: st.session_state.edit_fecha = date.today() 

st.title("🏰 Tesoro de Ingresos Fonoaudiológicos 💰")
st.markdown("✨ ¡Transforma cada atención en un diamante! ✨")

# --- Herramientas de Mantenimiento ---
if st.sidebar.button("🧹 Limpiar Cenicienta (Caché y Config)", type="secondary"):
    st.cache_data.clear() 
    st.cache_resource.clear() 
    load_data_from_db.clear() 
    re_load_global_config() 
    st.session_state.atenciones_df = load_data_from_db() 
    submit_and_reset() 
    st.success("Caché, Configuración y Datos Recargados.")
    st.rerun() 

st.sidebar.markdown("---") 

# --- Pestañas Principales ---
tab_registro, tab_dashboard, tab_config = st.tabs(["📝 Registrar Aventura", "📊 Mapa del Tesoro", "⚙️ Configuración Maestra"])

with tab_registro:
    # --- FORMULARIO DE INGRESO ---
    st.subheader("🎉 Nueva Aventura de Ingreso (Atención)")
    
    if 'save_status' in st.session_state:
        st.success(st.session_state.save_status)
        del st.session_state.save_status
        
    if 'save_error' in st.session_state:
        st.error(st.session_state.save_error)
        del st.session_state.save_error
    
    if not LUGARES or not METODOS_PAGO:
        st.error("🚨 ¡Fallo de Configuración! La lista de Lugares o Métodos de Pago está vacía.")
        
    # --- Inicialización de Valores para Formulario ---
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


    # WIDGETS REACTIVOS - Diseño de Cabecera
    st.markdown("### 📝 Datos de la Aventura")
    col_cabecera_1, col_cabecera_2, col_cabecera_3, col_cabecera_4 = st.columns(4)

    # 1. SELECTBOX LUGAR
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
    
    # 2. SELECTBOX ÍTEM
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
    
    # 3. VALOR BRUTO
    with col_cabecera_3:
        st.number_input(
            "💰 **Valor Bruto (Recompensa)**", 
            min_value=0, 
            step=1000,
            key="form_valor_bruto", 
            on_change=force_recalculate 
        )

    # 4. DESCUENTO ADICIONAL
    with col_cabecera_4:
        st.number_input(
            "✂️ **Polvo Mágico Extra (Ajuste)**", 
            min_value=-500000, 
            value=st.session_state.get('form_desc_adic_input', 0), 
            step=1000, 
            key="form_desc_adic_input",
            on_change=force_recalculate, 
            help="Ingresa un valor positivo para descuentos o negativo para cargos."
        )
    
    st.markdown("---") 

    col_c1, col_c2 = st.columns(2)
    
    with st.form("registro_atencion_form"): 
        
        with col_c1: 
            # FECHA DE ATENCIÓN
            st.date_input(
                "🗓️ Fecha de Atención", 
                st.session_state.form_fecha, 
                key="form_fecha", 
                on_change=force_recalculate 
            ) 
            
            # MÉTODO DE PAGO
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

            # PACIENTE 
            paciente = st.text_input("👤 Héroe/Heroína (Paciente/Asociado)", st.session_state.form_paciente, key="form_paciente")

        with col_c2:
            st.markdown("### Detalles de Reducciones y Tesoro Neto")

            if not LUGARES or not items_filtrados_initial:
                st.info("Configuración de Lugar/Ítem incompleta. Revisa la pestaña de Configuración.")
            else:
                
                desc_adicional_calc = st.session_state.form_desc_adic_input 
                valor_bruto_calc = st.session_state.form_valor_bruto
                
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
                
                if current_lugar_upper.upper() == 'CPM':
                    desc_lugar_label = f"Tributo al Castillo (CPM - 48.7% Bruto)"
                else:
                    try:
                        current_day_name = DIAS_SEMANA[st.session_state.form_fecha.weekday()] 
                        is_rule_applied = False
                        if current_lugar_upper in DESCUENTOS_REGLAS:
                            regla_especial_monto = DESCUENTOS_REGLAS[current_lugar_upper].get(current_day_name.upper())
                            if regla_especial_monto is not None:
                                desc_lugar_label += f" (Regla: {current_day_name})"
                                is_rule_applied = True
                        if not is_rule_applied and DESCUENTOS_LUGAR.get(current_lugar_upper, 0) > 0:
                            desc_lugar_label += " (Base)"
                    except Exception:
                        pass
                
                st.info(f"**{desc_lugar_label}:** {format_currency(resultados['desc_fijo_lugar'])}")
                
                st.markdown("###")
                st.success(
                    f"## 💎 Tesoro Total (Líquido): {format_currency(resultados['total_recibido'])}"
                )
    
        st.markdown("---") 

        st.form_submit_button(
            "✅ ¡Guardar Aventura y Tesoro!", 
            use_container_width=True, 
            type="primary",
            on_click=submit_and_reset 
        )

with tab_dashboard:
    # ===============================================
    # 6. DASHBOARD DE RESUMEN Y EDICIÓN
    # ===============================================
    st.header("✨ Mapa y Brújula de Ingresos (Dashboard)")

    df = st.session_state.atenciones_df

    if not df.empty:
        if 'Item' in df.columns and 'Ítem' not in df.columns:
            df = df.rename(columns={'Item': 'Ítem'})
            
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
        
        # --- MÉTRICAS PRINCIPALES ---
        total_ingreso = df['Total Recibido'].sum()
        total_atenciones = len(df)
        
        col_m1, col_m2 = st.columns(2)
        
        with col_m1:
            st.metric("💰 Tesoro Líquido Total", format_currency(total_ingreso))
        with col_m2:
            st.metric("👥 Atenciones Registradas", total_atenciones)
            
        st.markdown("---")
        
        # --- GRÁFICOS RESTAURADOS ---
        st.subheader("Gráficos de Distribución del Tesoro")
        col_g1, col_g2 = st.columns(2)

        # Gráfico de Ingreso por Lugar (Pie Chart)
        with col_g1:
            df_lugar = df.groupby('Lugar')['Total Recibido'].sum().reset_index()
            fig_lugar = px.pie(
                df_lugar, 
                values='Total Recibido', 
                names='Lugar', 
                title='Distribución por Castillo/Lugar',
                hole=.3
            )
            fig_lugar.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
            st.plotly_chart(fig_lugar, use_container_width=True)

        # Gráfico de Ingreso por Ítem (Bar Chart)
        with col_g2:
            df_item = df.groupby('Ítem')['Total Recibido'].sum().reset_index().sort_values(by='Total Recibido', ascending=False)
            fig_item = px.bar(
                df_item.head(10), 
                x='Ítem', 
                y='Total Recibido', 
                title='Top 10 Pociones/Procedimientos (Ingreso Líquido)',
                labels={'Total Recibido': 'Tesoro Líquido', 'Ítem': 'Ítem'}
            )
            fig_item.update_layout(xaxis={'categoryorder':'total descending'})
            st.plotly_chart(fig_item, use_container_width=True)
        
        st.markdown("---")
        
        # Gráfico de Tendencia Semanal
        st.subheader("Tendencia Histórica del Tesoro")
        df_grouped = df.groupby(df['Fecha'].dt.to_period('W')).agg(
            {'Total Recibido': 'sum'}
        ).reset_index()
        df_grouped['Fecha'] = df_grouped['Fecha'].dt.to_timestamp()
        
        fig = px.line(
            df_grouped, 
            x='Fecha', 
            y='Total Recibido', 
            title='Tesoro Líquido Acumulado por Semana',
            labels={'Total Recibido': 'Tesoro Líquido', 'Fecha': 'Semana'},
            line_shape='spline'
        )
        fig.update_layout(xaxis_tickformat="%Y-%m-%d")
        st.plotly_chart(fig, use_container_width=True)
        
        
        # --- TABLA DE DATOS CRUDA Y EDICIÓN ---
        st.subheader("🗺️ Detalles de las Aventuras Registradas")
        st.info("Utiliza el botón **Editar ✏️** al lado de cada registro para abrir el formulario de edición. La tabla está ordenada por **ID Ascendente (1, 2, 3...)**.")
        
        
        # 1. Definir columnas y anchos para la tabla simulada
        # Anchos relativos: [Botón, ID, Fecha, Lugar, Ítem, Paciente, Bruto, Neto, Ajustes]
        cols_widths = [1, 0.5, 1.2, 1.5, 1.5, 2, 1.2, 1.2, 1] 
        cols_names = ["", "ID", "Fecha", "Lugar", "Ítem", "Paciente", "Valor Bruto", "Total Recibido", "Ajustes"]

        # 2. Encabezados de la tabla
        header_cols = st.columns(cols_widths)
        for i, name in enumerate(cols_names):
            # CORRECCIÓN DE ESTILO: Usamos un span para aplicar el estilo de encabezado definido en el CSS (ahora transparente)
            header_cols[i].markdown(f"<span class='row-header'>{name}</span>", unsafe_allow_html=True)
        st.markdown("---")


        # 3. Iterar sobre el DataFrame para mostrar los datos y los botones
        # EL DATAFRAME df YA ESTÁ ORDENADO POR ID ASCENDENTE GRACIAS A load_data_from_db
        for index, row in df.iterrows():
            
            # Formatear datos
            fecha_str = row['Fecha'].strftime('%Y-%m-%d')
            bruto_str = format_currency(row['Valor Bruto'])
            neto_str = format_currency(row['Total Recibido'])
            ajustes_str = format_currency(row['Desc. Adicional'] + row['Desc. Tarjeta'] + row['Desc. Fijo Lugar'])
            
            # Crear las columnas para la fila actual
            data_cols = st.columns(cols_widths)

            # Botón de edición
            with data_cols[0]:
                st.button("Editar ✏️", key=f"edit_btn_{row['id']}", on_click=edit_record_callback, args=(row['id'],))
            
            # Datos de la fila
            data_cols[1].markdown(f"<span class='data-row'>{row['id']}</span>", unsafe_allow_html=True)
            data_cols[2].markdown(f"<span class='data-row'>{fecha_str}</span>", unsafe_allow_html=True)
            data_cols[3].markdown(f"<span class='data-row'>{row['Lugar']}</span>", unsafe_allow_html=True)
            data_cols[4].markdown(f"<span class='data-row'>{row['Ítem']}</span>", unsafe_allow_html=True)
            data_cols[5].markdown(f"<span class='data-row'>{row['Paciente']}</span>", unsafe_allow_html=True)
            data_cols[6].markdown(f"<span class='data-row'>{bruto_str}</span>", unsafe_allow_html=True)
            data_cols[7].markdown(f"<span class='data-row'>{neto_str}</span>", unsafe_allow_html=True)
            data_cols[8].markdown(f"<span class='data-row'>{ajustes_str}</span>", unsafe_allow_html=True)
            
            # Pequeña separación visual
            st.markdown("---")
        
        
        # --- FORMULARIO DE EDICIÓN (DESPLEGADO CONDICIONALMENTE) ---
        
        edited_id = st.session_state.edited_record_id
        
        if edited_id is not None and edited_id in df['id'].values:
            
            # 1. Cargar la fila a editar
            edit_row = df[df['id'] == edited_id].iloc[0]
            
            # 2. 🚨 CARGAR ESTADO DE SESIÓN AL ABRIR EL FORMULARIO 🚨
            
            current_paciente = st.session_state.get('edit_paciente', None)
            if current_paciente is None or current_paciente != edit_row['Paciente']:
                 st.session_state.edit_paciente = edit_row['Paciente']
                 
            st.session_state.edit_valor_bruto = edit_row['Valor Bruto']
            st.session_state.edit_desc_adic = edit_row['Desc. Adicional']
            st.session_state.original_desc_fijo_lugar = edit_row['Desc. Fijo Lugar']
            st.session_state.original_desc_tarjeta = edit_row['Desc. Tarjeta']
            st.session_state.edit_fecha = edit_row['Fecha'].date()
            
            st.session_state.edit_lugar = edit_row['Lugar']
            st.session_state.edit_item = edit_row['Ítem']
            st.session_state.edit_metodo = edit_row['Método Pago']
            
            
            # 3. Dibujar el formulario
            st.markdown(f"## ✏️ Editando Registro ID: {edited_id} ({edit_row['Paciente']})")
            
            # Usamos un `st.form` para asegurar que los botones de guardado no activen un re-run completo
            with st.form(key=f"edit_form_{edited_id}"):
                
                col_e1, col_e2, col_e3 = st.columns([1, 1, 1.2]) 
                
                # =============================================================
                # COLUMNA 1: DATOS CLAVE
                # =============================================================
                with col_e1:
                    st.subheader("Datos Clave")
                    
                    # FECHA (st.date_input) 
                    st.date_input("🗓️ Fecha de Atención", st.session_state.edit_fecha, key="edit_fecha")
                    
                    # LUGAR (st.selectbox) 
                    try:
                        lugar_idx = LUGARES.index(st.session_state.edit_lugar)
                    except ValueError:
                        lugar_idx = 0
                    st.selectbox("📍 Lugar", options=LUGARES, key="edit_lugar", index=lugar_idx)

                    # ÍTEM (st.selectbox) 
                    items_edit_list = list(PRECIOS_BASE_CONFIG.get(st.session_state.edit_lugar, {}).keys())
                    try:
                         item_idx = items_edit_list.index(st.session_state.edit_item) if st.session_state.edit_item in items_edit_list else 0
                    except (ValueError, KeyError):
                        item_idx = 0
                    st.selectbox("📋 Ítem", options=items_edit_list, key="edit_item", index=item_idx)
                    
                    # PACIENTE (st.text_input) 
                    st.text_input("👤 Paciente", key="edit_paciente")
                    
                    # MÉTODO DE PAGO (st.selectbox) 
                    try:
                        metodo_idx = METODOS_PAGO.index(st.session_state.edit_metodo)
                    except ValueError:
                        metodo_idx = 0
                    st.selectbox("💳 Método Pago", options=METODOS_PAGO, key="edit_metodo", index=metodo_idx)

                
                # =============================================================
                # COLUMNA 2: VALORES ECONÓMICOS EDITABLES/RECALCULABLES
                # =============================================================
                with col_e2:
                    st.subheader("Ajustes Financieros")
                    
                    # VALOR BRUTO - CORREGIDO: SE ELIMINÓ on_change
                    st.number_input(
                        "💰 Valor Bruto (Recompensa)", 
                        min_value=0, 
                        step=1000, 
                        key="edit_valor_bruto",
                    )
                    st.form_submit_button("🔄 Actualizar a Precio Base Sugerido", key='btn_update_price_form', on_click=update_edit_bruto_price, use_container_width=True)

                    st.markdown("---")

                    # DESCUENTO ADICIONAL (Editable) - CORREGIDO: SE ELIMINÓ on_change
                    st.number_input(
                        "✂️ Ajuste Extra (Desc. Adic.)", 
                        min_value=-500000, 
                        step=1000, 
                        key="edit_desc_adic",
                    )
                    
                    st.markdown("---")
                    
                    # Botones de Recálculo de Tributo y Tarjeta
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        # Este botón recalcula y guarda Desc. Fijo Lugar, usando Fecha y Lugar actuales
                        st.form_submit_button("🔄 Recalcular Tributo/Regla", key='btn_update_tributo_form', on_click=update_edit_tributo, use_container_width=True)
                    with col_btn2:
                         # Este botón recalcula y guarda Desc. Tarjeta, usando Método Pago y Valor Bruto actuales
                        st.form_submit_button("🔄 Recalcular Tarjeta", key='btn_update_tarjeta_form', on_click=update_edit_desc_tarjeta, use_container_width=True)


                # =============================================================
                # COLUMNA 3: CÁLCULOS Y TOTALES EN VIVO
                # =============================================================
                with col_e3:
                    st.subheader("Estado Actual (No Editable)")
                    
                    # Usamos los valores originales/recalculados (de los callbacks)
                    current_desc_fijo = st.session_state.get('original_desc_fijo_lugar', edit_row['Desc. Fijo Lugar'])
                    current_desc_tarjeta = st.session_state.get('original_desc_tarjeta', edit_row['Desc. Tarjeta'])
                    
                    # Calcular el total líquido temporal (Vista Previa)
                    total_liquido_live = (
                        st.session_state.edit_valor_bruto
                        - current_desc_fijo
                        - current_desc_tarjeta
                        - st.session_state.edit_desc_adic
                    )
                    
                    # Mostrar las métricas de descuento actuales
                    st.metric("❌ Desc. Fijo/Tributo", format_currency(current_desc_fijo))
                    st.metric("💳 Desc. Tarjeta", format_currency(current_desc_tarjeta))
                    st.metric("✂️ Desc. Adicional", format_currency(st.session_state.edit_desc_adic))
                    
                    st.markdown("---")
                    
                    st.success(f"### 💎 Tesoro Líquido (Vista Previa): {format_currency(total_liquido_live)}")
                    st.error(f"**Total Guardado Anterior:** {format_currency(edit_row['Total Recibido'])}")


                # --- Botones de Control Final ---
                st.markdown("---")
                col_final1, col_final2, col_final3 = st.columns([0.6, 0.2, 0.2])
                
                # Botón de Guardado general
                with col_final1:
                    # Este botón guarda todos los inputs (incluidos los de Recalcular)
                    if st.form_submit_button("💾 Aplicar Cambios y Cerrar Edición", type="primary"):
                        new_total = save_edit_state_to_df()
                        st.success(f"Registro ID {edited_id} actualizado y guardado. Nuevo Total: {format_currency(new_total)}")
                        _cleanup_edit_state()
                        st.session_state.rerun_after_edit = True 

                # Botón de Cierre Manual
                with col_final2:
                    st.form_submit_button("❌ Cerrar Edición", key='btn_close_edit_form', on_click=_cleanup_edit_state)
                    
                # Botón de Eliminar CORREGIDO
                with col_final3:
                    st.form_submit_button(
                        "🗑️ Eliminar", 
                        key='btn_delete_form', # <--- CORRECCIÓN CLAVE: Clave única
                        type="danger", 
                        help="Elimina permanentemente este registro.", 
                        on_click=delete_record_callback, # <--- CORRECCIÓN CLAVE: Usamos on_click
                        args=(edited_id,)
                    )
        
    else:
        st.warning("Aún no hay registros de atenciones para mostrar en el mapa del tesoro. ¡Registra una aventura primero!")

with tab_config:
    # ===============================================
    # 7. CONFIGURACIÓN MAESTRA
    # ===============================================
    st.header("⚙️ Configuración Maestra")
    st.info("⚠️ Los cambios aquí modifican el cálculo para **TODAS** las nuevas entradas y se guardan inmediatamente.")

    # --- Pestañas de Configuración ---
    tab_precios, tab_descuentos, tab_comisiones = st.tabs(["Precios por Ítem", "Descuentos Fijos (Tributo)", "Comisiones de Pago"])
    
    # 1. PRECIOS POR LUGAR/ÍTEM
    with tab_precios:
        st.subheader("💰 Recompensas Base (Valor Bruto)")
        
        precios_df_list = []
        for lugar, items in PRECIOS_BASE_CONFIG.items():
            for item, precio in items.items():
                precios_df_list.append({'Lugar': lugar, 'Ítem': item, 'Precio Sugerido': precio})
                
        precios_df = pd.DataFrame(precios_df_list)
        
        edited_precios_df = st.data_editor(
            precios_df,
            key="precios_editor",
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Precio Sugerido": st.column_config.NumberColumn(format="$%d")
            }
        )
        
        if st.button("💾 Guardar Configuración de Precios", type="primary"):
            new_precios_config = {}
            for index, row in edited_precios_df.iterrows():
                lugar = str(row['Lugar']).upper()
                item = str(row['Ítem'])
                precio = sanitize_number_input(row['Precio Sugerido'])
                
                if lugar not in new_precios_config:
                    new_precios_config[lugar] = {}
                
                if item and precio >= 0:
                    new_precios_config[lugar][item] = precio
                    
            save_config(new_precios_config, PRECIOS_FILE)
            re_load_global_config() 
            st.success("Configuración de Precios Guardada y Recargada.")
            st.rerun()

    # 2. DESCUENTOS FIJOS POR LUGAR (TRIBUTO) Y REGLAS
    with tab_descuentos:
        
        # --- DESCUENTO BASE POR LUGAR ---
        st.subheader("✂️ Tributo Fijo Base por Castillo/Lugar")

        descuentos_df = pd.DataFrame(list(DESCUENTOS_LUGAR.items()), columns=['Lugar', 'Desc. Fijo Base'])
        
        edited_descuentos_df = st.data_editor(
            descuentos_df,
            key="descuentos_editor",
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Desc. Fijo Base": st.column_config.NumberColumn(format="$%d")
            }
        )
        
        if st.button("💾 Guardar Configuración de Tributo Base", type="primary"):
            new_descuentos_config = {}
            for index, row in edited_descuentos_df.iterrows():
                lugar = str(row['Lugar']).upper()
                descuento = sanitize_number_input(row['Desc. Fijo Base'])
                if lugar:
                    new_descuentos_config[lugar] = descuento
                    
            save_config(new_descuentos_config, DESCUENTOS_FILE)
            re_load_global_config()
            st.success("Configuración de Tributo Base Guardada y Recargada.")
            st.rerun()
            
        st.markdown("---")
        
        # --- REGLAS DE DESCUENTO POR DÍA ---
        st.subheader("🗓️ Reglas de Tributo por Día de la Semana")
        
        with st.expander("🛠️ Editar Reglas Diarias", expanded=False):
            
            reglas_list = []
            for lugar, reglas in DESCUENTOS_REGLAS.items():
                for dia, monto in reglas.items():
                    reglas_list.append({'Lugar': lugar, 'Día': dia, 'Tributo Diario': monto})
            
            reglas_df = pd.DataFrame(reglas_list)
            
            edited_reglas_df = st.data_editor(
                reglas_df,
                key="reglas_editor",
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "Tributo Diario": st.column_config.NumberColumn(format="$%d"),
                    "Día": st.column_config.SelectboxColumn(options=DIAS_SEMANA)
                }
            )

            if st.button("💾 Guardar Reglas Diarias", type="secondary"):
                new_reglas_config = {}
                for index, row in edited_reglas_df.iterrows():
                    lugar = str(row['Lugar']).upper()
                    dia = str(row['Día']).upper()
                    monto = sanitize_number_input(row['Tributo Diario'])
                    
                    if lugar not in new_reglas_config:
                        new_reglas_config[lugar] = {}
                        
                    if dia:
                        new_reglas_config[lugar][dia] = monto
                        
                save_config(new_reglas_config, REGLAS_FILE)
                re_load_global_config()
                st.success("Configuración de Reglas Diarias Guardada y Recargada.")
                st.rerun()


    # 3. COMISIONES POR MÉTODO DE PAGO
    with tab_comisiones:
        st.subheader("💳 Comisiones por Método de Pago")
        
        comisiones_df = pd.DataFrame(list(COMISIONES_PAGO.items()), columns=['Método de Pago', 'Comisión %'])
        
        edited_comisiones_df = st.data_editor(
            comisiones_df,
            key="comisiones_editor",
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Comisión %": st.column_config.NumberColumn(format="%.2f")
            }
        )
        
        if st.button("💾 Guardar Configuración de Comisiones", type="primary"):
            new_comisiones_config = {}
            for index, row in edited_comisiones_df.iterrows():
                metodo = str(row['Método de Pago']).upper()
                comision = float(row['Comisión %'])
                if metodo:
                    new_comisiones_config[metodo] = comision
                    
            save_config(new_comisiones_config, COMISIONES_FILE)
            re_load_global_config()
            st.success("Configuración de Comisiones Guardada y Recargada.")
            st.rerun()
