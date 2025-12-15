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
        url: str = st.secrets["SUPABASE_URL"] 
        key: str = st.secrets["SUPABASE_KEY"]
        
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


@st.cache_data(show_spinner="Cargando Tesoro desde la Nube (Supabase Client)...", ttl=600)
def load_data_from_db():
    """Carga los datos desde Supabase a un DataFrame."""
    if supabase is None:
        return pd.DataFrame()
        
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
        st.error(f"Error al cargar datos desde Supabase: {e}")
        return pd.DataFrame()


def insert_new_record(record_dict):
    """Inserta un nuevo registro en la tabla de atenciones en Supabase."""
    if supabase is None:
        return False
        
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
    if supabase is None:
        return False
        
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
    desc_tarjeta = int((valor_bruto - desc_adicional_manual) * comision_pct)
    
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
    # Usamos .get() para evitar KeyError si se llama antes de que se creen las claves dinámicas
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
        # NOTA: La clave f'edit_desc_adicional_manual_{edited_id}' NO EXISTE y la eliminamos del cleanup
    ]
    
    # También añadimos la clave fallida al cleanup por si se creó accidentalmente
    keys_to_delete.append(f'edit_desc_adicional_manual_{edited_id}') 
    
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
    
    # LECTURA SEGURA DE TIPOS NUMÉRICOS
    valor_bruto_final = int(st.session_state.get(f'edit_valor_bruto_{record_id}', 0))
    desc_adicional_final = int(st.session_state.get(f'edit_desc_adic_{record_id}', 0)) # Usando la clave correcta 'edit_desc_adic'
    
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
    # Usamos .get() para robustez
    lugar_edit = st.session_state.get(f'edit_lugar_{edited_id}', '').upper()
    item_edit = st.session_state.get(f'edit_item_{edited_id}', '')
    
    precio_actual = st.session_state.get(f'edit_valor_bruto_{edited_id}', 0)
    nuevo_precio_base = PRECIOS_BASE_CONFIG.get(lugar_edit, {}).get(item_edit, precio_actual)
    
    # 1. Actualizar el widget de la sesión
    st.session_state[f'edit_valor_bruto_{edited_id}'] = int(nuevo_precio_base)
    
    # 2. Guardar en la DB con el nuevo valor
    new_total = save_edit_state_to_df() 
    
    if new_total > 0:
        st.toast(f"Valor Bruto actualizado a {format_currency(st.session_state[f'edit_valor_bruto_{edited_id}'])}$. Nuevo Tesoro Líquido: {format_currency(new_total)}", icon="🔄")
        
    # 🚨 CORRECCIÓN DE ROBUSTEZ: Asegurar el ID antes de la recarga
    st.session_state.edited_record_id = edited_id 
    
    st.rerun() 

def update_edit_desc_tarjeta(edited_id):
    """Callback: Recalcula y actualiza el Desc. Tarjeta (y guarda)."""
    # LECTURA ROBUSTA Y CORREGIDA DEL KEY
    metodo_pago_actual = st.session_state.get(f'edit_metodo_{edited_id}', '').upper()
    valor_bruto_actual = int(st.session_state.get(f'edit_valor_bruto_{edited_id}', 0))
    
    # 💥 CORRECCIÓN CRÍTICA: Usamos 'edit_desc_adic' que es la clave correcta en tu código.
    desc_adicional_manual_actual = int(st.session_state.get(f'edit_desc_adic_{edited_id}', 0))

    comision_pct_actual = COMISIONES_PAGO.get(metodo_pago_actual, 0.00)
    nuevo_desc_tarjeta = int((valor_bruto_actual - desc_adicional_manual_actual) * comision_pct_actual)
    
    # 1. Actualizar el valor en el estado de sesión (Desc. Tarjeta Original)
    st.session_state.original_desc_tarjeta = nuevo_desc_tarjeta
    
    # 2. Guardar en la DB con el nuevo valor de descuento de tarjeta
    new_total = save_edit_state_to_df() 
    
    if new_total > 0:
        st.toast(f"Desc. Tarjeta recalculado a {format_currency(nuevo_desc_tarjeta)}$. Nuevo Tesoro Líquido: {format_currency(new_total)}", icon="💳")

    # 🚨 CORRECCIÓN DE ROBUSTEZ: Asegurar el ID antes de la recarga
    st.session_state.edited_record_id = edited_id 
    
    st.rerun() 

def update_edit_tributo(edited_id):
    """Callback: Recalcula y actualiza el Tributo (Desc. Fijo Lugar) basado en Lugar y Fecha (y guarda)."""
    # Usamos .get() para robustez
    current_lugar_upper = st.session_state.get(f'edit_lugar_{edited_id}', '').upper()
    current_valor_bruto = int(st.session_state.get(f'edit_valor_bruto_{edited_id}', 0))
    desc_fijo_calc = DESCUENTOS_LUGAR.get(current_lugar_upper, 0)
    
    # --- LÓGICA DE CÁLCULO DE TRIBUTO EN EDICIÓN ---
    if current_lugar_upper == 'CPM':
        desc_fijo_calc = int(current_valor_bruto * 0.487)
    else:
        try:
            # LECTURA ROBUSTA DE FECHA
            current_date_val = st.session_state.get(f'edit_fecha_{edited_id}')
            
            if isinstance(current_date_val, date):
                current_date_obj = current_date_val
            elif current_date_val:
                 try:
                     current_date_obj = parse(current_date_val).date()
                 except Exception:
                     current_date_obj = date.today()
            else:
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
        
    # 🚨 CORRECCIÓN DE ROBUSTEZ: ESTE ES EL PASO CLAVE QUE ASEGURA EL ESTADO
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
                
                # --- Visualización de Resultados Calculados ---
                col_calc_1, col_calc_2 = st.columns(2)
                
                with col_calc_1:
                    st.metric("Desc. Fijo (Tributo)", format_currency(resultados['desc_fijo_lugar']), help="Descuento fijo basado en el lugar y día (si aplica).")
                    st.metric("Desc. Tarjeta (Comisión)", format_currency(resultados['desc_tarjeta']), help=f"Comisión del {COMISIONES_PAGO.get(st.session_state.form_metodo_pago.upper(), 0.00)*100:.0f}% sobre el Valor Bruto ajustado.")
                
                with col_calc_2:
                    st.metric("Desc. Adicional Manual", format_currency(desc_adicional_calc), help="Ajuste manual (Polvo Mágico Extra).")
                    st.metric("✨ **TESORO LÍQUIDO** ✨", format_currency(resultados['total_recibido']), delta=format_currency(resultados['total_recibido'] - resultados['valor_bruto']), delta_color="inverse")
                    
                st.markdown(f"Valor Bruto: **{format_currency(valor_bruto_calc)}**")
                st.markdown(f"Total Descuentos: **{format_currency(resultados['desc_fijo_lugar'] + resultados['desc_tarjeta'] + desc_adicional_calc)}**")
                
                st.markdown("---")

        st.form_submit_button("✅ Guardar Aventura y Recibir Tesoro", on_click=submit_and_reset, type="primary")

    st.markdown("---")
    
    # =========================================================================
    # VISUALIZACIÓN DE TABLA EDITABLE (ÚLTIMOS REGISTROS)
    # =========================================================================
    st.subheader("📜 Bitácora de las Últimas Aventuras")
    
    df_actual = st.session_state.atenciones_df
    
    if df_actual.empty:
        st.info("Aún no hay aventuras registradas. ¡Empieza la magia arriba!")
    else:
        df_display = df_actual.copy().tail(10) # Mostrar los últimos 10
        
        # Ocultamos ID para la visualización pública, pero lo usamos en el backend
        df_display = df_display[['Fecha', 'Paciente', 'Lugar', 'Ítem', 'Valor Bruto', 'Total Recibido']]

        # Conversión para display
        df_display['Valor Bruto'] = df_display['Valor Bruto'].apply(format_currency)
        df_display['Total Recibido'] = df_display['Total Recibido'].apply(format_currency)

        st.dataframe(df_display, 
                     use_container_width=True, 
                     hide_index=True)
                     
    st.markdown("---")
    
    # =========================================================================
    # SECCIÓN DE EDICIÓN / RECARGA
    # =========================================================================

    st.subheader("🔧 Modificar Registro por ID (Rastrear Aventura)")
    
    col_edit_input, col_edit_btn = st.columns([1, 1])

    with col_edit_input:
        st.number_input(
            "Ingresa el ID del registro a editar (visible en el 'Mapa del Tesoro')",
            min_value=1,
            step=1,
            value=st.session_state.get('input_id_edit', 1),
            key="input_id_edit",
        )
        
    with col_edit_btn:
        st.markdown("<br>", unsafe_allow_html=True) # Espacio para alinear
        if st.button("Buscar Registro 🔎", type="secondary"):
            st.session_state.edited_record_id = st.session_state.input_id_edit
            st.rerun()

    
    edited_id = st.session_state.edited_record_id
    
    if edited_id and not df_actual.empty:
        # Encuentra el registro a editar
        record_to_edit = df_actual[df_actual['id'] == edited_id]

        if not record_to_edit.empty:
            record_dict = record_to_edit.iloc[0].to_dict()

            with st.expander(f"**Modificar Registro ID: {edited_id} - {record_dict['Paciente']}**", expanded=True):
                
                # --- Inicialización de estado de edición si es la primera vez ---
                
                # Inicializar solo si es un nuevo ID o si las claves no existen
                if f'edit_valor_bruto_{edited_id}' not in st.session_state:
                    st.session_state[f'edit_valor_bruto_{edited_id}'] = record_dict['Valor Bruto']
                    st.session_state[f'edit_desc_adic_{edited_id}'] = record_dict['Desc. Adicional'] # Clave correcta
                    
                    # Guardamos los descuentos fijos originales para su uso
                    st.session_state.original_desc_fijo_lugar = record_dict['Desc. Fijo Lugar']
                    st.session_state.original_desc_tarjeta = record_dict['Desc. Tarjeta']

                    # Inicializar las claves de los selectores/inputs
                    st.session_state[f'edit_lugar_{edited_id}'] = record_dict['Lugar']
                    st.session_state[f'edit_item_{edited_id}'] = record_dict['Ítem']
                    st.session_state[f'edit_paciente_{edited_id}'] = record_dict['Paciente']
                    st.session_state[f'edit_metodo_{edited_id}'] = record_dict['Método Pago']
                    st.session_state[f'edit_fecha_{edited_id}'] = record_dict['Fecha'] # date object

                st.markdown("#### Datos de la Aventura")
                
                col_e1, col_e2, col_e3 = st.columns([1.5, 1, 1])
                
                with col_e1:
                    st.date_input("🗓️ Fecha de Atención", 
                                  st.session_state[f'edit_fecha_{edited_id}'], 
                                  key=f'edit_fecha_{edited_id}', 
                                  on_change=force_recalculate)
                    
                    st.selectbox("📍 Lugar", 
                                 options=LUGARES, 
                                 key=f'edit_lugar_{edited_id}', 
                                 on_change=update_edit_price, 
                                 args=(edited_id,))
                    
                    # Recalculamos la lista de items disponibles
                    current_lugar_edit = st.session_state[f'edit_lugar_{edited_id}']
                    items_edit_list = list(PRECIOS_BASE_CONFIG.get(current_lugar_edit.upper(), {}).keys())
                    
                    item_edit_default = st.session_state.get(f'edit_item_{edited_id}', items_edit_list[0] if items_edit_list else '')
                    
                    try:
                        item_idx = items_edit_list.index(item_edit_default) if item_edit_default in items_edit_list else 0
                    except ValueError:
                         item_idx = 0
                        
                    st.selectbox("📋 Ítem", 
                                 options=items_edit_list, 
                                 key=f'edit_item_{edited_id}', 
                                 index=item_idx, 
                                 on_change=update_edit_price, 
                                 args=(edited_id,))
                                 
                    st.text_input("👤 Paciente/Héroe", st.session_state[f'edit_paciente_{edited_id}'], key=f'edit_paciente_{edited_id}')

                with col_e2:
                    st.number_input("💰 **Valor Bruto (Recompensa)**", 
                                    min_value=0, step=1000, 
                                    key=f'edit_valor_bruto_{edited_id}', 
                                    on_change=force_recalculate)
                    
                    st.number_input("✂️ **Desc. Adicional Manual**", 
                                    step=1000, 
                                    key=f'edit_desc_adic_{edited_id}', 
                                    on_change=force_recalculate, 
                                    help="Ajuste positivo para descuentos, negativo para cargos.")
                    
                    try:
                        metodo_idx = METODOS_PAGO.index(st.session_state[f'edit_metodo_{edited_id}'])
                    except ValueError:
                         metodo_idx = 0
                        
                    st.radio("💳 Método de Pago", 
                             options=METODOS_PAGO, 
                             key=f'edit_metodo_{edited_id}', 
                             index=metodo_idx,
                             on_change=force_recalculate)

                with col_e3:
                    st.markdown("#### Descuentos Aplicados")
                    
                    # Valores actuales para display
                    current_desc_fijo = st.session_state.get('original_desc_fijo_lugar', record_dict['Desc. Fijo Lugar'])
                    current_desc_tarjeta = st.session_state.get('original_desc_tarjeta', record_dict['Desc. Tarjeta'])
                    current_desc_adic = st.session_state.get(f'edit_desc_adic_{edited_id}', 0)
                    
                    current_total = (
                        st.session_state.get(f'edit_valor_bruto_{edited_id}', 0) 
                        - current_desc_fijo 
                        - current_desc_tarjeta 
                        - current_desc_adic
                    )
                    
                    st.metric("Desc. Fijo Lugar (Tributo)", format_currency(current_desc_fijo), 
                              help=f"Actual: {format_currency(current_desc_fijo)}. Original: {format_currency(record_dict['Desc. Fijo Lugar'])}")
                    
                    st.metric("Desc. Tarjeta (Comisión)", format_currency(current_desc_tarjeta),
                              help=f"Actual: {format_currency(current_desc_tarjeta)}. Original: {format_currency(record_dict['Desc. Tarjeta'])}")
                    
                    st.markdown(f"**Tesoro Líquido Neto:** **{format_currency(current_total)}**")
                    
                    st.markdown("---")
                    
                    st.button("🔄 Actualizar Valor Bruto al Base", 
                              key=f'btn_update_price_form_{edited_id}', 
                              on_click=update_edit_bruto_price, 
                              args=(edited_id,), 
                              help="Fuerza el Valor Bruto al precio base configurado para el Ítem y Lugar actuales.")

                    st.button("🏛️ Recalcular Tributo", 
                              key=f'btn_update_tributo_form_{edited_id}', 
                              on_click=update_edit_tributo, 
                              args=(edited_id,), 
                              help="Recalcula el Desc. Fijo Lugar (Tributo) basado en el Lugar y la Fecha actual, aplicando reglas especiales.")
                    
                    st.button("💳 Recalcular Comisión Tarjeta", 
                              key=f'btn_update_tarjeta_form_{edited_id}', 
                              on_click=update_edit_desc_tarjeta, 
                              args=(edited_id,), 
                              help="Recalcula el Desc. Tarjeta basado en el Método de Pago, Valor Bruto y Desc. Adicional actuales.")

                st.markdown("---")
                
                col_save_e, col_close_e = st.columns(2)
                
                with col_save_e:
                    if st.button("💾 Guardar Cambios en BD", 
                                 key=f'btn_save_edit_form_{edited_id}', 
                                 type="primary",
                                 on_click=save_edit_state_to_df):
                        st.session_state.deletion_pending_cleanup = True # Pone el flag para limpiar y recargar
                        st.success(f"Registro ID {edited_id} actualizado. Recargando datos...")

                with col_close_e:
                    st.button("❌ Cerrar Edición", 
                              key=f'btn_close_edit_form_{edited_id}', 
                              on_click=_cleanup_edit_state, 
                              type="secondary")

        else:
            st.warning(f"No se encontró el registro con ID: {edited_id}")
            st.session_state.edited_record_id = None # Limpia el estado si el ID no existe

# =========================================================================
# CONTINUACIÓN DE PESTAÑAS (DASHBOARD Y CONFIGURACIÓN)
# =========================================================================

# --- Dashboard (Mapa del Tesoro) ---
with tab_dashboard:
    st.subheader("🗺️ Mapa del Tesoro (Resumen de Ingresos)")
    
    if st.session_state.atenciones_df.empty:
        st.info("No hay datos para mostrar en el mapa.")
    else:
        df_dash = st.session_state.atenciones_df.copy()
        df_dash['Fecha'] = pd.to_datetime(df_dash['Fecha'])
        df_dash['Mes'] = df_dash['Fecha'].dt.to_period('M')
        
        st.dataframe(df_dash.sort_values(by='id', ascending=False), use_container_width=True)

        # Gráfico de tendencias mensuales
        df_monthly = df_dash.groupby('Mes')['Total Recibido'].sum().reset_index()
        df_monthly['Mes'] = df_monthly['Mes'].astype(str)
        
        fig = px.bar(df_monthly, 
                     x='Mes', 
                     y='Total Recibido', 
                     text='Total Recibido',
                     title='Tesoro Recibido por Mes',
                     labels={'Total Recibido': 'Total Recibido', 'Mes': 'Mes'})
        
        fig.update_traces(texttemplate='%{text:$.2s}', textposition='outside')
        fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide', yaxis={'title': ''})
        st.plotly_chart(fig, use_container_width=True)


# --- Configuración Maestra ---
with tab_config:
    st.subheader("🛠️ Configuración Maestra")
    
    if st.button("🔄 Recargar archivos de Configuración", type="secondary"):
        re_load_global_config()
        st.success("Configuración recargada desde archivos JSON.")
        st.rerun() 
        
    st.markdown("---")

    # Función genérica para manejar la edición de configuración
    def edit_config_data(title, filename, config_dict):
        st.markdown(f"#### {title}")
        st.markdown(f"Archivo: `{filename}`")
        
        # Convertir a DataFrame para edición
        if filename == PRECIOS_FILE:
            # Precios es más complejo (Lugar -> Item -> Precio)
            rows = []
            for lugar, items in config_dict.items():
                for item, precio in items.items():
                    rows.append({'Lugar': lugar.upper(), 'Ítem': item, 'Precio': int(precio)})
            df_config = pd.DataFrame(rows)
            column_config = {"Precio": st.column_config.NumberColumn("Precio ($)", format="%.0f", help="Valor Bruto del servicio.")}
            
        elif filename == REGLAS_FILE:
             # Reglas (Lugar -> Día -> Monto)
            rows = []
            for lugar, reglas in config_dict.items():
                for dia, monto in reglas.items():
                    rows.append({'Lugar': lugar.upper(), 'Día': dia.upper(), 'Monto': int(monto)})
            df_config = pd.DataFrame(rows)
            column_config = {"Monto": st.column_config.NumberColumn("Monto ($)", format="%.0f", help="Monto fijo de descuento por día especial.")}
            
        else:
            # Configuración simple (Clave -> Valor)
            df_config = pd.DataFrame(list(config_dict.items()), columns=['Clave', 'Valor'])
            
            if filename == COMISIONES_FILE:
                 column_config = {"Valor": st.column_config.NumberColumn("Valor (Tasa %)", format="%.2f", help="Tasa de comisión (ej: 0.03 para 3%).")}
            else:
                 column_config = {"Valor": st.column_config.NumberColumn("Valor ($)", format="%.0f", help="Monto de descuento/valor.")}

        # Widget de edición de datos
        edited_df = st.data_editor(
            df_config,
            key=f'edit_key_{filename}',
            num_rows="dynamic",
            use_container_width=True,
            column_config=column_config if 'column_config' in locals() else None
        )

        if st.button(f"💾 Guardar {title}", key=f'btn_save_{filename}', type="primary"):
            
            new_data = {}
            valid_save = True

            if filename == PRECIOS_FILE:
                # Reconstruir la estructura Lugar -> Item -> Precio
                for _, row in edited_df.iterrows():
                    lugar = str(row['Lugar']).upper()
                    item = str(row['Ítem'])
                    precio = sanitize_number_input(row['Precio'])
                    if lugar and item and precio >= 0:
                         if lugar not in new_data: new_data[lugar] = {}
                         new_data[lugar][item] = precio
                    elif not pd.isna(row['Lugar']) and not pd.isna(row['Ítem']):
                        st.warning(f"Fila omitida por datos inválidos: Lugar='{row['Lugar']}', Ítem='{row['Ítem']}', Precio='{row['Precio']}'")
                        
            elif filename == REGLAS_FILE:
                # Reconstruir la estructura Lugar -> Día -> Monto
                for _, row in edited_df.iterrows():
                    lugar = str(row['Lugar']).upper()
                    dia = str(row['Día']).upper()
                    monto = sanitize_number_input(row['Monto'])
                    if lugar and dia and monto >= 0:
                         if lugar not in new_data: new_data[lugar] = {}
                         new_data[lugar][dia] = monto
                    elif not pd.isna(row['Lugar']) and not pd.isna(row['Día']):
                        st.warning(f"Fila omitida por datos inválidos: Lugar='{row['Lugar']}', Día='{row['Día']}', Monto='{row['Monto']}'")
                        
            else:
                # Estructura simple Clave -> Valor
                for _, row in edited_df.iterrows():
                    clave = str(row['Clave']).upper()
                    valor = row['Valor']
                    
                    if filename == COMISIONES_FILE:
                        # Para comisiones, el valor debe ser float
                        try:
                            valor_num = float(valor)
                        except (ValueError, TypeError):
                             st.error(f"Error: La comisión '{clave}' debe ser un número decimal (ej: 0.03).")
                             valid_save = False
                             break
                    else:
                        # Para descuentos fijos, el valor debe ser int
                        valor_num = sanitize_number_input(valor)
                        
                    if clave and valid_save:
                        new_data[clave] = valor_num
                    elif not pd.isna(row['Clave']):
                        st.warning(f"Fila omitida por datos inválidos: Clave='{row['Clave']}', Valor='{row['Valor']}'")


            if valid_save:
                save_config(new_data, filename)
                re_load_global_config()
                st.success(f"Configuración de {title} guardada y recargada con éxito.")
                st.rerun() 
            else:
                st.error("No se pudo guardar la configuración debido a errores de formato.")

        st.markdown("---")

    # Llamadas a la función de edición para cada configuración
    edit_config_data("Precios Base y Servicios", PRECIOS_FILE, PRECIOS_BASE_CONFIG)
    edit_config_data("Descuentos Fijos por Lugar (Tributo Base)", DESCUENTOS_FILE, DESCUENTOS_LUGAR)
    edit_config_data("Reglas de Descuento por Día/Lugar", REGLAS_FILE, DESCUENTOS_REGLAS)
    edit_config_data("Comisiones por Método de Pago", COMISIONES_FILE, COMISIONES_PAGO)
