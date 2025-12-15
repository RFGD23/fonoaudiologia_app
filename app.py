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
        # LECTURA DE CLAVES A NIVEL RAÍZ
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
    
    # 1. Calcular el Subtotal ANTES de Tarjeta y Tributo
    # Esto define la base imponible para la comisión de la tarjeta.
    subtotal_para_tarjeta = valor_bruto - desc_adicional_manual
    
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

    # 3. Aplicar Comisión de Tarjeta (MODIFICACIÓN CLAVE)
    comision_pct = COMISIONES_PAGO.get(metodo_pago_upper, 0.00) 
    
    # Base de la comisión: max(0, Valor Bruto - Desc. Adicional)
    base_comision = max(0, subtotal_para_tarjeta) 
    desc_tarjeta = int(base_comision * comision_pct) # APLICADO AL SUBTOTAL
    
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
    # Estos deben haber sido recalculados por los callbacks si las variables clave cambiaron.
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
    
    # 1. Obtener valores de la sesión
    valor_bruto_actual = st.session_state[f'edit_valor_bruto_{edited_id}']
    
    # Asegurarse de obtener el descuento adicional actual del input de edición
    try:
        desc_adicional_actual = int(st.session_state[f'edit_desc_adic_{edited_id}'])
    except:
        desc_adicional_actual = 0
    
    # 2. Calcular la base imponible para la comisión (Valor Bruto - Desc. Adicional) ## MODIFICACIÓN CLAVE
    subtotal_para_tarjeta = valor_bruto_actual - desc_adicional_actual
    base_comision = max(0, subtotal_para_tarjeta)
    
    # 3. Aplicar la comisión
    comision_pct_actual = COMISIONES_PAGO.get(metodo_pago_actual.upper(), 0.00)
    nuevo_desc_tarjeta = int(base_comision * comision_pct_actual) ## MODIFICACIÓN CLAVE
    
    # 4. Actualizar el valor en el estado de sesión
    st.session_state.original_desc_tarjeta = nuevo_desc_tarjeta
    
    # 5. Guardar en la DB con el nuevo valor de descuento de tarjeta
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

# ------------------------------------------------------------------------------------------------
# 5. INTERFAZ DE USUARIO (FRONTEND)
# ------------------------------------------------------------------------------------------------

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
                
                tributo_calc = resultados['desc_fijo_lugar']
                tarjeta_calc = resultados['desc_tarjeta']
                total_liquido = resultados['total_recibido']

                st.metric("➖ **Tributo al Castillo (Desc. Fijo Lugar)**", format_currency(tributo_calc))
                st.metric("➖ **Comisión de Tarjeta Mágica**", format_currency(tarjeta_calc))
                st.metric("➖ **Ajuste Manual (Polvo Extra)**", format_currency(desc_adicional_calc))
                
                st.markdown("---")
                st.markdown(f"## 🏆 Tesoro Recibido (Total Líquido): **{format_currency(total_liquido)}**")

        st.form_submit_button("✅ Guardar Aventura en el Libro de Cuentas", on_click=submit_and_reset, type="primary")

# ------------------------------------------------------------------------------------------------
# CÓDIGO RESTANTE (DASHBOARD Y CONFIGURACIÓN)
# ------------------------------------------------------------------------------------------------

with tab_dashboard:
    st.subheader("📊 Mapa del Tesoro (Historial de Atenciones)")
    
    if st.session_state.atenciones_df.empty:
        st.info("Aún no hay aventuras registradas. ¡Empieza la magia en la pestaña de Registro!")
    else:
        
        df_display = st.session_state.atenciones_df.copy()
        
        # --- Cálculo de totales (Métricas) ---
        total_ingreso = df_display['Total Recibido'].sum()
        total_atenciones = len(df_display)
        
        col_metrics_1, col_metrics_2, col_metrics_3 = st.columns(3)
        
        col_metrics_1.metric("Gran Tesoro Líquido Acumulado", format_currency(total_ingreso))
        col_metrics_2.metric("Total de Aventuras (Atenciones)", total_atenciones)
        
        # Ingreso promedio por atención
        ingreso_promedio = total_ingreso / total_atenciones if total_atenciones > 0 else 0
        col_metrics_3.metric("Valor Promedio por Aventura", format_currency(ingreso_promedio))

        st.markdown("---")
        
        # --- Edición y Filtros ---
        col_edit_filter_1, col_edit_filter_2 = st.columns([1, 4])
        
        # Input de Edición por ID
        with col_edit_filter_1:
            df_display['id'] = df_display['id'].astype(str)
            all_ids = sorted(df_display['id'].tolist(), key=int, reverse=True)
            
            # Usar un selectbox para la edición con callback para cargar el formulario
            def set_edit_id():
                selected_id = st.session_state.input_id_edit
                if selected_id:
                    st.session_state.edited_record_id = int(selected_id)
                else:
                    st.session_state.edited_record_id = None
                    
            st.selectbox(
                "✏️ Editar por ID", 
                options=[''] + all_ids, 
                key='input_id_edit', 
                on_change=set_edit_id, 
                index=0, 
                help="Selecciona un ID para abrir el formulario de edición."
            )
            
            if st.button("❌ Cerrar Edición", key="btn_close_global", type="secondary"):
                 _cleanup_edit_state()
                 st.rerun()

        # Filtros
        with col_edit_filter_2:
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                selected_lugar = st.multiselect("Filtrar por Castillo/Lugar", options=LUGARES, default=[])
            with col_f2:
                selected_pago = st.multiselect("Filtrar por Método de Pago", options=METODOS_PAGO, default=[])
            with col_f3:
                # Obtener rangos de fecha
                min_date = df_display['Fecha'].min() if not df_display.empty else date.today()
                max_date = df_display['Fecha'].max() if not df_display.empty else date.today()
                
                date_range = st.date_input(
                    "Filtrar por Rango de Fecha", 
                    value=(min_date, max_date) if min_date <= max_date else (date.today(), date.today()),
                    min_value=min_date, max_value=max_date
                )
                # Asegurar que date_range tiene dos elementos
                if len(date_range) == 1:
                    date_range = (date_range[0], date_range[0])
                
            # Aplicar filtros
            df_filtered = df_display.copy()
            
            if selected_lugar:
                df_filtered = df_filtered[df_filtered['Lugar'].isin(selected_lugar)]
            if selected_pago:
                df_filtered = df_filtered[df_filtered['Método Pago'].isin(selected_pago)]
            if date_range and len(date_range) == 2:
                start_date, end_date = date_range[0], date_range[1]
                df_filtered = df_filtered[(df_filtered['Fecha'] >= start_date) & (df_filtered['Fecha'] <= end_date)]


        st.markdown("---")

        # --- Formulario de Edición (Modal) ---
        edited_id = st.session_state.edited_record_id
        
        if edited_id is not None and not df_display.empty:
            record_to_edit = df_display[df_display['id'] == edited_id].iloc[0]
            
            # Inicializar los estados de sesión para el formulario de edición
            
            # Cargar valores originales al estado si es la primera vez que se abre la edición para este ID
            if f'edit_valor_bruto_{edited_id}' not in st.session_state:
                
                # Cargar valores de la fila
                st.session_state[f'edit_valor_bruto_{edited_id}'] = record_to_edit['Valor Bruto']
                st.session_state[f'edit_desc_adic_{edited_id}'] = record_to_edit['Desc. Adicional']
                st.session_state[f'edit_lugar_{edited_id}'] = record_to_edit['Lugar']
                st.session_state[f'edit_item_{edited_id}'] = record_to_edit['Ítem']
                st.session_state[f'edit_paciente_{edited_id}'] = record_to_edit['Paciente']
                st.session_state[f'edit_metodo_{edited_id}'] = record_to_edit['Método Pago']
                st.session_state[f'edit_fecha_{edited_id}'] = record_to_edit['Fecha']
                
                # Cargar valores de descuentos fijos (Estos NO se editan directamente, se recalculan)
                st.session_state['original_desc_fijo_lugar'] = record_to_edit['Desc. Fijo Lugar']
                st.session_state['original_desc_tarjeta'] = record_to_edit['Desc. Tarjeta']


            with st.expander(f"**✏️ Editando Registro ID: {edited_id}** (Paciente: {record_to_edit['Paciente']})", expanded=True):
                
                edit_c1, edit_c2, edit_c3 = st.columns(3)
                
                # Lado izquierdo: Datos clave
                with edit_c1:
                    # Fecha, Lugar, Ítem
                    st.date_input("Fecha", key=f'edit_fecha_{edited_id}', value=st.session_state[f'edit_fecha_{edited_id}'])
                    
                    # Lugar y Ítem (actualiza precio sugerido)
                    lugar_edit_options = list(PRECIOS_BASE_CONFIG.keys())
                    st.selectbox("Lugar", options=lugar_edit_options, key=f'edit_lugar_{edited_id}', on_change=update_edit_price, args=(edited_id,))

                    items_edit_options = list(PRECIOS_BASE_CONFIG.get(st.session_state[f'edit_lugar_{edited_id}'].upper(), {}).keys())
                    st.selectbox("Ítem", options=items_edit_options, key=f'edit_item_{edited_id}', on_change=update_edit_price, args=(edited_id,))
                    
                    st.text_input("Paciente", key=f'edit_paciente_{edited_id}')

                # Centro: Valores monetarios
                with edit_c2:
                    
                    # 1. Valor Bruto
                    st.number_input("Valor Bruto", min_value=0, step=1000, key=f'edit_valor_bruto_{edited_id}', on_change=save_edit_state_to_df)
                    st.button("🔄 Recalcular Valor Bruto (Precio Base)", key=f"btn_update_price_form_{edited_id}", on_click=update_edit_bruto_price, args=(edited_id,))

                    # 2. Descuento Adicional
                    st.number_input("Desc. Adicional (Polvo Extra)", min_value=-500000, step=1000, key=f'edit_desc_adic_{edited_id}', on_change=save_edit_state_to_df)
                    
                    st.markdown("---")
                    
                    # Botones de Recálculo de Descuentos (solo aplican el cálculo, no el guardado final)
                    # El guardado se hace en el callback del botón/input que dispara el recálculo
                    st.button("🏛️ Recalcular Tributo (Desc. Fijo)", key=f"btn_update_tributo_form_{edited_id}", on_click=update_edit_tributo, args=(edited_id,))
                    st.button("💳 Recalcular Comisión de Tarjeta", key=f"btn_update_tarjeta_form_{edited_id}", on_click=update_edit_desc_tarjeta, args=(edited_id,))


                # Lado derecho: Resultados y Guardado
                with edit_c3:
                    
                    # Re-calcular los totales para mostrar la vista previa
                    # Usamos los valores actuales de la sesión (widgets) y los descuentos fijos guardados
                    
                    current_valor_bruto = st.session_state.get(f'edit_valor_bruto_{edited_id}', 0)
                    current_desc_adic = st.session_state.get(f'edit_desc_adic_{edited_id}', 0)
                    current_desc_fijo = st.session_state.get('original_desc_fijo_lugar', 0)
                    current_desc_tarjeta = st.session_state.get('original_desc_tarjeta', 0)
                    
                    current_total_liquido = (
                        current_valor_bruto 
                        - current_desc_fijo 
                        - current_desc_tarjeta 
                        - current_desc_adic
                    )
                    
                    # 3. Método de Pago (actualiza descuento tarjeta)
                    st.selectbox("Método Pago", options=METODOS_PAGO, key=f'edit_metodo_{edited_id}', on_change=update_edit_desc_tarjeta, args=(edited_id,))
                    
                    st.markdown("---")

                    st.metric("Desc. Fijo Lugar (Tributo)", format_currency(current_desc_fijo))
                    st.metric("Desc. Tarjeta (Comisión)", format_currency(current_desc_tarjeta))
                    st.markdown(f"## 💰 Tesoro Líquido: **{format_currency(current_total_liquido)}**")

                    st.markdown("---")
                    
                    # Botón de Guardado Final (opcional, ya que los inputs guardan por sí solos, pero útil para confirmar)
                    if st.button("💾 Guardar y Finalizar Edición", key=f"btn_save_edit_form_{edited_id}", type="primary", on_click=save_edit_state_to_df):
                        st.session_state.deletion_pending_cleanup = True
                        
                    if st.button("Cerrar sin guardar", key=f"btn_close_edit_form_{edited_id}", type="secondary"):
                        st.session_state.deletion_pending_cleanup = True 
                        st.rerun()


        # --- Visualización de Datos Filtrados ---
        st.subheader("Listado de Aventuras")
        
        # Ocultar columnas que son solo para cálculo
        columns_to_show = [
            'id', 'Fecha', 'Lugar', 'Ítem', 'Paciente', 'Método Pago', 
            'Valor Bruto', 'Desc. Adicional', 'Desc. Fijo Lugar', 'Desc. Tarjeta', 'Total Recibido'
        ]
        
        df_show = df_filtered[columns_to_show]
        
        # Formateo
        for col in ['Valor Bruto', 'Desc. Adicional', 'Desc. Fijo Lugar', 'Desc. Tarjeta', 'Total Recibido']:
            if col in df_show.columns:
                 # Usa apply con el lambda para evitar problemas con números grandes de float
                 df_show[col] = df_show[col].apply(lambda x: format_currency(x))

        st.dataframe(
            df_show, 
            hide_index=True,
            column_order=['id', 'Fecha', 'Lugar', 'Ítem', 'Paciente', 'Método Pago', 'Total Recibido', 'Valor Bruto', 'Desc. Adicional', 'Desc. Fijo Lugar', 'Desc. Tarjeta'],
            column_config={
                "Total Recibido": st.column_config.Column("🏆 Total Recibido", help="El tesoro final (líquido).", width="medium"),
                "Desc. Adicional": st.column_config.Column("✂️ Polvo Extra", help="Ajuste manual (Polvo Mágico Extra)."),
                "Desc. Fijo Lugar": st.column_config.Column("🏛️ Tributo Fijo", help="Descuento fijo por lugar/día."),
                "Desc. Tarjeta": st.column_config.Column("💳 Comisión Tarjeta", help="Comisión sobre el subtotal (Bruto - Adicional)."),
            },
            use_container_width=True
        )

# ------------------------------------------------------------------------------------------------
# PESTAÑA DE CONFIGURACIÓN
# ------------------------------------------------------------------------------------------------

with tab_config:
    st.subheader("⚙️ Configuración Maestra del Castillo")
    st.info("⚠️ **¡Advertencia!** Cualquier cambio aquí afectará los cálculos futuros.")
    
    tab_precios, tab_descuentos_fijos, tab_comisiones = st.tabs(["Precios Base (Ítems)", "Tributos Fijos (Lugares/Días)", "Comisiones de Pago"])
    
    with tab_precios:
        st.markdown("### 🏷️ Precios Base por Castillo y Poción")
        st.caption("Define el precio base ('Valor Bruto Sugerido') para cada combinación de Lugar y Poción/Procedimiento.")

        # --- Interfaz de Edición de Precios ---
        
        # Estructurar para edición de dataframe
        data_for_edit = []
        for lugar, items in PRECIOS_BASE_CONFIG.items():
            for item, precio in items.items():
                data_for_edit.append({'Lugar': lugar, 'Ítem': item, 'Precio Base Sugerido': precio})
                
        df_precios = pd.DataFrame(data_for_edit)
        
        edited_df_precios = st.data_editor(
            df_precios,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Precio Base Sugerido": st.column_config.NumberColumn(
                    "💰 Precio Base Sugerido",
                    format="$%,d",
                    help="Precio por defecto que se carga en el formulario.",
                    min_value=0,
                    step=1000
                ),
            },
            key="precios_data_editor"
        )
        
        if st.button("💾 Guardar Precios Base", key="save_precios", type="primary"):
            try:
                new_config = {}
                for index, row in edited_df_precios.iterrows():
                    lugar_key = str(row['Lugar']).upper().strip()
                    item_key = str(row['Ítem']).strip()
                    precio = sanitize_number_input(row['Precio Base Sugerido'])
                    
                    if lugar_key and item_key:
                        if lugar_key not in new_config:
                            new_config[lugar_key] = {}
                        new_config[lugar_key][item_key] = precio
                
                save_config(new_config, PRECIOS_FILE)
                re_load_global_config()
                st.success("Configuración de Precios Base guardada y recargada.")
                st.rerun()

            except Exception as e:
                st.error(f"Error al procesar la configuración de precios: {e}")


    with tab_descuentos_fijos:
        st.markdown("### 🏛️ Tributos Fijos (Desc. Fijo Lugar)")
        st.caption("Monto fijo de descuento por Lugar (Ej. Arriendo, Cánon). Se anula por reglas de día especial (ver tabla de reglas).")

        # --- Interfaz de Edición de Descuentos Fijos ---
        
        # Tabla para Descuentos Fijos Generales
        df_desc_fijos = pd.DataFrame(list(DESCUENTOS_LUGAR.items()), columns=['Lugar', 'Tributo Fijo'])
        
        edited_df_desc_fijos = st.data_editor(
            df_desc_fijos,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Tributo Fijo": st.column_config.NumberColumn(
                    "💰 Monto Tributo Fijo ($)",
                    format="$%,d",
                    min_value=0,
                    step=100
                ),
            },
            key="desc_fijos_data_editor"
        )
        
        if st.button("💾 Guardar Tributos Fijos Generales", key="save_desc_fijos", type="primary"):
            try:
                new_config = {}
                for index, row in edited_df_desc_fijos.iterrows():
                    lugar_key = str(row['Lugar']).upper().strip()
                    monto = sanitize_number_input(row['Tributo Fijo'])
                    if lugar_key:
                        new_config[lugar_key] = monto
                        
                save_config(new_config, DESCUENTOS_FILE)
                re_load_global_config()
                st.success("Configuración de Tributos Fijos guardada y recargada.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al procesar la configuración de tributos fijos: {e}")

        st.markdown("---")
        
        st.markdown("### 🗓️ Reglas de Descuento Especiales por Día y Lugar")
        st.caption("Estos montos anulan el 'Tributo Fijo' solo en el día especificado.")

        # --- Interfaz de Edición de Reglas por Día ---
        
        all_dias = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO', 'DOMINGO']
        
        reglas_list = []
        for lugar, reglas in DESCUENTOS_REGLAS.items():
            for dia, monto in reglas.items():
                reglas_list.append({'Lugar': lugar, 'Día': dia, 'Monto Descuento Especial': monto})
                
        df_reglas = pd.DataFrame(reglas_list)
        
        edited_df_reglas = st.data_editor(
            df_reglas,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Día": st.column_config.SelectboxColumn(
                    "Día de la Semana",
                    options=all_dias,
                    required=True
                ),
                "Monto Descuento Especial": st.column_config.NumberColumn(
                    "💰 Monto Descuento ($)",
                    format="$%,d",
                    min_value=0,
                    step=100
                ),
            },
            key="reglas_data_editor"
        )
        
        if st.button("💾 Guardar Reglas Especiales por Día", key="save_reglas", type="primary"):
            try:
                new_config = {}
                for index, row in edited_df_reglas.iterrows():
                    lugar_key = str(row['Lugar']).upper().strip()
                    dia_key = str(row['Día']).upper().strip()
                    monto = sanitize_number_input(row['Monto Descuento Especial'])
                    
                    if lugar_key and dia_key in all_dias:
                        if lugar_key not in new_config:
                            new_config[lugar_key] = {}
                        new_config[lugar_key][dia_key] = monto
                        
                save_config(new_config, REGLAS_FILE)
                re_load_global_config()
                st.success("Configuración de Reglas por Día guardada y recargada.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al procesar la configuración de reglas: {e}")


    with tab_comisiones:
        st.markdown("### 💳 Comisiones de Tarjeta Mágica")
        st.caption("Porcentaje de comisión por método de pago. El porcentaje se aplica sobre el Valor Bruto - Desc. Adicional.")

        # --- Interfaz de Edición de Comisiones ---
        
        df_comisiones = pd.DataFrame(list(COMISIONES_PAGO.items()), columns=['Método Pago', 'Comisión (%)'])
        
        edited_df_comisiones = st.data_editor(
            df_comisiones,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Comisión (%)": st.column_config.NumberColumn(
                    "Tasa (%)",
                    format="%.2f",
                    min_value=0.00,
                    max_value=1.00,
                    step=0.01
                ),
            },
            key="comisiones_data_editor"
        )
        
        if st.button("💾 Guardar Comisiones de Pago", key="save_comisiones", type="primary"):
            try:
                new_config = {}
                for index, row in edited_df_comisiones.iterrows():
                    pago_key = str(row['Método Pago']).upper().strip()
                    # Convertir a float. Usamos .get() para manejar valores NaN o None.
                    comision = row.get('Comisión (%)') 
                    if pd.isna(comision): comision = 0.00
                    
                    if pago_key:
                        new_config[pago_key] = float(comision)
                        
                save_config(new_config, COMISIONES_FILE)
                re_load_global_config()
                st.success("Configuración de Comisiones guardada y recargada.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al procesar la configuración de comisiones: {e}")

# ------------------------------------------------------------------------------------------------
# FIN DEL CÓDIGO
# ------------------------------------------------------------------------------------------------
