import streamlit as st
import pandas as pd
from datetime import date
import json 
import time 
import plotly.express as px
import numpy as np 
import os 
from dateutil.parser import parse
from supabase import create_client, Client 

# ===============================================
# 1. CONFIGURACIÓN Y BASES DE DATOS (MAESTRAS)
# ===============================================

PRECIOS_FILE = 'precios_base.json'
DESCUENTOS_FILE = 'descuentos_lugar.json'
COMISIONES_FILE = 'comisiones_pago.json'
REGLAS_FILE = 'descuentos_reglas.json' 

def save_config(data, filename):
    """Guarda la configuración a un archivo JSON."""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4, sort_keys=True)
            f.flush() 
    except Exception as e:
        st.error(f"Error al guardar el archivo {filename}: {e}")

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
# 2. FUNCIONES DE PERSISTENCIA (SUPABASE CLIENT)
# ===============================================

@st.cache_resource
def init_connection() -> Client:
    """
    Inicializa y devuelve el cliente de Supabase usando los secretos de Streamlit.
    """
    try:
        # LECTURA DE CLAVES A NIVEL RAÍZ (SOLUCIÓN A "no attribute 'supabase'")
        # *** RECUERDA REEMPLAZAR CON TUS CLAVES REALES EN secrets.toml ***
        # url: str = st.secrets["SUPABASE_URL"] 
        # key: str = st.secrets["SUPABASE_KEY"]
        
        # Simulando la lectura de secretos (AJUSTA ESTO EN TU ENTORNO)
        url: str = 'TU_URL_DE_SUPABASE' # Reemplazar con st.secrets["SUPABASE_URL"]
        key: str = 'TU_CLAVE_API' # Reemplazar con st.secrets["SUPABASE_KEY"]

        if url == 'TU_URL_DE_SUPABASE' or key == 'TU_CLAVE_API':
            st.error("🚨 Error: Las claves de Supabase no están configuradas correctamente. Usando datos dummy.")
            return None # Retornar None si las claves son las de marcador de posición
            
        if not url or not key:
             st.error("🚨 Error: SUPABASE_URL o SUPABASE_KEY no están configurados en los secretos.")
             return None

        # Crea el cliente de Supabase
        return create_client(url, key)
        
    except KeyError as e:
        st.error(f"🚨 Error: No se encontró la clave necesaria en st.secrets: {e}. Asegúrate de que SUPABASE_URL y SUPABASE_KEY estén en el nivel raíz de tu secrets.toml.")
        return None
    except Exception as e:
        st.error(f"🚨 Error al inicializar la conexión con Supabase: {e}")
        return None

# Inicializa el cliente global
supabase = init_connection()

# =======================================================
# Función dummy para DB si la conexión falla (ROBUSTEZ)
# =======================================================
def load_data_dummy():
    """Crea un DataFrame dummy si la conexión a Supabase falla."""
    data = {
        'id': [1, 2, 3],
        'Fecha': [date(2025, 1, 1), date(2025, 1, 5), date(2025, 1, 10)],
        'Lugar': ['ALERCE', 'AMAR AUSTRAL', 'ALERCE'],
        'Ítem': ['Item1', 'ADIR+ADOS2', 'Item2'],
        'Paciente': ['Frodo', 'Sam', 'Gandalf'],
        'Método Pago': ['EFECTIVO', 'TARJETA', 'TRANSFERENCIA'],
        'Valor Bruto': [30000, 30000, 40000],
        'Desc. Fijo Lugar': [5000, 7000, 5000],
        'Desc. Tarjeta': [0, 900, 0],
        'Desc. Adicional': [0, 0, 5000],
        'Total Recibido': [25000, 22100, 35000]
    }
    return pd.DataFrame(data)

@st.cache_data(show_spinner="Cargando Tesoro desde la Nube (Supabase Client)...", ttl=600)
def load_data_from_db():
    """Carga los datos desde Supabase a un DataFrame."""
    if supabase is None:
        return load_data_dummy() # Usar dummy si no hay conexión
        
    try:
        # Consulta select usando el cliente de Supabase
        response = supabase.table("atenciones").select("*").order("id", desc=False).execute()
        
        # Verificar la respuesta y extraer los datos
        if not response.data:
            return pd.DataFrame()
            
        df = pd.DataFrame(response.data)
        
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
        st.error(f"Error al cargar datos desde Supabase: {e}. Se cargará la data dummy.")
        return load_data_dummy()


def insert_new_record(record_dict):
    """Inserta un nuevo registro en la tabla de atenciones en Supabase."""
    if supabase is None or supabase.url == 'TU_URL_DE_SUPABASE':
        st.warning("Usando modo dummy: No se pudo conectar a la DB. No se guardó el registro.")
        return True # Simula éxito en modo dummy
        
    try:
        # Supabase insert
        response = supabase.table("atenciones").insert(record_dict).execute()
        
        # Supabase client retorna un objeto; verificamos que haya datos insertados
        if response.data and len(response.data) > 0:
            return True
        else:
            # Captura de error de API de Supabase más detallada
            error_message = response.json() if hasattr(response, 'json') else str(response)
            st.error(f"Error al insertar en la BD (Supabase API): {error_message}") 
            return False

    except Exception as e:
        st.error(f"Error al insertar en la BD (Supabase Client): {e}")
        return False


def update_existing_record(record_dict):
    """Actualiza un registro existente usando su 'id' como clave en Supabase."""
    if supabase is None or supabase.url == 'TU_URL_DE_SUPABASE':
        st.warning(f"Usando modo dummy: No se pudo conectar a la DB. No se actualizó el ID {record_dict.get('id')}.")
        return True # Simula éxito en modo dummy
        
    record_id = record_dict.pop('id') # El payload de update no debe contener 'id'
    
    try:
        # Supabase update: filtramos por ID, luego actualizamos los datos
        response = supabase.table("atenciones").update(record_dict).eq('id', record_id).execute()
        
        # Verificamos si la actualización fue exitosa
        if response.data and len(response.data) > 0:
            return True
        else:
            # Captura de error de API de Supabase más detallada
            error_message = response.json() if hasattr(response, 'json') else str(response)
            st.error(f"Error al actualizar la BD (Supabase API): {error_message}") 
            return False

    except Exception as e:
        st.error(f"Error al actualizar la BD (Supabase Client): {e}")
        return False

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
        
        # Keys del input de edición
        f'input_id_edit_{edited_id}', 'input_id_edit',
    ]
    
    for key in keys_to_delete:
        if key in st.session_state: del st.session_state[key] 
        
    st.session_state.edited_record_id = None 
    st.session_state.input_id_edit = None 
    
    
def save_edit_state_to_df():
    """
    Guarda el estado actual de los inputs de edición DIRECTAMENTE en la base de datos Supabase.
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
        desc_adicional_final = int(st.session_state.get(f'edit_desc_adic_{record_id}', 0))
    except:
        desc_adicional_final = 0
        
    # Obtener los descuentos actualizados (o los originales si no se recalcularon)
    # ¡Importante!: La lógica de recalculo de Tributo y Tarjeta actualiza estas claves
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
        
    st.session_state.edited_record_id = edited_id 
    
    st.rerun() 

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

    st.session_state.edited_record_id = edited_id 
    
    st.rerun() 

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
                 try:
                     current_date_obj = parse(st.session_state[f'edit_fecha_{edited_id}']).date()
                 except Exception:
                     current_date_obj = date.today()
                     
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
        
    st.session_state.edited_record_id = edited_id 

    st.rerun()


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
    /* ---------------------- Responsive Fixes ---------------------- */
    /* Asegura que los botones ocupen el ancho completo en contenedores pequeños */
    div[data-testid="stColumn"] > div > .stButton > button {
        width: 100%;
    }
    /* Estrecha el radio button para que quepa mejor en columnas pequeñas */
    div.stRadio > label {
        margin-right: 0px !important; 
    }
    /* ---------------------- Theme Styling (Mantenido) ---------------------- */
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
    layout="wide" # <--- CLAVE RESPONSIVE
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
    
# Para guardar los descuentos originales en edición
if 'original_desc_fijo_lugar' not in st.session_state:
    st.session_state.original_desc_fijo_lugar = 0
if 'original_desc_tarjeta' not in st.session_state:
    st.session_state.original_desc_tarjeta = 0
    

st.title("🏰 Tesoro de Ingresos Fonoaudiológicos 💰")
st.markdown("✨ ¡Transforma cada atención en un diamante! ✨")


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

# =========================================================================
# 📝 TAB: REGISTRAR AVENTURA (Formulario Responsive)
# =========================================================================
with tab_registro:
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


    # -------------------------------------------------------------------------
    # Diseño Responsive: Columna de Input (1.5) y Columna de Resultados (1)
    # -------------------------------------------------------------------------
    col_input, col_results = st.columns([1.5, 1]) 
    
    
    # --- Columna 1: Entrada de Datos ---
    with col_input:
        st.markdown("### 📝 Datos de la Aventura")
        
        # Fila 1 (Lugar + Ítem) - 2 columnas que se apilan en móvil
        c1_lugar, c1_item = st.columns(2) 
        
        with c1_lugar:
            try:
                lugar_index = LUGARES.index(st.session_state.form_lugar) if st.session_state.form_lugar in LUGARES else 0
            except ValueError:
                lugar_index = 0

            st.selectbox("📍 Castillo/Lugar de Atención", 
                         options=LUGARES, 
                         key="form_lugar",
                         index=lugar_index,
                         on_change=update_price_from_item_or_lugar) 
        
        with c1_item:
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

        
        # Fila 2 (Valor Bruto + Desc. Adicional) - 2 columnas que se apilan en móvil
        c2_bruto, c2_adic = st.columns(2) 
        
        with c2_bruto:
            st.number_input(
                "💰 **Valor Bruto (Recompensa)**", 
                min_value=0, 
                step=1000,
                key="form_valor_bruto", 
                on_change=force_recalculate 
            )

        with c2_adic:
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

        # Campos apilados verticalmente (Mejor en móvil)
        with st.form("registro_atencion_form"): 
            
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
            
            st.text_input("👤 Héroe/Heroína (Paciente/Asociado)", st.session_state.form_paciente, key="form_paciente")
            
            st.markdown("---")
            
            st.form_submit_button("✅ ¡Guardar Aventura y Recolectar Tesoro!", type="primary", on_click=submit_and_reset, use_container_width=True) # Botón ancho
            
    # --- Columna 2: Resultados de Cálculo (Métricas Responsive) ---
    with col_results:
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
            
            st.metric(label="Valor Bruto (Recompensa)", value=format_currency(resultados['valor_bruto']), delta="100%", delta_color="off")
            
            st.metric(label="Tributo Fijo Lugar (Desc. Fijo)", value=format_currency(-resultados['desc_fijo_lugar']), delta="- Tributo", delta_color="inverse")
            
            st.metric(label="Comisión Tarjeta (Desc. Tarjeta)", value=format_currency(-resultados['desc_tarjeta']), delta="- Comisión", delta_color="inverse")

            st.metric(label="Polvo Mágico Extra (Desc. Adic.)", value=format_currency(-desc_adicional_calc), delta=f"{'+ Cargo' if desc_adicional_calc < 0 else '- Descuento'}", delta_color="inverse")

            st.metric(label="**💰 Tesoro Líquido (Total Neto)**", 
                      value=format_currency(resultados['total_recibido']), 
                      delta="¡Ganancia Final!", delta_color="normal")
            
            st.info("El Tesoro Líquido es lo que recibes tras todos los descuentos.")


# =========================================================================
# 📊 TAB: MAPA DEL TESORO (Dashboard Responsive)
# =========================================================================
with tab_dashboard:
    st.header("📊 Mapa del Tesoro: Resumen de Ingresos")
    
    df_actual = st.session_state.atenciones_df.copy()

    if df_actual.empty:
        st.info("Aún no hay aventuras registradas. ¡Empieza a registrar en la pestaña anterior!")
    else:
        # --- 2.1. FILTROS EN COLUMNAS RESPONSIVE ---
        col_filtro_fecha, col_filtro_lugar = st.columns(2)

        with col_filtro_fecha:
            fecha_min = df_actual['Fecha'].min() if not df_actual['Fecha'].empty else date.today()
            fecha_max = df_actual['Fecha'].max() if not df_actual['Fecha'].empty else date.today()
            # Asegurar que los valores por defecto existan
            if fecha_min > fecha_max:
                fecha_max = fecha_min
            
            fecha_inicio, fecha_fin = st.date_input(
                "🗓️ Rango de Fechas", 
                value=(fecha_min, fecha_max), 
                min_value=fecha_min, 
                max_value=fecha_max
            )
            df_filtrado = df_actual[
                (df_actual['Fecha'] >= fecha_inicio) & 
                (df_actual['Fecha'] <= fecha_fin)
            ]

        with col_filtro_lugar:
            opciones_lugar = ['Todos'] + LUGARES
            lugar_seleccionado = st.selectbox("📍 Filtrar por Lugar", opciones_lugar)
            
            if lugar_seleccionado != 'Todos':
                df_filtrado = df_filtrado[df_filtrado['Lugar'] == lugar_seleccionado]

        st.markdown("---")

        # --- 2.2. INDICADORES CLAVE (KPIs) - 3 columnas que se apilan ---
        kpi1, kpi2, kpi3 = st.columns(3)
        
        total_ingreso = df_filtrado['Total Recibido'].sum()
        total_atenciones = len(df_filtrado)
        promedio_atencion = total_ingreso / total_atenciones if total_atenciones else 0

        with kpi1:
            st.metric("Tesoro Neto Filtrado", format_currency(total_ingreso))
        with kpi2:
            st.metric("Número de Aventuras", total_atenciones)
        with kpi3:
            st.metric("Promedio por Aventura", format_currency(promedio_atencion))
            
        st.markdown("---")

        # --- 2.3. GRÁFICOS Y TABLA DE DETALLE ---
        st.subheader("Gráficos de Distribución")
        
        # Dos columnas para los gráficos. En PC lado a lado, en Móvil apilados.
        col_chart_1, col_chart_2 = st.columns(2)
        
        with col_chart_1:
            st.caption("Distribución de Tesoro Neto por Lugar")
            df_lugar = df_filtrado.groupby('Lugar')['Total Recibido'].sum().reset_index()
            fig_pie = px.pie(df_lugar, values='Total Recibido', names='Lugar', hole=.3)
            st.plotly_chart(fig_pie, use_container_width=True) # CLAVE RESPONSIVE

        with col_chart_2:
            st.caption("Evolución Diaria del Tesoro Neto")
            df_linea = df_filtrado.groupby('Fecha')['Total Recibido'].sum().reset_index()
            fig_line = px.line(df_linea, x='Fecha', y='Total Recibido', 
                               labels={'Total Recibido': 'Tesoro Neto'}, 
                               title="Tendencia de Ingresos")
            st.plotly_chart(fig_line, use_container_width=True) # CLAVE RESPONSIVE

        st.markdown("---")
        
        st.subheader("Detalle del Tesoro Filtrado")
        
        # Input de edición de ID
        st.number_input("🔍 Ingresa el ID para Editar/Ver el registro", 
                        min_value=0, 
                        value=st.session_state.get('input_id_edit', 0), 
                        step=1, 
                        key='input_id_edit', 
                        help="Busca el ID en la tabla de abajo para abrir el formulario de edición.")
        
        
        # --- LÓGICA Y FORMULARIO DE EDICIÓN RESPONSIVE ---
        if st.session_state.input_id_edit and st.session_state.input_id_edit != 0:
            if st.session_state.edited_record_id is None:
                # Intenta encontrar y preparar la edición
                edited_id_int = int(st.session_state.input_id_edit)
                if edited_id_int in df_actual['id'].values:
                    st.session_state.edited_record_id = edited_id_int
                    st.rerun()
                else:
                    st.warning(f"ID {edited_id_int} no encontrado. Ingresa un ID válido de la tabla.")
            
        if st.session_state.edited_record_id is not None:
            edited_id = st.session_state.edited_record_id
            
            try:
                current_record_series = df_actual[
                    df_actual['id'] == edited_id
                ].iloc[0]
                
                # Seteamos el estado para el formulario de edición (si no existe)
                if f'edit_valor_bruto_{edited_id}' not in st.session_state:
                    st.session_state[f'edit_valor_bruto_{edited_id}'] = current_record_series['Valor Bruto']
                    st.session_state.original_desc_fijo_lugar = current_record_series['Desc. Fijo Lugar']
                    st.session_state.original_desc_tarjeta = current_record_series['Desc. Tarjeta']
                    
                
                # --- Expander de Edición Responsive ---
                with st.expander(f"✍️ Editando Aventura ID: {edited_id}", expanded=True):
                    
                    # 1. Bloque de Cabecera (3 columnas en PC, apiladas en Móvil)
                    col_e_1, col_e_2, col_e_3 = st.columns(3)
                    
                    with col_e_1:
                        st.date_input(
                            "🗓️ Fecha de Atención", 
                            value=current_record_series['Fecha'], 
                            key=f"edit_fecha_{edited_id}",
                            on_change=update_edit_tributo, # Cambiar fecha puede cambiar tributo
                            args=(edited_id,)
                        )
                    
                    with col_e_2:
                        current_lugar = current_record_series['Lugar']
                        try: lugar_idx = LUGARES.index(current_lugar) 
                        except: lugar_idx = 0
                        st.selectbox(
                            "📍 Lugar", 
                            options=LUGARES, 
                            index=lugar_idx,
                            key=f"edit_lugar_{edited_id}",
                            on_change=update_edit_price, 
                            args=(edited_id,)
                        )
                    
                    with col_e_3:
                        st.text_input(
                            "👤 Paciente", 
                            value=current_record_series['Paciente'],
                            key=f"edit_paciente_{edited_id}"
                        )

                    st.markdown("---")

                    # 2. Bloque de Valores y Descuentos (2 columnas en PC, apiladas en Móvil)
                    col_e_4, col_e_5 = st.columns(2)
                    
                    with col_e_4:
                        st.subheader("Recompensa Bruta")
                        
                        # Ítem
                        current_item = current_record_series['Ítem']
                        current_lugar_key = st.session_state.get(f"edit_lugar_{edited_id}", current_lugar)
                        items_disponibles = list(PRECIOS_BASE_CONFIG.get(current_lugar_key, {}).keys())
                        try: item_idx = items_disponibles.index(current_item)
                        except: item_idx = 0
                            
                        st.selectbox(
                            "📋 Ítem/Procedimiento", 
                            options=items_disponibles, 
                            index=item_idx,
                            key=f"edit_item_{edited_id}",
                            on_change=update_edit_price, 
                            args=(edited_id,)
                        )
                        
                        # Valor Bruto
                        st.number_input(
                            "💰 Valor Bruto (Editable)", 
                            value=st.session_state.get(f'edit_valor_bruto_{edited_id}', current_record_series['Valor Bruto']),
                            key=f"edit_valor_bruto_{edited_id}",
                            min_value=0
                        )
                        
                        st.button(
                            "🔄 Recalcular Precio Sugerido", 
                            key=f'btn_update_price_form_{edited_id}', 
                            on_click=update_edit_bruto_price, 
                            args=(edited_id,),
                            use_container_width=True
                        )

                    with col_e_5:
                        st.subheader("Reducciones (Tributos/Comisiones)")

                        # Método de Pago
                        current_metodo = current_record_series['Método Pago']
                        try: metodo_idx = METODOS_PAGO.index(current_metodo)
                        except: metodo_idx = 0
                        st.selectbox(
                            "💳 Método de Pago",
                            options=METODOS_PAGO,
                            index=metodo_idx,
                            key=f"edit_metodo_{edited_id}",
                            on_change=update_edit_desc_tarjeta, 
                            args=(edited_id,)
                        )
                        
                        # Descuento Fijo (Tributo) y Tarjeta en 2 sub-columnas responsive
                        c5_tributo, c5_tarjeta = st.columns(2) 

                        with c5_tributo:
                            st.markdown(f"**Tributo Fijo:** {format_currency(st.session_state.original_desc_fijo_lugar)}")
                            st.button(
                                "🏛️ Recalcular Tributo", 
                                key=f'btn_update_tributo_form_{edited_id}', 
                                on_click=update_edit_tributo, 
                                args=(edited_id,),
                                use_container_width=True
                            )
                        
                        with c5_tarjeta:
                            st.markdown(f"**Comisión Tarjeta:** {format_currency(st.session_state.original_desc_tarjeta)}")
                            st.button(
                                "💳 Recalcular Comisión", 
                                key=f'btn_update_tarjeta_form_{edited_id}', 
                                on_click=update_edit_desc_tarjeta, 
                                args=(edited_id,),
                                use_container_width=True
                            )

                        st.markdown("---")
                        # Descuento Adicional (Manual) - Solo un campo
                        st.number_input(
                            "✂️ Descuento Adicional (Ajuste)", 
                            value=st.session_state.get(f'edit_desc_adic_{edited_id}', current_record_series['Desc. Adicional']),
                            key=f"edit_desc_adic_{edited_id}",
                            step=1000
                        )


                    st.markdown("---")
                    
                    # 3. Bloque Final y Botones de Guardar/Cerrar (2 columnas en PC, apiladas en Móvil)
                    col_final_1, col_final_2 = st.columns(2)
                    
                    total_liquido_calc = (
                        st.session_state[f'edit_valor_bruto_{edited_id}']
                        - st.session_state.original_desc_fijo_lugar
                        - st.session_state.original_desc_tarjeta
                        - st.session_state[f'edit_desc_adic_{edited_id}']
                    )
                    
                    with col_final_1:
                        st.metric(
                            "✨ Tesoro Neto Actual", 
                            format_currency(total_liquido_calc), 
                            delta="¡Guarda para aplicar el cambio!"
                        )

                    with col_final_2:
                        if st.button("💾 Guardar Cambios y Recargar", key=f'btn_save_edit_form_{edited_id}', type="primary", use_container_width=True):
                            final_total = save_edit_state_to_df()
                            if final_total > 0:
                                st.session_state.deletion_pending_cleanup = True 
                                st.toast(f"✅ ¡Cambios guardados! Nuevo Tesoro: {format_currency(final_total)}", icon="💾")
                                st.rerun()

                        if st.button("❌ Cerrar Sin Guardar", key=f'btn_close_edit_form_{edited_id}', use_container_width=True):
                            st.session_state.deletion_pending_cleanup = True 
                            st.toast("Edición cancelada.", icon="❌")
                            st.rerun()
                            
            except IndexError:
                st.error(f"No se encontró un registro con ID: {edited_id}")
                st.session_state.deletion_pending_cleanup = True
                st.rerun()
        # Fin de la lógica de edición
        
        st.subheader("Tabla Completa de Aventuras")
        # st.dataframe es la mejor opción responsive para mostrar tablas largas
        st.dataframe(df_filtrado, use_container_width=True)


# =========================================================================
# ⚙️ TAB: CONFIGURACIÓN MAESTRA (Expander y Editor Responsive)
# =========================================================================

# NOTA: La función display_config_editor fue definida anteriormente para manejar el diseño responsive
# usando st.expander y st.data_editor con use_container_width=True.

def display_config_editor(title, config_data, filename, help_text):
    """Función unificada para mostrar y editar la configuración."""
    
    with st.expander(f"🔮 {title}", expanded=False):
        st.info(help_text)
        
        # --- Lógica de Manejo de DataFrames para Edición ---
        if title == "Reglas Especiales de Descuento (Día/Lugar)":
            reglas_df_list = []
            for lugar, reglas in config_data.items():
                for dia, monto in reglas.items():
                    reglas_df_list.append({
                        'Lugar': lugar,
                        'Día': dia,
                        'Monto': monto
                    })
            reglas_df = pd.DataFrame(reglas_df_list)
            
            if reglas_df.empty:
                 reglas_df = pd.DataFrame({'Lugar': ['NUEVO_LUGAR'], 'Día': ['LUNES'], 'Monto': [0]})

            edited_df = st.data_editor(
                reglas_df,
                num_rows="dynamic",
                key=f"editor_{filename}",
                use_container_width=True
            )
            
            if st.button(f"Guardar {title}", key=f"save_btn_{filename}", type="primary", use_container_width=True):
                new_config = {}
                for _, row in edited_df.iterrows():
                    lugar = str(row['Lugar']).upper()
                    dia = str(row['Día']).upper()
                    monto = sanitize_number_input(row['Monto'])
                    
                    if lugar not in new_config:
                        new_config[lugar] = {}
                    new_config[lugar][dia] = monto

                save_config(new_config, filename)
                re_load_global_config() 
                st.toast(f"{title} guardado y recargado con éxito.", icon="✅")
                st.rerun()
                
        elif title == "Precios Base de Items (Lugar)":
            data_list = []
            for lugar, items in config_data.items():
                for item, precio in items.items():
                    data_list.append({'Lugar': lugar, 'Ítem': item, 'Precio': precio})
            
            precios_df = pd.DataFrame(data_list)
            
            if precios_df.empty:
                precios_df = pd.DataFrame({'Lugar': ['NUEVO_LUGAR'], 'Ítem': ['NUEVO_ITEM'], 'Precio': [0]})

            edited_df = st.data_editor(
                precios_df,
                num_rows="dynamic",
                key=f"editor_{filename}",
                column_config={"Precio": st.column_config.NumberColumn(format="$,.0f")},
                use_container_width=True
            )

            if st.button(f"Guardar {title}", key=f"save_btn_{filename}", type="primary", use_container_width=True):
                new_config = {}
                for _, row in edited_df.iterrows():
                    lugar = str(row['Lugar']).upper()
                    item = str(row['Ítem'])
                    precio = sanitize_number_input(row['Precio'])
                    
                    if lugar not in new_config:
                        new_config[lugar] = {}
                    new_config[lugar][item] = precio
                
                save_config(new_config, filename)
                re_load_global_config()
                st.toast(f"{title} guardado y recargado con éxito.", icon="✅")
                st.rerun()
                
        else:
            df = pd.DataFrame(list(config_data.items()), columns=['Clave', 'Valor'])
            
            if title == "Comisiones por Método de Pago":
                col_type = st.column_config.NumberColumn(format="0.00%")
            else:
                col_type = st.column_config.NumberColumn(format="$,.0f")
            
            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                key=f"editor_{filename}",
                column_config={"Valor": col_type},
                use_container_width=True
            )

            if st.button(f"Guardar {title}", key=f"save_btn_{filename}", type="primary", use_container_width=True):
                new_config = {str(row['Clave']).upper(): row['Valor'] for _, row in edited_df.iterrows()}
                
                save_config(new_config, filename)
                re_load_global_config()
                st.toast(f"{title} guardado y recargado con éxito.", icon="✅")
                st.rerun()


with tab_config:
    st.header("⚙️ Configuración Maestra del Tesoro")
    st.warning("⚠️ **¡Advertencia de Hechicería!** Los cambios aquí afectan el cálculo de *todos* los nuevos registros.")

    display_config_editor(
        "Precios Base de Items (Lugar)",
        PRECIOS_BASE_CONFIG,
        PRECIOS_FILE,
        "Define el precio de referencia para cada Ítem dentro de cada Lugar."
    )

    display_config_editor(
        "Tributo Fijo por Lugar (Descuento Base)",
        DESCUENTOS_LUGAR,
        DESCUENTOS_FILE,
        "Monto fijo que se descuenta automáticamente por el uso de cada Lugar (Ej: Arriendo, Administración)."
    )
    
    display_config_editor(
        "Reglas Especiales de Descuento (Día/Lugar)",
        DESCUENTOS_REGLAS,
        REGLAS_FILE,
        "Permite anular el Tributo Fijo por un monto especial si se cumple la condición de Día y Lugar (Ej: Martes en Amar Austral)."
    )

    display_config_editor(
        "Comisiones por Método de Pago",
        COMISIONES_PAGO,
        COMISIONES_FILE,
        "Porcentaje de comisión por método de pago (Ej: Tarjeta de Crédito 3%). Use decimales (0.03 = 3%)."
    )

    st.markdown("---")
    st.info("Para que todos los cambios se apliquen por completo, recomendamos usar el botón 'Limpiar Cenicienta' en la barra lateral después de guardar.")
