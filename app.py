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
    # =================================================================================
    # CAMBIO SOLICITADO: Descuento Tarjeta = (Valor Bruto - Desc. Adicional) * Comisión
    # =================================================================================
    base_para_comision = valor_bruto - desc_adicional_manual 
    desc_tarjeta = int(base_para_comision * comision_pct)
    # =================================================================================
    
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
        st.session_state.form_item = items_filtrados_current[0]
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
        
    # 🚨 CORRECCIÓN DE ROBUSTEZ: Asegurar el ID antes de la recarga
    st.session_state.edited_record_id = edited_id 
    
    st.rerun() 

def update_edit_desc_tarjeta(edited_id):
    """Callback: Recalcula y actualiza el Desc. Tarjeta (y guarda)."""
    metodo_pago_actual = st.session_state[f'edit_metodo_{edited_id}']
    valor_bruto_actual = st.session_state[f'edit_valor_bruto_{edited_id}']
    desc_adicional_actual = st.session_state[f'edit_desc_adic_{edited_id}'] # Se usa para la nueva lógica
    
    comision_pct_actual = COMISIONES_PAGO.get(metodo_pago_actual.upper(), 0.00)
    # Aplicando la nueva lógica: Valor Bruto - Desc. Adicional
    base_para_comision = valor_bruto_actual - desc_adicional_actual
    nuevo_desc_tarjeta = int(base_para_comision * comision_pct_actual)
    
    # 1. Actualizar el valor en el estado de sesión
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
                
                # ... (El resto del código del bloque 'else' y el `st.form` continúa aquí)
                
                st.metric("💸 Desc. Fijo (Tributo a la Hostería)", format_currency(resultados['desc_fijo_lugar']))
                st.metric("💳 Desc. por Tarjeta (Comisión del Banco)", format_currency(resultados['desc_tarjeta']), 
                          help="Calculado como (Valor Bruto - Polvo Mágico Extra) * Comisión %")
                st.metric("✨ Total Neto a Recibir (El Tesoro)", format_currency(resultados['total_recibido']), delta=format_currency(resultados['total_recibido']))
                
                st.markdown("---")
                st.form_submit_button("✅ Guardar Aventura (Registro)", type="primary", on_click=submit_and_reset)
                
    st.markdown("---")
    st.markdown("### 📜 **Tabla de Ingresos Recientes**")

    # Muestra la tabla de datos
    if st.session_state.atenciones_df.empty:
        st.info("Aún no hay aventuras registradas. ¡Hora de empezar!")
    else:
        df_display = st.session_state.atenciones_df.copy()
        
        # Ocultar la columna ID si no está en modo edición
        if st.session_state.edited_record_id is None:
            df_display = df_display.rename(columns={'id': 'ID'})
            column_order = [
                'Fecha', 'Lugar', 'Ítem', 'Paciente', 
                'Método Pago', 'Valor Bruto', 'Desc. Fijo Lugar', 
                'Desc. Tarjeta', 'Desc. Adicional', 'Total Recibido', 
                'ID'
            ]
            df_display = df_display.reindex(columns=column_order)
            
            # Formatear las columnas de dinero como moneda
            money_cols = ['Valor Bruto', 'Desc. Fijo Lugar', 'Desc. Tarjeta', 'Desc. Adicional', 'Total Recibido']
            for col in money_cols:
                df_display[col] = df_display[col].apply(format_currency)

            # Mostrar la tabla, incluyendo un botón de acción en la tabla dinámica
            def render_row(row):
                cols = st.columns([1, 1, 1.5, 2, 1, 1.5, 1.5, 1.5, 1.5, 1.5, 0.5]) # Ajuste para las 11 columnas
                
                # Contenido de la fila
                for i, col_name in enumerate(df_display.columns):
                    if col_name == 'ID': continue # Se salta la ID para el botón
                    cols[i].markdown(f"<div class='data-row'>{row[col_name]}</div>", unsafe_allow_html=True)
                
                # Botón de edición
                with cols[-1]:
                    # Usamos una función para envolver el callback del botón y capturar el ID
                    def set_edit_mode(record_id):
                        st.session_state.edited_record_id = record_id
                        st.session_state.input_id_edit = record_id
                        st.rerun() # Forzar rerun para mostrar el expander
                        
                    st.button("Editar", key=f"edit_btn_{row['ID']}", on_click=set_edit_mode, args=(row['ID'],))

            # Renderizar el encabezado
            header_cols = st.columns([1, 1, 1.5, 2, 1, 1.5, 1.5, 1.5, 1.5, 1.5, 0.5])
            header_names = ['Fecha', 'Lugar', 'Ítem', 'Paciente', 'Método Pago', 'Valor Bruto', 'Desc. Fijo Lugar', 'Desc. Tarjeta', 'Desc. Adicional', 'Total Recibido', 'Acción']
            for i, col_name in enumerate(header_names):
                header_cols[i].markdown(f"<div class='row-header'>{col_name}</div>", unsafe_allow_html=True)

            # Iterar y renderizar filas
            df_recent = df_display.sort_values(by='ID', ascending=False).head(20) # Mostrar solo las 20 más recientes
            for index, row in df_recent.iterrows():
                render_row(row)
                
            # --- Modal de Edición (Expander) ---
            if st.session_state.edited_record_id is not None:
                
                record_id_to_edit = st.session_state.edited_record_id
                
                # Buscar el registro original en el DataFrame (sin formatear)
                original_row = st.session_state.atenciones_df[st.session_state.atenciones_df['id'] == record_id_to_edit].iloc[0]
                
                # Inicializar los estados de sesión para la edición (si no existen o si se cambió el ID)
                if st.session_state.get('input_id_edit') != record_id_to_edit:
                    
                    st.session_state[f'edit_lugar_{record_id_to_edit}'] = original_row['Lugar']
                    st.session_state[f'edit_item_{record_id_to_edit}'] = original_row['Ítem']
                    st.session_state[f'edit_valor_bruto_{record_id_to_edit}'] = original_row['Valor Bruto']
                    st.session_state[f'edit_desc_adic_{record_id_to_edit}'] = original_row['Desc. Adicional']
                    st.session_state[f'edit_fecha_{record_id_to_edit}'] = original_row['Fecha']
                    st.session_state[f'edit_metodo_{record_id_to_edit}'] = original_row['Método Pago']
                    st.session_state[f'edit_paciente_{record_id_to_edit}'] = original_row['Paciente']
                    
                    # Guardamos los descuentos calculados originalmente para mostrarlos/usarlos como base
                    st.session_state['original_desc_fijo_lugar'] = original_row['Desc. Fijo Lugar']
                    st.session_state['original_desc_tarjeta'] = original_row['Desc. Tarjeta']
                    
                    st.session_state.input_id_edit = record_id_to_edit
                    
                    # Forzar una recarga inicial para que todos los widgets tengan sus valores iniciales correctos
                    st.rerun() 
                    
                
                # Re-obtener los valores para asegurar la reactividad
                lugar_edit_val = st.session_state.get(f'edit_lugar_{record_id_to_edit}')
                item_edit_val = st.session_state.get(f'edit_item_{record_id_to_edit}')
                valor_bruto_edit_val = st.session_state.get(f'edit_valor_bruto_{record_id_to_edit}')
                desc_adic_edit_val = st.session_state.get(f'edit_desc_adic_{record_id_to_edit}')
                fecha_edit_val = st.session_state.get(f'edit_fecha_{record_id_to_edit}')
                metodo_edit_val = st.session_state.get(f'edit_metodo_{record_id_to_edit}')
                paciente_edit_val = st.session_state.get(f'edit_paciente_{record_id_to_edit}')
                
                desc_fijo_current = st.session_state.get('original_desc_fijo_lugar', 0)
                desc_tarjeta_current = st.session_state.get('original_desc_tarjeta', 0)
                
                
                with st.expander(f"**🛠️ Editando Registro ID: {record_id_to_edit} - {paciente_edit_val}**", expanded=True):
                    
                    # --- Formulario de Edición ---
                    with st.form(key=f"edit_form_{record_id_to_edit}"):
                        
                        col_e1, col_e2, col_e3, col_e4 = st.columns(4)
                        
                        with col_e1:
                            lugar_edit_options = list(PRECIOS_BASE_CONFIG.keys())
                            try:
                                lugar_edit_idx = lugar_edit_options.index(lugar_edit_val)
                            except:
                                lugar_edit_idx = 0

                            st.selectbox("📍 Lugar", 
                                options=lugar_edit_options, 
                                key=f'edit_lugar_{record_id_to_edit}', 
                                index=lugar_edit_idx,
                                on_change=update_edit_price, # Actualiza precio sugerido
                                args=(record_id_to_edit,))

                        with col_e2:
                            current_items_edit = list(PRECIOS_BASE_CONFIG.get(lugar_edit_val.upper(), {}).keys())
                            try:
                                item_edit_idx = current_items_edit.index(item_edit_val)
                            except:
                                item_edit_idx = 0

                            st.selectbox("📋 Ítem", 
                                options=current_items_edit, 
                                key=f'edit_item_{record_id_to_edit}', 
                                index=item_edit_idx,
                                on_change=update_edit_price, # Actualiza precio sugerido
                                args=(record_id_to_edit,))

                        with col_e3:
                            st.number_input("💰 Valor Bruto", 
                                min_value=0, 
                                step=1000, 
                                key=f'edit_valor_bruto_{record_id_to_edit}', 
                                on_change=force_recalculate) # Fuerza el cálculo del total líquido

                        with col_e4:
                            st.number_input("✂️ Desc. Adicional", 
                                step=1000,
                                key=f'edit_desc_adic_{record_id_to_edit}',
                                on_change=force_recalculate)
                            
                        # --- Fila 2: Fecha, Pago y Paciente ---
                        col_f1, col_f2, col_f3 = st.columns(3)
                        
                        with col_f1:
                            st.date_input("🗓️ Fecha", 
                                value=fecha_edit_val,
                                key=f'edit_fecha_{record_id_to_edit}',
                                on_change=force_recalculate)
                            
                        with col_f2:
                            pago_edit_options = METODOS_PAGO
                            try:
                                pago_edit_idx = pago_edit_options.index(metodo_edit_val)
                            except:
                                pago_edit_idx = 0
                                
                            st.selectbox("💳 Método de Pago", 
                                options=pago_edit_options, 
                                key=f'edit_metodo_{record_id_to_edit}',
                                index=pago_edit_idx,
                                on_change=force_recalculate)
                            
                        with col_f3:
                            st.text_input("👤 Paciente", 
                                value=paciente_edit_val,
                                key=f'edit_paciente_{record_id_to_edit}')
                            
                        st.markdown("---")
                        
                        # --- Fila de Cálculos y Botones ---
                        col_r1, col_r2, col_r3, col_r4 = st.columns([2, 2, 2, 4])
                        
                        # Calcular el total actual
                        total_liquido_actual = (
                            st.session_state[f'edit_valor_bruto_{record_id_to_edit}']
                            - desc_fijo_current
                            - desc_tarjeta_current
                            - st.session_state[f'edit_desc_adic_{record_id_to_edit}']
                        )
                        
                        with col_r1:
                            st.metric("💸 Desc. Fijo (Tributo)", format_currency(desc_fijo_current))
                            st.button("🔄 Recalcular Tributo", 
                                key=f"btn_update_tributo_form_{record_id_to_edit}", 
                                on_click=update_edit_tributo, 
                                args=(record_id_to_edit,),
                                help="Recalcula el tributo (Desc. Fijo) basado en el Lugar y la Fecha.")

                        with col_r2:
                            st.metric("💳 Desc. Tarjeta", format_currency(desc_tarjeta_current))
                            st.button("🔄 Recalcular Tarjeta", 
                                key=f"btn_update_tarjeta_form_{record_id_to_edit}", 
                                on_click=update_edit_desc_tarjeta, 
                                args=(record_id_to_edit,),
                                help="Recalcula el descuento de tarjeta basado en el Valor Bruto, Desc. Adicional y Método de Pago.")
                            
                        with col_r3:
                            st.metric("✨ **Total Líquido Final**", format_currency(total_liquido_actual))
                            st.button("💰 Recalcular Total Bruto", 
                                key=f"btn_update_price_form_{record_id_to_edit}", 
                                on_click=update_edit_bruto_price, 
                                args=(record_id_to_edit,),
                                help="Establece el Valor Bruto al precio base sugerido del ítem/lugar.")
                            
                        with col_r4:
                            st.markdown("---")
                            col_save, col_close = st.columns(2)
                            with col_save:
                                # El submit button siempre se usa para la acción principal y guarda todos los campos
                                if st.form_submit_button("💾 Guardar Cambios y Recalcular Total", type="primary", key=f"btn_save_edit_form_{record_id_to_edit}"):
                                    final_total = save_edit_state_to_df()
                                    st.toast(f"✅ ¡Registro {record_id_to_edit} Actualizado! Tesoro Líquido: {format_currency(final_total)}", icon="💾")
                                    st.session_state.deletion_pending_cleanup = True # Para limpiar el expander
                                    st.rerun() 
                            with col_close:
                                if st.button("❌ Cerrar Edición", key=f"btn_close_edit_form_{record_id_to_edit}"):
                                    st.session_state.deletion_pending_cleanup = True 
                                    st.rerun()


with tab_dashboard:
    # =========================================================================
    # DASHBOARD
    # =========================================================================
    st.subheader("📊 Mapa del Tesoro (Dashboard de Ingresos)")
    
    df_data = st.session_state.atenciones_df.copy()
    
    if df_data.empty:
        st.info("No hay datos para mostrar en el Mapa del Tesoro.")
    else:
        
        # --- Cálculo de Métricas Clave ---
        total_ingreso = df_data['Total Recibido'].sum()
        total_atenciones = len(df_data)
        
        df_mes = df_data.copy()
        df_mes['Mes'] = pd.to_datetime(df_mes['Fecha']).dt.to_period('M')
        
        # Filtro por Mes
        meses_disponibles = sorted(df_mes['Mes'].unique(), reverse=True)
        meses_formateados = [f"{m.year}-{m.month:02d}" for m in meses_disponibles]
        
        mes_seleccionado_str = st.selectbox("📅 Selecciona el Mes a Analizar", options=meses_formateados)
        mes_seleccionado_period = pd.Period(mes_seleccionado_str)
        
        df_filtrado = df_mes[df_mes['Mes'] == mes_seleccionado_period]
        
        total_ingreso_mes = df_filtrado['Total Recibido'].sum()
        total_atenciones_mes = len(df_filtrado)
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("💰 Tesoro Líquido Total (Mes)", format_currency(total_ingreso_mes))
        col_m2.metric("👤 Aventuras Registradas (Mes)", total_atenciones_mes)
        
        # --- Gráfico 1: Ingresos por Lugar ---
        ingresos_por_lugar = df_filtrado.groupby('Lugar')['Total Recibido'].sum().reset_index()
        ingresos_por_lugar['Total Recibido'] = ingresos_por_lugar['Total Recibido'].apply(lambda x: x / 1000) # Para simplificar el eje
        
        fig_lugar = px.bar(
            ingresos_por_lugar, 
            x='Lugar', 
            y='Total Recibido', 
            title=f"Tesoro Líquido por Castillo (Miles de ${mes_seleccionado_str})",
            labels={'Total Recibido': 'Tesoro Líquido (k$)', 'Lugar': 'Castillo'},
            color='Lugar',
            template="plotly_dark"
        )
        st.plotly_chart(fig_lugar, use_container_width=True)

        # --- Gráfico 2: Distribución por Método de Pago ---
        ingresos_por_pago = df_filtrado.groupby('Método Pago')['Total Recibido'].sum().reset_index()
        fig_pago = px.pie(
            ingresos_por_pago, 
            values='Total Recibido', 
            names='Método Pago', 
            title=f"Distribución del Tesoro por Método de Pago ({mes_seleccionado_str})",
            template="plotly_dark"
        )
        st.plotly_chart(fig_pago, use_container_width=True)


with tab_config:
    # =========================================================================
    # CONFIGURACIÓN MAESTRA
    # =========================================================================
    st.subheader("⚙️ Configuración Maestra del Tesoro y Tributos")
    st.markdown("Modifica los precios, descuentos fijos y comisiones por pago. Los cambios se guardan automáticamente.")

    tab_precios, tab_descuentos_fijos, tab_comisiones = st.tabs(["Precios Base", "Tributos Fijos/Reglas", "Comisiones por Pago"])

    # -----------------------------------------------
    # 6.1. PRECIOS BASE
    # -----------------------------------------------
    with tab_precios:
        st.markdown("### 💰 Precios Base por Castillo/Lugar y Poción/Procedimiento")
        st.warning("🚨 Importante: Modificar estos valores no afecta los registros pasados. Solo los nuevos registros usarán estos precios sugeridos.")
        
        # Convertir la configuración anidada a un DataFrame para edición
        precios_data = []
        for lugar, items in PRECIOS_BASE_CONFIG.items():
            for item, precio in items.items():
                precios_data.append({'Lugar': lugar, 'Ítem': item, 'Valor Bruto Base': precio})
                
        df_precios = pd.DataFrame(precios_data)
        
        # Usar st.data_editor para permitir edición en línea
        edited_df_precios = st.data_editor(
            df_precios,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Valor Bruto Base": st.column_config.NumberColumn(
                    "Valor Bruto Base",
                    format="$%d",
                    min_value=0,
                    step=1000,
                )
            },
            key="precios_data_editor"
        )
        
        if st.button("💾 Guardar Precios Base Actualizados", key="save_precios_btn", type="primary"):
            new_precios_config = {}
            for _, row in edited_df_precios.iterrows():
                lugar = row['Lugar'].upper().strip()
                item = str(row['Ítem']).strip()
                precio = sanitize_number_input(row['Valor Bruto Base'])
                
                if lugar and item:
                    if lugar not in new_precios_config:
                        new_precios_config[lugar] = {}
                    new_precios_config[lugar][item] = precio
                    
            save_config(new_precios_config, PRECIOS_FILE)
            re_load_global_config() # Recargar la configuración global
            st.toast("✅ Precios Base Guardados y Recargados.", icon="💰")
            st.rerun()


    # -----------------------------------------------
    # 6.2. DESCUENTOS FIJOS Y REGLAS (TRIBUTOS)
    # -----------------------------------------------
    with tab_descuentos_fijos:
        st.markdown("### 🏛️ Tributos Fijos por Castillo/Lugar")
        st.warning("El Tributo es un descuento **fijo** que se aplica por el solo hecho de la atención en ese Lugar, **a menos que** exista una regla especial por día para ese Lugar.")
        
        # Descuentos Fijos por Lugar (Inicial)
        df_desc_lugar = pd.DataFrame(
            DESCUENTOS_LUGAR.items(), 
            columns=['Lugar', 'Tributo Base (Desc. Fijo)']
        )
        
        edited_df_desc_lugar = st.data_editor(
            df_desc_lugar,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Tributo Base (Desc. Fijo)": st.column_config.NumberColumn(
                    "Tributo Base (Desc. Fijo)",
                    format="$%d",
                    min_value=0,
                    step=100,
                )
            },
            key="desc_lugar_data_editor"
        )
        
        if st.button("💾 Guardar Tributos Base", key="save_desc_lugar_btn", type="primary"):
            new_desc_config = {}
            for _, row in edited_df_desc_lugar.iterrows():
                lugar = str(row['Lugar']).upper().strip()
                monto = sanitize_number_input(row['Tributo Base (Desc. Fijo)'])
                
                if lugar:
                    new_desc_config[lugar] = monto
                    
            save_config(new_desc_config, DESCUENTOS_FILE)
            re_load_global_config()
            st.toast("✅ Tributos Base Guardados y Recargados.", icon="🏛️")
            st.rerun()
            
        st.markdown("---")
        
        # Reglas Especiales por Día
        st.markdown("### 🗓️ Reglas Especiales por Día de la Semana (Sobrescriben el Tributo Base)")
        st.info("Define montos de tributo diferentes para días específicos. Si se deja un Lugar sin reglas, usará el Tributo Base.")
        
        reglas_data = []
        for lugar, reglas in DESCUENTOS_REGLAS.items():
            for dia, monto in reglas.items():
                reglas_data.append({'Lugar': lugar, 'Día de la Semana': dia, 'Tributo Especial': monto})
                
        df_reglas = pd.DataFrame(reglas_data)
        
        edited_df_reglas = st.data_editor(
            df_reglas,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Día de la Semana": st.column_config.SelectboxColumn(
                    "Día de la Semana",
                    options=DIAS_SEMANA
                ),
                "Lugar": st.column_config.SelectboxColumn(
                    "Lugar",
                    options=LUGARES
                ),
                "Tributo Especial": st.column_config.NumberColumn(
                    "Tributo Especial",
                    format="$%d",
                    min_value=0,
                    step=100,
                )
            },
            key="reglas_data_editor"
        )
        
        if st.button("💾 Guardar Reglas Especiales", key="save_reglas_btn", type="secondary"):
            new_reglas_config = {}
            for _, row in edited_df_reglas.iterrows():
                lugar = str(row['Lugar']).upper().strip()
                dia = str(row['Día de la Semana']).upper().strip()
                monto = sanitize_number_input(row['Tributo Especial'])
                
                if lugar and dia in DIAS_SEMANA:
                    if lugar not in new_reglas_config:
                        new_reglas_config[lugar] = {}
                    new_reglas_config[lugar][dia] = monto
                    
            save_config(new_reglas_config, REGLAS_FILE)
            re_load_global_config()
            st.toast("✅ Reglas Especiales Guardadas y Recargadas.", icon="🗓️")
            st.rerun()
            

    # -----------------------------------------------
    # 6.3. COMISIONES POR PAGO
    # -----------------------------------------------
    with tab_comisiones:
        st.markdown("### 💳 Comisiones por Método de Pago")
        st.info("Estas comisiones se aplican al Valor Bruto **descontando el Polvo Mágico Extra** (Desc. Adicional) si el método es 'TARJETA'. Para otros métodos, el valor es 0.00.")
        
        # Comisiones por Pago
        df_comisiones = pd.DataFrame(
            COMISIONES_PAGO.items(), 
            columns=['Método Pago', 'Comisión (%)']
        )
        
        edited_df_comisiones = st.data_editor(
            df_comisiones,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Comisión (%)": st.column_config.NumberColumn(
                    "Comisión (%)",
                    format="%.2f",
                    min_value=0.00,
                    max_value=1.00,
                    step=0.005,
                )
            },
            key="comisiones_data_editor"
        )
        
        if st.button("💾 Guardar Comisiones por Pago", key="save_comisiones_btn", type="primary"):
            new_comisiones_config = {}
            for _, row in edited_df_comisiones.iterrows():
                metodo = str(row['Método Pago']).upper().strip()
                comision = float(row['Comisión (%)'])
                
                if metodo:
                    new_comisiones_config[metodo] = comision
                    
            save_config(new_comisiones_config, COMISIONES_FILE)
            re_load_global_config()
            st.toast("✅ Comisiones Guardadas y Recargadas.", icon="💳")
            st.rerun()

# Fin del script.
