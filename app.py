import streamlit as st
import pandas as pd
from datetime import date
import json 
import time 
import plotly.express as px
import numpy as np 
# import sqlite3  # YA NO USAMOS SQLITE3
import psycopg2 # USAMOS ESTE PARA POSTGRESQL/SUPABASE
from psycopg2 import sql # Para construir queries de forma segura
import os 
from dateutil.parser import parse

# ===============================================
# 1. CONFIGURACIÓN Y BASES DE DATOS (MAESTRAS)
# ===============================================

# DB_FILE ya no es necesario
PRECIOS_FILE = 'precios_base.json'
DESCUENTOS_FILE = 'descuentos_lugar.json'
COMISIONES_FILE = 'comisiones_pago.json'
REGLAS_FILE = 'descuentos_reglas.json' 


def save_config(data, filename):
    """Guarda la configuración a un archivo JSON."""
    try:
        # Nota: estos archivos (json) se guardarán en el sistema de archivos
        # de Streamlit Cloud. Son más estables que SQLite, pero se recomienda
        # usar Google Sheets si estos archivos cambian muy a menudo.
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4, sort_keys=True)
            f.flush() 
    except Exception as e:
        st.error(f"Error al guardar el archivo {filename}: {e}")

# ... (load_config y el resto de la configuración de maestras se mantiene igual) ...

def load_config(filename):
    """Carga la configuración desde un archivo JSON, creando el archivo si no existe."""
    try:
        if not os.path.exists(filename):
            raise FileNotFoundError
            
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
            default_data = {'ALERCE': 5000, 'AMAR AUSTRAL': 7000, 'CPM': 0} 
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
    """Convierte un valor de input de tabla (que puede ser NaN, string o float) a int."""
    if pd.isna(value) or value is None or value == "":
        return 0
    
    try:
        return int(float(value)) 
    except (ValueError, TypeError):
        return 0 

def re_load_global_config():
    """Recarga todas las variables de configuración global y las listas derivadas."""
    global PRECIOS_BASE_CONFIG, DESCUENTOS_LUGAR, COMISIONES_PAGO, DESCUENTOS_REGLAS
    global LUGARES, METODOS_PAGO
    
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
# 2. FUNCIONES DE PERSISTENCIA (POSTGRESQL)
# ===============================================

@st.cache_resource
def get_db_connection():
    """Establece la conexión a la base de datos PostgreSQL usando secrets."""
    try:
        conn = psycopg2.connect(st.secrets["connections"]["postgres_uri"])
        conn.autocommit = True # Necesario para CREATE TABLE
        cursor = conn.cursor()

        # Asegura la existencia de la tabla (usando comillas dobles para nombres con espacios)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS atenciones (
                id SERIAL PRIMARY KEY,
                Fecha DATE,
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
    except KeyError:
        st.error("🚨 Error: No se encontró la URI de PostgreSQL en `.streamlit/secrets.toml`.")
        return None
    except Exception as e:
        st.error(f"🚨 Error de conexión a la BD: {e}")
        return None

@st.cache_data(show_spinner="Cargando Tesoro desde la Nube...")
def load_data_from_db():
    """Carga los datos desde PostgreSQL a un DataFrame."""
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
        
    # Usar pd.read_sql para obtener los datos directamente
    try:
        # Aseguramos el orden ascendente por ID
        df = pd.read_sql_query('SELECT * FROM atenciones ORDER BY id ASC', conn)
        
        if not df.empty:
            df['Fecha'] = pd.to_datetime(df['Fecha']).dt.date
            
            # Forzamos las columnas clave a enteros
            numeric_cols = ['id', 'Valor Bruto', 'Desc. Fijo Lugar', 'Desc. Tarjeta', 'Desc. Adicional', 'Total Recibido']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

        if 'Item' in df.columns:
            df = df.rename(columns={'Item': 'Ítem'})
            
        return df
        
    except Exception as e:
        st.error(f"Error al cargar datos desde PostgreSQL: {e}")
        return pd.DataFrame()


def insert_new_record(record_dict):
    """Inserta un nuevo registro en la tabla de atenciones en PostgreSQL."""
    conn = get_db_connection()
    if conn is None:
        return False
        
    cursor = conn.cursor()
    
    # Prepara los nombres de las columnas y placeholders
    cols = list(record_dict.keys())
    values = list(record_dict.values())
    
    # Crea una lista de identificadores SQL para las columnas (asegurando comillas dobles)
    col_names = sql.SQL(', ').join(map(sql.Identifier, cols))
    
    # Crea una lista de placeholders para los valores (%s)
    placeholders = sql.SQL(', ').join(sql.Placeholder() * len(values))
    
    # Construye el query usando sql.SQL para seguridad
    query = sql.SQL("INSERT INTO atenciones ({}) VALUES ({})").format(col_names, placeholders)
    
    try:
        cursor.execute(query, values)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error al insertar en la BD: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()


def update_existing_record(record_dict):
    """Actualiza un registro existente usando su 'id' como clave en PostgreSQL."""
    conn = get_db_connection()
    if conn is None:
        return False
        
    cursor = conn.cursor()
    record_id = record_dict.pop('id') 
    
    set_clauses = []
    values = []
    
    # Construir las cláusulas SET de forma segura
    for k, v in record_dict.items():
        set_clauses.append(sql.SQL("{} = %s").format(sql.Identifier(k)))
        values.append(v)
        
    set_clause = sql.SQL(', ').join(set_clauses)
    
    # Añadir el ID al final de los valores y construir el query
    values.append(record_id)
    query = sql.SQL("UPDATE atenciones SET {} WHERE id = %s").format(set_clause)

    try:
        cursor.execute(query, values)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error al actualizar la BD: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()

# ... (El resto de las funciones de cálculo y la lógica de la interfaz de usuario se mantiene igual) ...


# ===============================================
# 3. FUNCIONES DE CÁLCULO Y LÓGICA DE NEGOCIO
# ===============================================

def format_currency(value):
    """Función para formatear números como moneda en español con punto y coma."""
    if value is None or not isinstance(value, (int, float)):
          value = 0
    # Usamos la técnica de replace para simular el formato de miles con punto y decimal con coma (CLP)
    return f"${int(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
    valor_bruto = valor_bruto_override if (valor_bruto_override is not None and valor_bruto_override > 0) else precio_base
    
    # 2. LÓGICA DE DESCUENTO FIJO CONDICIONAL (Tributo)
    desc_fijo_lugar = DESCUENTOS_LUGAR.get(lugar_upper, 0) 
    
    # *** REGLA ESPECIAL PARA CPM: 48.7% DEL VALOR BRUTO ***
    if lugar_upper == 'CPM':
        desc_fijo_lugar = int(valor_bruto * 0.487) 
    else:
        # 2.1. Revisar si existe una regla especial para el día
        try:
            if isinstance(fecha_atencion, date):
                fecha_obj = fecha_atencion
            else:
                fecha_obj = parse(fecha_atencion).date() 
            
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
    desc_tarjeta = int(valor_bruto * comision_pct)
    
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

def update_edit_price(edited_id):
    """Callback para actualizar precio sugerido en el modal de edición."""
    lugar_key_edit = st.session_state.get(f'edit_lugar_{edited_id}', '').upper()
    item_key_edit = st.session_state.get(f'edit_item_{edited_id}', '')
    
    if not lugar_key_edit or not item_key_edit:
        st.session_state[f'edit_valor_bruto_{edited_id}'] = 0
        return
        
    precio_base_sugerido_edit = PRECIOS_BASE_CONFIG.get(lugar_key_edit, {}).get(item_key_edit, 0)
    st.session_state[f'edit_valor_bruto_{edited_id}'] = int(precio_base_sugerido_edit)
    
def _cleanup_edit_state():
    """Limpia las claves de sesión relacionadas con el modo de edición para forzar el cierre del expander."""
    edited_id = st.session_state.edited_record_id
    if edited_id is None:
        return
        
    keys_to_delete = [
        f'edit_valor_bruto_{edited_id}', f'edit_desc_adic_{edited_id}', 
        'original_desc_fijo_lugar', 'original_desc_tarjeta', 
        f'edit_lugar_{edited_id}', f'edit_item_{edited_id}', 
        f'edit_paciente_{edited_id}', f'edit_metodo_{edited_id}', 
        f'edit_fecha_{edited_id}',
        f'btn_close_edit_form_{edited_id}', 
        f'btn_save_edit_form_{edited_id}', 
        f'btn_update_price_form_{edited_id}', 
        f'btn_update_tributo_form_{edited_id}', 
        f'btn_update_tarjeta_form_{edited_id}', 
    ]
    
    for key in keys_to_delete:
        if key in st.session_state: del st.session_state[key] 
        
    st.session_state.edited_record_id = None 
    st.session_state.input_id_edit = None 
    
    # 🚨 LIMPIEZA DE ESTADOS DE ELIMINACIÓN ELIMINADA 🚨
    
    
def save_edit_state_to_df():
    """
    Guarda el estado actual de los inputs de edición DIRECTAMENTE en la base de datos PostgreSQL.
    Retorna el Tesoro Líquido calculado.
    """
    if st.session_state.edited_record_id is None:
        st.warning("Error: No hay un ID de registro para guardar la edición.")
        return 0
        
    record_id = st.session_state.edited_record_id
    
    # ASEGURAR TIPOS NUMÉRICOS AL LEER DEL WIDGET
    try:
        valor_bruto_final = int(st.session_state[f'edit_valor_bruto_{record_id}'])
    except:
        valor_bruto_final = 0
    
    try:
        desc_adicional_final = int(st.session_state[f'edit_desc_adic_{record_id}'])
    except:
        desc_adicional_final = 0
        
    # Obtener los descuentos actualizados (o los originales si no se recalcularon)
    desc_fijo_final = int(st.session_state.get('original_desc_fijo_lugar', 0))
    desc_tarjeta_final = int(st.session_state.get('original_desc_tarjeta', 0))
    
    total_liquido_final = (
        valor_bruto_final
        - desc_fijo_final
        - desc_tarjeta_final
        - desc_adicional_final
    )
    
    data_to_update = {
        "id": record_id, 
        "Fecha": st.session_state[f'edit_fecha_{record_id}'].strftime('%Y-%m-%d'),
        "Lugar": st.session_state[f'edit_lugar_{record_id}'],
        "Item": st.session_state[f'edit_item_{record_id}'], 
        "Paciente": st.session_state[f'edit_paciente_{record_id}'],
        "Método Pago": st.session_state[f'edit_metodo_{record_id}'],
        "Valor Bruto": valor_bruto_final,
        "Desc. Fijo Lugar": desc_fijo_final,
        "Desc. Tarjeta": desc_tarjeta_final,
        "Desc. Adicional": desc_adicional_final,
        "Total Recibido": total_liquido_final 
    }
    
    if update_existing_record(data_to_update): 
        # Es crucial que la data se recargue después de guardar en la DB
        load_data_from_db.clear()
        st.session_state.atenciones_df = load_data_from_db()
        return total_liquido_final
    
    return 0 

# =========================================================================
# FUNCIONES DE CALLBACKS DE EDICIÓN
# =========================================================================

def update_edit_bruto_price(edited_id):
    """Callback: Actualiza el Valor Bruto al precio base sugerido (y guarda)."""
    lugar_edit = st.session_state[f'edit_lugar_{edited_id}'].upper()
    item_edit = st.session_state[f'edit_item_{edited_id}']
    
    precio_actual = st.session_state[f'edit_valor_bruto_{edited_id}']
    nuevo_precio_base = PRECIOS_BASE_CONFIG.get(lugar_edit, {}).get(item_edit, precio_actual)
    
    # 1. Actualizar el widget de la sesión
    st.session_state[f'edit_valor_bruto_{edited_id}'] = int(nuevo_precio_base)
    
    # 2. Guardar en la DB con el nuevo valor
    new_total = save_edit_state_to_df() 
    
    if new_total > 0:
        st.toast(f"Valor Bruto actualizado a {format_currency(st.session_state[f'edit_valor_bruto_{edited_id}'])}$. Nuevo Tesoro Líquido: {format_currency(new_total)}", icon="🔄")

def update_edit_desc_tarjeta(edited_id):
    """Callback: Recalcula y actualiza el Desc. Tarjeta (y guarda)."""
    metodo_pago_actual = st.session_state[f'edit_metodo_{edited_id}']
    valor_bruto_actual = st.session_state[f'edit_valor_bruto_{edited_id}']
    
    comision_pct_actual = COMISIONES_PAGO.get(metodo_pago_actual.upper(), 0.00)
    nuevo_desc_tarjeta = int(valor_bruto_actual * comision_pct_actual)
    
    # 1. Actualizar el valor en el estado de sesión
    st.session_state.original_desc_tarjeta = nuevo_desc_tarjeta
    
    # 2. Guardar en la DB con el nuevo valor de descuento de tarjeta
    new_total = save_edit_state_to_df() 
    
    if new_total > 0:
        st.toast(f"Desc. Tarjeta recalculado a {format_currency(nuevo_desc_tarjeta)}$. Nuevo Tesoro Líquido: {format_currency(new_total)}", icon="💳")

def update_edit_tributo(edited_id):
    """Callback: Recalcula y actualiza el Tributo (Desc. Fijo Lugar) basado en Lugar y Fecha (y guarda)."""
    current_lugar_upper = st.session_state[f'edit_lugar_{edited_id}'].upper()
    current_valor_bruto = st.session_state[f'edit_valor_bruto_{edited_id}']
    desc_fijo_calc = DESCUENTOS_LUGAR.get(current_lugar_upper, 0)
    
    # --- LÓGICA DE CÁLCULO DE TRIBUTO EN EDICIÓN ---
    if current_lugar_upper == 'CPM':
        desc_fijo_calc = int(current_valor_bruto * 0.487)
    else:
        try:
            if isinstance(st.session_state[f'edit_fecha_{edited_id}'], date):
                 current_date_obj = st.session_state[f'edit_fecha_{edited_id}']
            else:
                 current_date_obj = parse(st.session_state[f'edit_fecha_{edited_id}']).date()
                 
            current_day_name = DIAS_SEMANA[current_date_obj.weekday()]
        except Exception:
            current_day_name = "" 
        
        if current_lugar_upper in DESCUENTOS_REGLAS:
             try: 
                 regla_especial_monto = DESCUENTOS_REGLAS[current_lugar_upper].get(current_day_name.upper())
                 if regla_especial_monto is not None:
                     desc_fijo_calc = regla_especial_monto
             except Exception:
                 pass
             
    # 1. Actualizar el valor en el estado de sesión
    st.session_state.original_desc_fijo_lugar = desc_fijo_calc
    
    # 2. Guardar en la DB con el nuevo valor de tributo
    new_total = save_edit_state_to_df() 
    
    if new_total > 0:
        st.toast(f"Tributo recalculado a {format_currency(desc_fijo_calc)}$. Nuevo Tesoro Líquido: {format_currency(new_total)}", icon="🏛️")


def edit_record_callback(record_id):
    """Callback para establecer el ID a editar."""
    if st.session_state.edited_record_id is not None:
        _cleanup_edit_state() 
        
    st.session_state.edited_record_id = record_id

# 🚨 FUNCIONES DE CALLBACKS Y FLUJO DE ELIMINACIÓN ELIMINADAS 🚨

def submit_and_reset():
    """Ejecuta la lógica de guardado del formulario de registro y luego resetea el formulario."""
    
    if st.session_state.get('form_paciente', "") == "":
        st.session_state['save_error'] = "Por favor, ingresa el nombre del paciente antes de guardar."
        return 
    
    if not LUGARES or not METODOS_PAGO:
        st.session_state['save_error'] = "Error de configuración: Lugares o Métodos de Pago vacíos."
        return 
        
    paciente_nombre_guardar = st.session_state.form_paciente 
    
    resultados_calculados = calcular_ingreso( 
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
        "Item": st.session_state.form_item, 
        "Paciente": paciente_nombre_guardar, 
        "Método Pago": st.session_state.form_metodo_pago,
        "Valor Bruto": resultados_calculados['valor_bruto'],
        "Desc. Fijo Lugar": resultados_calculados['desc_fijo_lugar'],
        "Desc. Tarjeta": resultados_calculados['desc_tarjeta'],
        "Desc. Adicional": st.session_state.form_desc_adic_input, 
        "Total Recibido": resultados_calculados['total_recibido']
    }
    
    insert_new_record(nueva_atencion)
    
    load_data_from_db.clear() 
    st.session_state.atenciones_df = load_data_from_db() 
    
    st.session_state['save_status'] = f"🎉 ¡Aventura registrada para {paciente_nombre_guardar}! El tesoro es {format_currency(resultados_calculados['total_recibido'])}"

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

def set_dark_mode_theme():
    """Establece transparencia y ajusta la apariencia para el tema oscuro."""
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
        background-color: #4CAF50; 
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
        background-color: transparent; 
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

# --- Inicialización de Estado ---
if 'atenciones_df' not in st.session_state:
    st.session_state.atenciones_df = load_data_from_db()
    
if 'edited_record_id' not in st.session_state:
    st.session_state.edited_record_id = None
    
# Estado de limpieza de edición pendiente (mantenido)
if 'deletion_pending_cleanup' not in st.session_state:
    st.session_state.deletion_pending_cleanup = False
    
# Estado para el input de ID de edición
if 'input_id_edit' not in st.session_state:
    st.session_state.input_id_edit = None 
    
# 🚨 ESTADOS DE ELIMINACIÓN ELIMINADOS 🚨


st.title("🏰 Tesoro de Ingresos Fonoaudiológicos 💰")
st.markdown("✨ ¡Transforma cada atención en un diamante! ✨")

# 🚨 BLOQUE DE LIMPIEZA POST-ELIMINACIÓN ELIMINADO 🚨

# Bloque de limpieza de edición (mantenido)
if st.session_state.deletion_pending_cleanup:
    with st.spinner("Limpiando estado y recargando la aplicación..."):
        _cleanup_edit_state() 
        st.session_state.deletion_pending_cleanup = False
        st.rerun() 

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
    # =========================================================================
    # FORMULARIO DE INGRESO 
    # =========================================================================
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
    
    with col_cabecera_3:
        st.number_input(
            "💰 **Valor Bruto (Recompensa)**", 
            min_value=0, 
            step=1000,
            key="form_valor_bruto", 
            on_change=force_recalculate 
        )

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
            st.date_input(
                "🗓️ Fecha de Atención", 
                st.session_state.form_fecha, 
                key="form_fecha", 
                on_change=force_recalculate 
            ) 
            
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

            st.text_input("👤 Héroe/Heroína (Paciente/Asociado)", st.session_state.form_paciente, key="form_paciente")

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

                st.warning(f"**Desc. Tarjeta 🧙‍♀️ ({COMISIONES_PAGO.get(st.session_state.form_metodo_pago.upper(), 0.00)*100:.0f}%):** {format_currency(resultados['desc_tarjeta'])}")
                
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

    df = st.session_state.atenciones_df.copy()
    
    if not df.empty:
        # Renombrar columnas para la visualización
        df = df.rename(columns={
            'id': 'ID',
            'Desc. Fijo Lugar': 'Desc. Tributo',
            'Desc. Tarjeta': 'Desc. Tarjeta',
            'Desc. Adicional': 'Desc. Ajuste',
            'Total Recibido': 'Tesoro Líquido',
        })
        
        columns_to_show = ['ID', 'Fecha', 'Lugar', 'Ítem', 'Paciente', 'Método Pago', 'Valor Bruto', 'Desc. Tributo', 'Desc. Ajuste', 'Tesoro Líquido']
        df_display = df[columns_to_show]
        
        df_display['Fecha'] = df_display['Fecha'].astype(str)
        
        # --- MÉTRICAS Y GRÁFICOS (Implementación mantenida) ---
        total_ingreso = df['Tesoro Líquido'].sum() 
        total_atenciones = len(df)
        
        col_m1, col_m2 = st.columns(2)
        
        with col_m1:
            st.metric("💰 Tesoro Líquido Total", format_currency(total_ingreso))
        with col_m2:
            st.metric("👥 Atenciones Registradas", total_atenciones)
            
        st.markdown("---")
        
        st.subheader("Gráficos de Distribución del Tesoro")
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            df_lugar = df.groupby('Lugar')['Tesoro Líquido'].sum().reset_index()
            fig_lugar = px.pie(df_lugar, values='Tesoro Líquido', names='Lugar', title='Distribución por Castillo/Lugar', hole=.3)
            st.plotly_chart(fig_lugar, use_container_width=True)

        with col_g2:
            df_item = df.groupby('Ítem')['Tesoro Líquido'].sum().reset_index().sort_values(by='Tesoro Líquido', ascending=False)
            fig_item = px.bar(df_item.head(10), x='Ítem', y='Tesoro Líquido', title='Top 10 Pociones/Procedimientos (Ingreso Líquido)', labels={'Tesoro Líquido': 'Tesoro Líquido', 'Ítem': 'Ítem'})
            st.plotly_chart(fig_item, use_container_width=True)

        st.markdown("---")
        
        # 🟢 Gráfico Semanal (mantenido del paso anterior)
        st.subheader("Tesoro Líquido Acumulado por Semana")
        
        df_temp = df.copy()
        # Asegurarse de que 'Fecha' sea datetime para usar dt.to_period
        df_temp['Fecha_dt'] = pd.to_datetime(df_temp['Fecha']) 
        
        # 1. Agrupar por periodo semanal ('W').
        df_grouped_weekly = df_temp.groupby(df_temp['Fecha_dt'].dt.to_period('W')).agg(
            {'Tesoro Líquido': 'sum'}
        ).reset_index()
        
        # 2. Convertir el periodo semanal a una etiqueta legible (ej. "Semana 51 / 15-dic")
        df_grouped_weekly['Semana'] = df_grouped_weekly['Fecha_dt'].apply(
            lambda x: f"Semana {x.weekofyear} / {x.start_time.strftime('%d-%b')}"
        ) 
        
        # 3. Crear el gráfico de líneas
        fig = px.line(
            df_grouped_weekly, 
            x='Semana', # Usamos la nueva etiqueta categórica
            y='Tesoro Líquido', 
            title='Tesoro Líquido Acumulado por Semana', 
            labels={'Tesoro Líquido': 'Tesoro Líquido', 'Semana': 'Período Semanal (Fecha de Inicio)'}, 
            line_shape='spline'
        )
        # Añadir marcadores para ver los puntos de datos individuales
        fig.update_traces(mode='lines+markers') 
        
        # Opcional: Rotar etiquetas para mejor lectura
        fig.update_layout(xaxis_tickangle=-45)
        
        st.plotly_chart(fig, use_container_width=True)
        # 🟢 FIN DEL GRÁFICO
        
        
        # --- TABLA DE DATOS CRUDA Y EDICIÓN ---
        st.subheader("Historial Completo de Aventuras (Registros)")

        edited_id = st.session_state.edited_record_id
        
        # =================================================================
        # LÓGICA DE AISLAMIENTO: O SE DIBUJA LA TABLA, O EL FORMULARIO
        # =================================================================
        
        if edited_id is not None and edited_id in df['ID'].values: 
            # -------------------------------------------------------------
            # DIBUJAR FORMULARIO DE EDICIÓN 
            # -------------------------------------------------------------
            edit_row = df[df['ID'] == edited_id].iloc[0]
            
            # CARGAR ESTADO DE SESIÓN AL ABRIR EL FORMULARIO (Mantenido)
            if f'edit_paciente_{edited_id}' not in st.session_state:
                 st.session_state[f'edit_paciente_{edited_id}'] = edit_row['Paciente']
                 st.session_state[f'edit_valor_bruto_{edited_id}'] = edit_row['Valor Bruto']
                 st.session_state[f'edit_desc_adic_{edited_id}'] = edit_row['Desc. Ajuste']
                 st.session_state.original_desc_fijo_lugar = edit_row['Desc. Tributo']
                 st.session_state.original_desc_tarjeta = edit_row['Desc. Tarjeta']
                 # Usamos pd.to_datetime para asegurar que se puede convertir a date
                 fecha_dt = pd.to_datetime(edit_row['Fecha'])
                 st.session_state[f'edit_fecha_{edited_id}'] = fecha_dt.date() if pd.notna(fecha_dt) else date.today()
                 st.session_state[f'edit_lugar_{edited_id}'] = edit_row['Lugar']
                 st.session_state[f'edit_item_{edited_id}'] = edit_row['Ítem']
                 st.session_state[f'edit_metodo_{edited_id}'] = edit_row['Método Pago']
            
            
            st.markdown(f"## ✏️ Editando Registro ID: {edited_id} ({st.session_state[f'edit_paciente_{edited_id}']})")
            
            col_e1, col_e2, col_e3 = st.columns([1, 1, 1.2]) 
            
            with col_e1:
                st.subheader("Datos Clave")
                fecha_display = st.session_state[f'edit_fecha_{edited_id}']
                st.date_input("🗓️ Fecha de Atención", fecha_display, key=f"edit_fecha_{edited_id}")
                
                try:
                    lugar_idx = LUGARES.index(st.session_state[f'edit_lugar_{edited_id}'])
                except ValueError:
                    lugar_idx = 0
                st.selectbox("📍 Lugar", options=LUGARES, key=f"edit_lugar_{edited_id}", index=lugar_idx, on_change=update_edit_price, args=(edited_id,))

                items_edit_list = list(PRECIOS_BASE_CONFIG.get(st.session_state[f'edit_lugar_{edited_id}'], {}).keys())
                item_actual = st.session_state[f'edit_item_{edited_id}']
                try:
                     item_idx = items_edit_list.index(item_actual) if item_actual in items_edit_list else 0
                except (ValueError, KeyError):
                    item_idx = 0
                st.selectbox("📋 Ítem", options=items_edit_list, key=f"edit_item_{edited_id}", index=item_idx, on_change=update_edit_price, args=(edited_id,))
                
                st.text_input("👤 Paciente", key=f"edit_paciente_{edited_id}")
                
                try:
                    metodo_idx = METODOS_PAGO.index(st.session_state[f'edit_metodo_{edited_id}'])
                except ValueError:
                    metodo_idx = 0
                st.selectbox("💳 Método Pago", options=METODOS_PAGO, key=f"edit_metodo_{edited_id}", index=metodo_idx, on_change=update_edit_desc_tarjeta, args=(edited_id,))

            
            with col_e2:
                st.subheader("Ajustes Financieros")
                st.number_input("💰 Valor Bruto (Recompensa)", min_value=0, step=1000, key=f"edit_valor_bruto_{edited_id}")
                st.button("🔄 Actualizar a Precio Base Sugerido", key=f'btn_update_price_form_{edited_id}', on_click=update_edit_bruto_price, args=(edited_id,), use_container_width=True)

                st.markdown("---")

                st.number_input("✂️ Ajuste Extra (Desc. Adic.)", min_value=-500000, step=1000, key=f"edit_desc_adic_{edited_id}")
                
                st.markdown("---")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    st.button("🔄 Recalcular Tributo/Regla", key=f'btn_update_tributo_form_{edited_id}', on_click=update_edit_tributo, args=(edited_id,), use_container_width=True)
                with col_btn2:
                    st.button("🔄 Recalcular Tarjeta", key=f'btn_update_tarjeta_form_{edited_id}', on_click=update_edit_desc_tarjeta, args=(edited_id,), use_container_width=True)


            with col_e3:
                st.subheader("Estado Actual (No Editable)")
                # Forzamos los valores a int para el cálculo de la vista previa
                try:
                    current_desc_fijo = int(st.session_state.get('original_desc_fijo_lugar', edit_row['Desc. Tributo']))
                except:
                    current_desc_fijo = 0
                
                try:
                    current_desc_tarjeta = int(st.session_state.get('original_desc_tarjeta', edit_row['Desc. Tarjeta']))
                except:
                    current_desc_tarjeta = 0
                
                try:
                    current_valor_bruto = int(st.session_state[f'edit_valor_bruto_{edited_id}'])
                except:
                    current_valor_bruto = 0
                    
                try:
                    current_desc_adicional = int(st.session_state[f'edit_desc_adic_{edited_id}'])
                except:
                    current_desc_adicional = 0
                
                total_liquido_live = (
                    current_valor_bruto
                    - current_desc_fijo
                    - current_desc_tarjeta
                    - current_desc_adicional
                )
                
                st.metric("❌ Desc. Fijo/Tributo", format_currency(current_desc_fijo))
                st.metric("💳 Desc. Tarjeta", format_currency(current_desc_tarjeta))
                st.metric("✂️ Desc. Adicional", format_currency(current_desc_adicional))
                
                st.markdown("---")
                
                st.success(f"### 💎 Tesoro Líquido (Vista Previa): {format_currency(total_liquido_live)}")
                st.error(f"**Total Guardado Anterior:** {format_currency(edit_row['Tesoro Líquido'])}")


            # --- Botones de Control Final ---
            st.markdown("---")
            
            col_final1, col_final2 = st.columns([0.8, 0.2])
            
            with col_final1:
                if st.button(
                    "💾 Aplicar Cambios y Cerrar Edición", 
                    type="primary",
                    key=f'btn_save_edit_form_{edited_id}', 
                    use_container_width=True
                ):
                    new_total = save_edit_state_to_df()
                    st.success(f"Registro ID {edited_id} actualizado y guardado. Nuevo Total: {format_currency(new_total)}")
                    _cleanup_edit_state() 
                    st.rerun() 

            with col_final2:
                st.button("❌ Cerrar Edición", key=f'btn_close_edit_form_{edited_id}', on_click=_cleanup_edit_state, use_container_width=True)


        # =================================================================
        # SECCIÓN DE BÚSQUEDA POR ID Y TABLA
        # =================================================================
        else: 
            st.markdown("### 🗺️ Registros Detallados")
            
            # --- 1. DIBUJAR LA TABLA DE DATOS (VISUALIZACIÓN) ---
            df_display_no_actions = df_display.copy()

            # Definición de columnas 
            config_columns = {
                'ID': st.column_config.NumberColumn(width='small', help="Identificador único del registro", disabled=True),
                'Fecha': st.column_config.TextColumn(disabled=True),
                'Lugar': st.column_config.TextColumn(disabled=True),
                'Ítem': st.column_config.TextColumn(disabled=True),
                'Paciente': st.column_config.TextColumn(disabled=True),
                'Método Pago': st.column_config.TextColumn(disabled=True),
                'Valor Bruto': st.column_config.NumberColumn(format=format_currency(0)[0] + "%d", disabled=True),
                'Desc. Tributo': st.column_config.NumberColumn(format=format_currency(0)[0] + "%d", disabled=True),
                'Desc. Ajuste': st.column_config.NumberColumn(format=format_currency(0)[0] + "%d", disabled=True),
                'Tesoro Líquido': st.column_config.NumberColumn(format=format_currency(0)[0] + "%d", help="Total final recibido después de descuentos y ajustes", disabled=True),
            }
            
            st.data_editor(
                df_display_no_actions,
                column_config=config_columns,
                hide_index=True,
                use_container_width=True,
                num_rows='fixed', 
                key='ingresos_viewer'
            )

            st.markdown("---")

            # --- 2. SECCIÓN DE EDICIÓN POR ID ---
            st.subheader("🛠️ Mantenimiento de Registros (Solo Edición)")
            
            min_id = df['ID'].min() if not df.empty else 1
            max_id = df['ID'].max() if not df.empty else 10000

            col_edit_input, col_edit_button = st.columns([0.2, 0.8])
            
            # --- EDICIÓN ---
            with col_edit_input:
                id_to_edit = st.number_input(
                    "ID a editar:", 
                    min_value=min_id, 
                    max_value=max_id, 
                    step=1, 
                    value=int(min_id) if not df.empty and st.session_state.input_id_edit is None else st.session_state.input_id_edit, 
                    key='input_id_edit', 
                    label_visibility="visible"
                )
            
            is_valid_id_edit = id_to_edit is not None and id_to_edit in df['ID'].values
            
            with col_edit_button:
                st.markdown("<br>", unsafe_allow_html=True) # Espacio para alinear el botón
                if st.button(
                    "✏️ Iniciar Edición", 
                    key='btn_start_edit_single', 
                    type="primary",
                    use_container_width=True, 
                    disabled=not is_valid_id_edit
                ):
                    edit_record_callback(id_to_edit)
                    st.rerun()
            
            # 🚨 SECCIÓN DE ELIMINACIÓN ELIMINADA 🚨
            # 🚨 BLOQUE DE CONFIRMACIÓN DE ELIMINACIÓN ELIMINADO 🚨

            if id_to_edit is not None and not is_valid_id_edit and st.session_state.edited_record_id is None:
                 st.info(f"El ID {int(id_to_edit)} no existe para editar.")

            st.markdown("---") 

        
    else:
        st.warning("Aún no hay registros de atenciones para mostrar en el mapa del tesoro. ¡Registra una aventura primero!")

# --- Bloque de Configuración (Mantenido) ---
with tab_config:
    st.header("⚙️ Configuración Maestra")
    st.info("⚠️ Los cambios aquí modifican el cálculo para **TODAS** las nuevas entradas y se guardan inmediatamente.")

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
                "Precio Sugerido": st.column_config.NumberColumn(format=format_currency(0)[0] + "%d")
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
            time.sleep(0.1) 
            st.success("Configuración de Precios Guardada y Recargada.")
            st.rerun()

    # 2. DESCUENTOS FIJOS POR LUGAR (TRIBUTO) Y REGLAS
    with tab_descuentos:
        
        st.subheader("✂️ Tributo Fijo Base por Castillo/Lugar")

        descuentos_df = pd.DataFrame(list(DESCUENTOS_LUGAR.items()), columns=['Lugar', 'Desc. Fijo Base'])
        
        edited_descuentos_df = st.data_editor(
            descuentos_df,
            key="descuentos_editor",
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Desc. Fijo Base": st.column_config.NumberColumn(format=format_currency(0)[0] + "%d")
            }
        )
        
        if st.button("💾 Guardar Configuración de Tributo Base", type="primary", key='btn_save_desc_base'):
            new_descuentos_config = {}
            for index, row in edited_descuentos_df.iterrows():
                lugar = str(row['Lugar']).upper()
                descuento = sanitize_number_input(row['Desc. Fijo Base'])
                if lugar:
                    new_descuentos_config[lugar] = descuento
                    
            save_config(new_descuentos_config, DESCUENTOS_FILE)
            re_load_global_config()
            time.sleep(0.1) 
            st.success("Configuración de Tributo Base Guardada y Recargada.")
            st.rerun()
            
        st.markdown("---")
        
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
                    "Tributo Diario": st.column_config.NumberColumn(format=format_currency(0)[0] + "%d"),
                    "Día": st.column_config.SelectboxColumn(options=DIAS_SEMANA)
                }
            )

            if st.button("💾 Guardar Reglas Diarias", type="secondary", key='btn_save_reglas'):
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
                time.sleep(0.1) 
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
        
        if st.button("💾 Guardar Configuración de Comisiones", type="primary", key='btn_save_comisiones'):
            new_comisiones_config = {}
            for index, row in edited_comisiones_df.iterrows():
                metodo = str(row['Método de Pago']).upper()
                comision = float(row['Comisión %'])
                if metodo:
                    new_comisiones_config[metodo] = comision
                    
            save_config(new_comisiones_config, COMISIONES_FILE)
            re_load_global_config()
            time.sleep(0.1) 
            st.success("Configuración de Comisiones Guardada y Recargada.")
            st.rerun()
