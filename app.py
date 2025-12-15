import streamlit as st 
import pandas as pd
from datetime import date
import os
import json 
import time 
import plotly.express as px
import numpy as np 

# ===============================================
# 1. CONFIGURACIÓN Y BASES DE DATOS (MAESTRAS)
# ===============================================

DATA_FILE = 'atenciones_registradas.csv'
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
# 2. FUNCIONES DE PERSISTENCIA, CÁLCULO Y ESTILO
# ===============================================

def load_data():
    """Carga los datos del archivo CSV de forma segura."""
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce', format='%Y-%m-%d') 
        return df
    else:
        return pd.DataFrame(columns=[
            "Fecha", "Lugar", "Ítem", "Paciente", "Método Pago", 
            "Valor Bruto", "Desc. Fijo Lugar", "Desc. Tarjeta", 
            "Desc. Adicional", "Total Recibido"
        ])

def save_data(df):
    """Guarda el DataFrame actualizado en el archivo CSV."""
    df.to_csv(DATA_FILE, index=False)

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
    
    # 2.1. Revisar si existe una regla especial para el día
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
        'desc_fijo_lugar': int(desc_fijo_lugar),
        'desc_tarjeta': int(desc_tarjeta),
        'total_recibido': int(total_recibido)
    }

# --- Funciones de Reactividad y Reinicio ---

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
# --- NUEVA FUNCIÓN DE GUARDADO PARA EL MODO EDICIÓN (CLAVE DE LA SOLUCIÓN) ---

def save_edit_state_to_df():
    """
    Guarda el estado actual de los inputs de edición (st.session_state) 
    directamente en el DataFrame y en el archivo CSV.
    """
    if st.session_state.edit_index is None:
        return 0
        
    index_to_edit = st.session_state.edit_index
    
    # Se obtienen los valores de la sesión
    valor_bruto_final = st.session_state.edit_valor_bruto
    desc_adicional_final = st.session_state.edit_desc_adic
    
    # Se usan los valores de los botones de actualización si fueron presionados, 
    # si no, se usa el valor actual de la columna del DF (para no forzar un cambio si no se quiso)
    data_to_edit = st.session_state.atenciones_df.loc[index_to_edit]
    desc_fijo_final = st.session_state.get('original_desc_fijo_lugar', data_to_edit['Desc. Fijo Lugar'])
    desc_tarjeta_final = st.session_state.get('original_desc_tarjeta', data_to_edit['Desc. Tarjeta'])
    
    # 2. Recalcular el total líquido con los valores finales
    total_liquido_final = (
        valor_bruto_final
        - desc_fijo_final
        - desc_tarjeta_final
        - desc_adicional_final
    )
    
    # 3. Actualizar la fila en el DataFrame
    st.session_state.atenciones_df.loc[index_to_edit, "Fecha"] = st.session_state.edit_fecha.strftime('%Y-%m-%d')
    st.session_state.atenciones_df.loc[index_to_edit, "Lugar"] = st.session_state.edit_lugar
    st.session_state.atenciones_df.loc[index_to_edit, "Ítem"] = st.session_state.edit_item
    st.session_state.atenciones_df.loc[index_to_edit, "Paciente"] = st.session_state.edit_paciente
    st.session_state.atenciones_df.loc[index_to_edit, "Método Pago"] = st.session_state.edit_metodo
    
    st.session_state.atenciones_df.loc[index_to_edit, "Valor Bruto"] = valor_bruto_final
    st.session_state.atenciones_df.loc[index_to_edit, "Desc. Fijo Lugar"] = desc_fijo_final
    st.session_state.atenciones_df.loc[index_to_edit, "Desc. Tarjeta"] = desc_tarjeta_final
    st.session_state.atenciones_df.loc[index_to_edit, "Desc. Adicional"] = desc_adicional_final
    st.session_state.atenciones_df.loc[index_to_edit, "Total Recibido"] = total_liquido_final
    
    # 4. Guardar en el CSV
    save_data(st.session_state.atenciones_df)
    
    return total_liquido_final

# --------------------------------------------------------------------------


# --- FUNCIONES DE CALLBACK PARA LOS BOTONES DE ACTUALIZACIÓN EN EDICIÓN (SOLUCIÓN AL ERROR) ---

def update_edit_bruto_price():
    """Callback: Actualiza el Valor Bruto de la edición con el precio base actual, **guarda automáticamente** y notifica."""
    lugar_edit = st.session_state.edit_lugar.upper()
    item_edit = st.session_state.edit_item
    
    # 1. Obtener el nuevo precio base
    nuevo_precio_base = PRECIOS_BASE_CONFIG.get(lugar_edit, {}).get(item_edit, st.session_state.edit_valor_bruto)
    
    # 2. Actualizar el estado de sesión asociado al number_input
    st.session_state.edit_valor_bruto = int(nuevo_precio_base)
    
    # 3. Guardar en DF/CSV y obtener el nuevo total
    new_total = save_edit_state_to_df()
    
    st.success(f"Valor Bruto actualizado y guardado. Nuevo Tesoro Líquido: {format_currency(new_total)}")

def update_edit_desc_tarjeta():
    """Callback: Recalcula y actualiza el Desc. Tarjeta, **guarda automáticamente** y notifica."""
    comision_pct_actual = COMISIONES_PAGO.get(st.session_state.edit_metodo, 0.00)
    valor_bruto_actual = st.session_state.edit_valor_bruto
    nuevo_desc_tarjeta = int(valor_bruto_actual * comision_pct_actual)
    
    # 1. Actualizar el valor que se usará en el cálculo final al guardar
    st.session_state.original_desc_tarjeta = nuevo_desc_tarjeta
    
    # 2. Guardar en DF/CSV y obtener el nuevo total
    new_total = save_edit_state_to_df()
    
    st.success(f"Desc. Tarjeta actualizado y guardado. Nuevo Tesoro Líquido: {format_currency(new_total)}")

def update_edit_tributo():
    """Callback: Recalcula y actualiza el Tributo (Desc. Fijo Lugar), **guarda automáticamente** y notifica."""
    current_lugar_upper = st.session_state.edit_lugar 
    
    try:
        current_day_name = DIAS_SEMANA[st.session_state.edit_fecha.weekday()]
    except Exception:
        current_day_name = "LUNES" 
    
    # Lógica de cálculo del Tributo (se mantiene)
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
    
    # 2. Guardar en DF/CSV y obtener el nuevo total
    new_total = save_edit_state_to_df()
    
    st.success(f"Tributo actualizado y guardado. Nuevo Tesoro Líquido: {format_currency(new_total)}")

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
    
    # 3. Actualizar DataFrame y CSV
    df_actualizado = pd.concat([
        st.session_state.atenciones_df, 
        pd.DataFrame([nueva_atencion])
    ], ignore_index=True)
    
    st.session_state.atenciones_df = df_actualizado
    save_data(st.session_state.atenciones_df)
    
    # 4. Mensaje de éxito
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

st.title("🏰 Tesoro de Ingresos Fonoaudiológicos 💰")
st.markdown("✨ ¡Transforma cada atención en un diamante! ✨")

# --- Herramientas de Mantenimiento ---
if st.sidebar.button("🧹 Limpiar Cenicienta (Caché y Config)", type="secondary"):
    st.cache_data.clear() 
    st.cache_resource.clear() 
    
    re_load_global_config() 
    st.session_state.atenciones_df = load_data() 
    
    submit_and_reset() 
    
    st.success("Caché, Configuración y Datos Recargados. ¡La magia continúa!")
    st.rerun() 

st.sidebar.markdown("---") 

# Cargar los datos y asignarlos al estado de la sesión
if 'atenciones_df' not in st.session_state:
    st.session_state.atenciones_df = load_data()
    
if 'edit_index' not in st.session_state:
    st.session_state.edit_index = None 

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
                try:
                    current_day_name = DIAS_SEMANA[st.session_state.form_fecha.weekday()] 
                except Exception:
                    current_day_name = "N/A"
                    
                desc_lugar_label = f"Tributo al Castillo ({current_lugar_upper})"
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
        st.sidebar.header("🔍 Lupa Mágica (Filtros)")
        
        lugares_disponibles = ['Todos los Reinos'] + sorted(df['Lugar'].unique().tolist())
        filtro_lugar = st.sidebar.selectbox(
            "📍 Seleccionar Castillo/Reino", 
            options=lugares_disponibles
        )
        
        if filtro_lugar != 'Todos los Reinos':
            df_lugar = df[df['Lugar'] == filtro_lugar]
            items_disponibles = ['Todas las Pociones'] + sorted(df_lugar['Ítem'].unique().tolist())
        else:
            items_disponibles = ['Todas las Pociones'] + sorted(df['Ítem'].unique().tolist())
            
        filtro_item = st.sidebar.selectbox(
            "📋 Seleccionar Ítem/Poción", 
            options=items_disponibles
        )
        st.sidebar.markdown("---") 
        
        # APLICACIÓN DE FILTROS 
        df_filtrado_dashboard = df.copy()
        if filtro_lugar != 'Todos los Reinos':
            df_filtrado_dashboard = df_filtrado_dashboard[df_filtrado_dashboard['Lugar'] == filtro_lugar]
            
        if filtro_item != 'Todas las Pociones':
            df_filtrado_dashboard = df_filtrado_dashboard[df_filtrado_dashboard['Ítem'] == filtro_item]
        
        if df_filtrado_dashboard.empty:
            st.warning("No hay datos disponibles para la combinación mágica seleccionada.")
            st.stop()
            
        # LÓGICA DE VALIDACIÓN DE FECHAS SEGURA 
        df_valid_dates = df_filtrado_dashboard.dropna(subset=['Fecha'])

        if df_valid_dates.empty:
            min_date = date.today()
            max_date = date.today()
        else:
            min_date = df_valid_dates['Fecha'].min().date()
            max_date = df_valid_dates['Fecha'].max().date()

            if min_date.year < 2000:
                min_date = date.today()
                max_date = date.today()

        st.subheader("Tiempo de la Aventura")
        col_start, col_end = st.columns(2)
        
        fecha_default_inicio = min_date
        if min_date > max_date:
            fecha_default_inicio = max_date 
            
        fecha_inicio = col_start.date_input(
            "📅 Desde el Inicio del Cuento", 
            fecha_default_inicio, 
            min_value=min_date, 
            max_value=max_date,
            key="dashboard_fecha_inicio"
        )
        fecha_fin = col_end.date_input(
            "📅 Hasta el Final del Cuento", 
            max_date, 
            min_value=min_date, 
            max_value=max_date,
            key="dashboard_fecha_fin"
        )
        
        df_filtrado_dashboard = df_filtrado_dashboard.dropna(subset=['Fecha']) 
        
        df = df_filtrado_dashboard[
            (df_filtrado_dashboard['Fecha'].dt.date >= fecha_inicio) & 
            (df_filtrado_dashboard['Fecha'].dt.date <= fecha_fin)
        ]
        
        if df.empty:
            st.warning("No hay tesoros registrados en este periodo de tiempo.")
            st.stop()
            
        # ----------------------------------------------------
        # MÉTRICAS PRINCIPALES (KPIs)
        # ----------------------------------------------------
            
        st.markdown("### 🔑 Metas Clave")
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        
        total_liquido_historico = df["Total Recibido"].sum()
        col_kpi1.metric("💎 Tesoro Neto (Líquido)", format_currency(total_liquido_historico))
        
        total_bruto_historico = df["Valor Bruto"].sum()
        col_kpi2.metric("✨ Recompensa Bruta", format_currency(total_bruto_historico))
        
        total_atenciones_historico = len(df)
        col_kpi3.metric("👸 Total Héroes Atendidos", f"{total_atenciones_historico:,}".replace(",", "."))
        
        st.markdown("---")
        
        # ----------------------------------------------------
        # ANÁLISIS DE RENTABILIDAD Y COSTOS
        # ----------------------------------------------------
        st.header("⚖️ Análisis de Rentabilidad y Costos")

        df['Total Reducciones'] = df["Desc. Fijo Lugar"] + df["Desc. Tarjeta"] + df["Desc. Adicional"]
        total_cost_reductions = df['Total Reducciones'].sum()
        total_atenciones = len(df)
        avg_net_income = df["Total Recibido"].mean()
        
        col_r1, col_r2, col_r3 = st.columns(3)

        col_r1.metric(
            "💰 Total Descuentos/Costos Aplicados", 
            format_currency(total_cost_reductions),
        )

        col_r2.metric(
            "📊 Ingreso Neto Promedio por Atención", 
            format_currency(avg_net_income)
        )
        
        avg_cost_reduction = total_cost_reductions / total_atenciones if total_atenciones else 0
        col_r3.metric(
            "💔 Costo Promedio por Atención",
            format_currency(avg_cost_reduction)
        )
        
        st.markdown("---")

        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            st.subheader("💔 Desglose de Costos (Maleficios)")
            cost_summary = pd.DataFrame({
                'Tipo': ['Tributo Fijo al Lugar', 'Comisión Tarjeta', 'Ajuste Manual'],
                'Monto': [
                    df["Desc. Fijo Lugar"].sum(), 
                    df["Desc. Tarjeta"].sum(), 
                    df["Desc. Adicional"].sum()
                ]
            })

            fig_cost_breakdown = px.pie(
                cost_summary,
                values='Monto',
                names='Tipo',
                title='Distribución de las Reducciones Aplicadas',
                color_discrete_sequence=px.colors.qualitative.Dark24
            )
            fig_cost_breakdown.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
            st.plotly_chart(fig_cost_breakdown, use_container_width=True)

        with col_c2:
            st.subheader("📉 Evolución Mensual: Ingreso Neto vs. Costos")

            df['Mes_Año'] = df['Fecha'].dt.to_period('M').astype(str)
            df_monthly = df.groupby('Mes_Año').agg({
                'Total Recibido': 'sum',
                'Total Reducciones': 'sum'
            }).reset_index()

            df_monthly.columns = ['Mes_Año', 'Ingreso Neto Total', 'Costos Totales']

            fig_monthly_profitability = px.line(
                df_monthly,
                x='Mes_Año',
                y=['Ingreso Neto Total', 'Costos Totales'],
                title='Tendencia Mensual de Ingresos Netos y Costos',
                markers=True,
                color_discrete_map={
                    'Ingreso Neto Total': 'green',
                    'Costos Totales': 'red'
                }
            )
            fig_monthly_profitability.update_layout(yaxis_title="Monto ($)")
            st.plotly_chart(fig_monthly_profitability, use_container_width=True)
            
        st.markdown("---")

        # Análisis por Lugar (Plotly)
        st.subheader("🗺️ Mapa de Castillos (Distribución de Ingresos Netos)")
        resumen_lugar = df.groupby("Lugar")["Total Recibido"].sum().reset_index()
        
        fig_lugar = px.pie(
            resumen_lugar,
            values='Total Recibido',
            names='Lugar',
            title='Proporción de Tesoros Líquidos por Castillo',
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_lugar.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_lugar, use_container_width=True)

        # ----------------------------------------------------
        # GESTIÓN Y EXPORTACIÓN SIMPLE (VISTA DE TABLA)
        # ----------------------------------------------------
        st.header("📜 Libro de Registros (Gestión de Atenciones)")

        df_display = df.copy() 
        
        st.subheader("Atenciones Registradas (✏️ Editar, 🗑️ Eliminar)")

        # Títulos de columna con emojis (AJUSTADO PARA AÑADIR ITEM Y DESC. FIJO)
        cols_title = st.columns([0.1, 0.1, 0.15, 0.15, 0.15, 0.25, 0.05, 0.05])
        cols_title[0].write("**Fecha**")
        cols_title[1].write("**Lugar**")
        cols_title[2].write("📋 **Poción**") # NUEVA COLUMNA
        cols_title[3].write("💔 **Tributo**") # NUEVA COLUMNA
        cols_title[4].write("💎 **Líquido**")
        cols_title[5].write("👤 **Héroe**")
        cols_title[6].write("**E**") # Editar
        cols_title[7].write("**X**") # Eliminar
        
        st.markdown("---") 

        # Iterar sobre las filas y crear los botones
        for index, row in df_display.iterrows():
            
            # AJUSTADO PARA AÑADIR ITEM Y DESC. FIJO
            cols = st.columns([0.1, 0.1, 0.15, 0.15, 0.15, 0.25, 0.05, 0.05])
            
            cols[0].write(row['Fecha'].strftime('%Y-%m-%d'))
            cols[1].write(row['Lugar'])
            cols[2].write(row['Ítem']) # Mostrar Ítem/Poción
            cols[3].write(format_currency(row['Desc. Fijo Lugar'])) # Mostrar Tributo
            cols[4].write(format_currency(row['Total Recibido']))
            cols[5].write(row['Paciente'])
            
            # --- BOTÓN DE EDICIÓN ---
            if cols[6].button("✏️", key=f"edit_{index}", help="Editar esta aventura"):
                st.session_state.edit_index = index
                st.session_state.edited_lugar_state = row['Lugar'] 
                
                # Inicializar los valores de number_input en el state antes de abrir el modal
                st.session_state.edit_valor_bruto = int(row['Valor Bruto'])
                st.session_state.edit_desc_adic = int(row['Desc. Adicional'])
                
                # Inicializar el estado de la fila original para recalculos específicos
                st.session_state.original_desc_fijo_lugar = int(row['Desc. Fijo Lugar'])
                st.session_state.original_desc_tarjeta = int(row['Desc. Tarjeta'])

                st.rerun()

            # --- BOTÓN DE ELIMINACIÓN ---
            if cols[7].button("🗑️", key=f"delete_{index}", help="Eliminar esta aventura (¡Cuidado con la magia negra!)"):
                st.session_state.atenciones_df = st.session_state.atenciones_df.drop(index, axis=0).reset_index(drop=True)
                save_data(st.session_state.atenciones_df)
                st.success(f"Aventura de {row['Paciente']} eliminada. Recargando el Libro...")
                st.rerun()

        st.markdown("---") 
        
        # 🌟 EXPORTACIÓN FÁCIL DE USAR 
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ ¡Descargar el Mapa del Tesoro (CSV)! 🗺️",
            data=csv,
            file_name='reporte_tesoros_filtrado.csv',
            mime='text/csv',
            use_container_width=True, 
            type="primary"
        )
    else:
        st.info("Aún no hay aventuras. ¡Registra el primer tesoro para ver el mapa!")

    # ===============================================
    # 5. MODAL DE EDICIÓN DE REGISTRO
    # ===============================================

    if st.session_state.edit_index is not None:
        
        index_to_edit = st.session_state.edit_index
        
        try:
            data_to_edit = st.session_state.atenciones_df.loc[index_to_edit]
            
            if isinstance(data_to_edit['Fecha'], pd.Timestamp):
                initial_date = data_to_edit['Fecha'].date()
            else:
                initial_date = date.today()
                
        except KeyError:
            st.error("Error: El índice de la fila a editar no fue encontrado.")
            st.session_state.edit_index = None
            st.session_state.edited_lugar_state = None
            st.rerun()

        if 'edited_lugar_state' not in st.session_state or st.session_state.edited_lugar_state is None:
            st.session_state.edited_lugar_state = data_to_edit['Lugar']
            

        with st.expander(f"📝 Editar Aventura para {data_to_edit['Paciente']}", expanded=True):
            
            st.subheader("Modificar Datos de la Atención")
            
            
            col_edit1_out, col_edit2_out = st.columns(2)
            
            with col_edit1_out:
                edited_fecha = st.date_input("🗓️ Fecha de Atención", 
                                                 value=initial_date, 
                                                 key="edit_fecha",
                                                 on_change=force_recalculate 
                                                 )
                
                try:
                    lugar_idx = LUGARES.index(st.session_state.edited_lugar_state)
                except ValueError:
                    lugar_idx = 0
                
                edited_lugar_display = st.selectbox(
                    "📍 Castillo/Lugar de Atención", 
                    options=LUGARES, 
                    index=lugar_idx, 
                    key="edit_lugar", 
                    on_change=update_edit_price 
                )
                
                lugar_key_edit = st.session_state.edit_lugar 
                items_edit = list(PRECIOS_BASE_CONFIG.get(lugar_key_edit, {}).keys())
                
                # Ajustar el índice para el ítem de edición
                try:
                    current_item = st.session_state.get("edit_item", data_to_edit['Ítem']) 
                    current_item_index = items_edit.index(current_item)
                except ValueError:
                    current_item_index = 0
                
                item_key = "edit_item" 
                
                edited_item_display = st.selectbox(
                    "📋 Poción/Procedimiento", 
                    options=items_edit, 
                    index=current_item_index, 
                    key=item_key,
                    on_change=update_edit_price 
                )
                
                edited_paciente = st.text_input("👤 Héroe/Heroína (Paciente)", value=data_to_edit['Paciente'], key="edit_paciente")
                
                try:
                    pago_idx = METODOS_PAGO.index(data_to_edit['Método Pago'].upper())
                except ValueError:
                    pago_idx = 0
                edited_metodo_pago = st.radio("💳 Método de Pago Mágico", 
                                              options=METODOS_PAGO, 
                                              index=pago_idx, 
                                              key="edit_metodo",
                                              on_change=force_recalculate 
                                             )
            
            with col_edit2_out: 
                
                # VALOR BRUTO DE EDICIÓN 
                col_vb_input, col_vb_btn = st.columns([0.65, 0.35])
                
                with col_vb_input:
                    edited_valor_bruto = st.number_input(
                        "💰 **Valor Bruto (Recompensa)**", 
                        min_value=0, 
                        step=1000,
                        key="edit_valor_bruto" ,
                        on_change=force_recalculate 
                    )
                
                # --- BOTÓN DE RECALCULAR VALOR BRUTO (Ahora guarda automáticamente) ---
                with col_vb_btn:
                    st.button(
                        "🔄 Actualizar Base", 
                        key="btn_update_bruto", 
                        help="Actualizar el Valor Bruto con el precio actual de la configuración maestra y guardar.",
                        on_click=update_edit_bruto_price
                    )

                edited_desc_adicional_manual = st.number_input(
                    "✂️ **Polvo Mágico Extra (Ajuste)**", 
                    min_value=-500000, 
                    value=st.session_state.edit_desc_adic, 
                    step=1000, 
                    key="edit_desc_adic",
                    on_change=force_recalculate, 
                    help="Ingresa un valor positivo para descuentos (más magia) o negativo para cargos."
                )
                
                # Recalculo en tiempo real para la edición. 
                # El total debe reflejar los valores guardados en los estados `original_*` (si los botones fueron presionados)
                # o los valores originales del DF si no han sido presionados.
                
                data_to_edit_current = st.session_state.atenciones_df.loc[index_to_edit]
                
                desc_tarjeta_display = st.session_state.get('original_desc_tarjeta', data_to_edit_current['Desc. Tarjeta'])
                desc_fijo_display = st.session_state.get('original_desc_fijo_lugar', data_to_edit_current['Desc. Fijo Lugar'])
                
                st.markdown("---") 
                st.markdown("### 🛠️ Recalcular Reducciones")

                # --- DESCUENTO TARJETA Y BOTÓN DE ACTUALIZACIÓN (Ahora guarda automáticamente) ---
                col_tarjeta_text, col_tarjeta_btn = st.columns([0.65, 0.35])
                
                with col_tarjeta_text:
                    comision_pct_actual = COMISIONES_PAGO.get(st.session_state.edit_metodo, 0.00)
                    st.warning(f"**Desc. Tarjeta 🧙‍♀️ ({comision_pct_actual*100:.0f}% actual):** {format_currency(desc_tarjeta_display)}")
                
                with col_tarjeta_btn:
                    st.button(
                        "🔄 Recalcular Desc. Tarjeta", 
                        key="btn_update_tarjeta", 
                        help="Recalcula el descuento de tarjeta con la tasa de comisión actual, el Valor Bruto de la edición y guarda.",
                        on_click=update_edit_desc_tarjeta
                    )

                # --- TRIBUTO Y BOTÓN DE ACTUALIZACIÓN (Ahora guarda automáticamente) ---
                col_tributo_text, col_tributo_btn = st.columns([0.65, 0.35])
                
                # LÓGICA DE ETIQUETADO DEL TRIBUTO EN EDICIÓN
                current_lugar_upper = st.session_state.edit_lugar 
                current_day_name = DIAS_SEMANA[st.session_state.edit_fecha.weekday()]
                desc_lugar_label = f"Tributo al Castillo ({current_lugar_upper})"
                
                if current_lugar_upper in DESCUENTOS_REGLAS:
                    try:
                        regla_especial_monto = DESCUENTOS_REGLAS[current_lugar_upper].get(current_day_name.upper())
                        if regla_especial_monto is not None:
                            desc_lugar_label += f" (Regla: {current_day_name})"
                    except Exception:
                        pass
                elif DESCUENTOS_LUGAR.get(current_lugar_upper, 0) > 0:
                    desc_lugar_label += " (Base)"
                
                with col_tributo_text:
                    st.info(f"**{desc_lugar_label}:** {format_currency(desc_fijo_display)}")
                
                with col_tributo_btn:
                     st.button(
                        "🔄 Actualizar Tributo", 
                        key="btn_update_tributo", 
                        help="Actualiza el Tributo (Desc. Fijo Lugar) con la regla actual y guarda.",
                        on_click=update_edit_tributo
                    )

                st.markdown("---")
                
                # Cálculo del Total Líquido usando los valores que están en el estado
                total_liquido_display = (
                    st.session_state.edit_valor_bruto
                    - desc_fijo_display
                    - desc_tarjeta_display
                    - st.session_state.edit_desc_adic
                )
                
                st.success(
                    f"## 💎 Tesoro Total (Líquido): {format_currency(total_liquido_display)}"
                )

            # --- BOTONES DE ACCIÓN ---
            col_actions = st.columns([1, 1])
            
            # EL BOTÓN "GUARDAR EDICIÓN" AHORA SOLO CIERRA EL EXPANDER Y LIMPIA EL ESTADO
            if col_actions[0].button("💾 Guardar Edición", use_container_width=True, type="primary", key="save_edit"):
                
                st.session_state.edit_index = None
                st.session_state.edited_lugar_state = None
                
                # Limpiar estados de recalculo
                if 'original_desc_fijo_lugar' in st.session_state: del st.session_state.original_desc_fijo_lugar
                if 'original_desc_tarjeta' in st.session_state: del st.session_state.original_desc_tarjeta
                
                st.success("✅ Aventura editada y tesoro recalculado.") 
                st.rerun()

            if col_actions[1].button("❌ Cancelar Edición", use_container_width=True, key="cancel_edit"):
                st.session_state.edit_index = None
                st.session_state.edited_lugar_state = None
                
                # Limpiar estados de recalculo
                if 'original_desc_fijo_lugar' in st.session_state: del st.session_state.original_desc_fijo_lugar
                if 'original_desc_tarjeta' in st.session_state: del st.session_state.original_desc_tarjeta
                
                st.rerun()
                
with tab_config:
    # ===============================================
    # 6. CONFIGURACIÓN MAESTRA
    # ===============================================
    st.header("⚙️ Configuración Maestra del Tesoro")
    st.warning("🚨 ¡Precaución! Los cambios aquí afectan a los cálculos de registro de aventuras futuros.")
    
    # ----------------------------------------------------
    # 1. PRECIOS BASE (PRECIOS_BASE_CONFIG)
    # ----------------------------------------------------
    with st.expander("💰 Administrar Precios Base por Castillo/Lugar", expanded=True):
        st.subheader("Tabla de Precios Brutos Sugeridos")
        
        # Convierte el diccionario anidado a un DataFrame para edición
        data_for_df = []
        for lugar, items in PRECIOS_BASE_CONFIG.items():
            for item, precio in items.items():
                data_for_df.append({"Lugar": lugar, "Ítem": item, "Valor Bruto": sanitize_number_input(precio)})
        
        if data_for_df:
            df_precios = pd.DataFrame(data_for_df)
        else:
            df_precios = pd.DataFrame(columns=["Lugar", "Ítem", "Valor Bruto"])
            
        st.info("Utiliza la tabla para añadir, modificar o eliminar filas. Las columnas 'Lugar' e 'Ítem' son la clave.")
        
        edited_df_precios = st.data_editor(
            df_precios,
            num_rows="dynamic",
            column_config={
                "Valor Bruto": st.column_config.NumberColumn(
                    "Valor Bruto",
                    help="Precio sugerido para este Ítem en este Lugar.",
                    min_value=0,
                    step=1000,
                ),
                "Lugar": st.column_config.TextColumn("Lugar", required=True),
                "Ítem": st.column_config.TextColumn("Ítem", required=True)
            },
            key="precios_editor",
            use_container_width=True
        )

        if st.button("💾 Guardar Precios Base", type="primary", key="save_precios"):
            try:
                # Revertir el DataFrame a la estructura de diccionario anidado, SANITIZANDO EL VALOR
                new_precios_config = {}
                for _, row in edited_df_precios.iterrows():
                    lugar = str(row['Lugar']).upper() 
                    item = str(row['Ítem'])
                    valor = sanitize_number_input(row['Valor Bruto']) 
                    
                    if lugar and item and item != 'None':
                        if lugar not in new_precios_config:
                            new_precios_config[lugar] = {}
                        new_precios_config[lugar][item] = valor
                
                save_config(new_precios_config, PRECIOS_FILE)
                
                # FORZAR RECARGA DE CONFIGURACIÓN Y RERUN
                re_load_global_config() 
                st.success("✅ Precios base actualizados correctamente. **⚠️ Nota:** Los cambios de configuración solo aplican a las aventuras que se registren o editen a partir de este momento. Los registros históricos no se modifican.")
                time.sleep(4)
                st.rerun()
                
            except Exception as e:
                st.error(f"Error al guardar: Asegúrate de que los campos Lugar e Ítem no estén vacíos. Detalle: {e}")

    st.markdown("---")

    # ----------------------------------------------------
    # 2. DESCUENTOS FIJOS Y REGLAS POR LUGAR (DESCUENTOS_LUGAR, DESCUENTOS_REGLAS)
    # ----------------------------------------------------
    
    with st.expander("✂️ Administrar Descuentos Fijos y Reglas (Tributo al Castillo)"):
        st.subheader("Tributo Fijo al Castillo (Descuento Base)")

        df_descuentos_fijos = pd.DataFrame(
            list(DESCUENTOS_LUGAR.items()), 
            columns=["Lugar", "Desc. Fijo Base"]
        )

        edited_df_descuentos = st.data_editor(
            df_descuentos_fijos,
            num_rows="dynamic",
            column_config={
                "Desc. Fijo Base": st.column_config.NumberColumn(
                    "Tributo Base",
                    help="Monto fijo que se descuenta por defecto en este Lugar.",
                    min_value=0,
                    step=500,
                ),
                "Lugar": st.column_config.TextColumn("Lugar", required=True)
            },
            key="descuentos_editor",
            use_container_width=True
        )
        
        if st.button("💾 Guardar Descuentos Fijos", key="save_desc_fijos"):
            try:
                new_descuentos_config = {}
                for _, row in edited_df_descuentos.iterrows():
                    lugar = str(row['Lugar']).upper() 
                    valor = sanitize_number_input(row['Desc. Fijo Base']) 
                    if lugar:
                        new_descuentos_config[lugar] = valor
                
                save_config(new_descuentos_config, DESCUENTOS_FILE)
                
                # FORZAR RECARGA DE CONFIGURACIÓN Y RERUN
                re_load_global_config() 
                st.success("✅ Descuentos fijos actualizados correctamente. **⚠️ Nota:** Los cambios de configuración solo aplican a las aventuras que se registren o editen a partir de este momento. Los registros históricos no se modifican.")
                time.sleep(4)
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar descuentos fijos: {e}")
                
        # --- Reglas de Descuento por Día ---
        st.subheader("Reglas de Descuento por Día de la Semana")
        st.info("Define un monto de descuento diferente al base, solo para un día específico de la semana y un lugar.")
        
        # Transformar DESCUENTOS_REGLAS (anidado) a DataFrame plano
        reglas_plano = []
        for lugar, reglas in DESCUENTOS_REGLAS.items():
            for dia, monto in reglas.items():
                reglas_plano.append({"Lugar": lugar, "Día": dia, "Descuento Regla": monto})

        df_reglas = pd.DataFrame(reglas_plano)
        
        edited_df_reglas = st.data_editor(
            df_reglas,
            num_rows="dynamic",
            column_config={
                "Descuento Regla": st.column_config.NumberColumn(
                    "Monto Descuento Regla",
                    help="Monto que reemplaza al 'Desc. Fijo Base' si coincide el día y lugar.",
                    min_value=0,
                    step=500,
                ),
                "Lugar": st.column_config.TextColumn("Lugar", required=True),
                "Día": st.column_config.SelectboxColumn(
                    "Día", 
                    options=DIAS_SEMANA, 
                    required=True
                )
            },
            key="reglas_editor",
            use_container_width=True
        )

        if st.button("💾 Guardar Reglas por Día", key="save_reglas"):
            try:
                new_reglas_config = {}
                for _, row in edited_df_reglas.iterrows():
                    lugar = str(row['Lugar']).upper() 
                    dia = str(row['Día']).upper() 
                    monto = sanitize_number_input(row['Descuento Regla']) 
                    
                    if lugar and dia and dia in DIAS_SEMANA:
                        if lugar not in new_reglas_config:
                            new_reglas_config[lugar] = {}
                        new_reglas_config[lugar][dia] = monto
                        
                save_config(new_reglas_config, REGLAS_FILE)
                
                # FORZAR RECARGA DE CONFIGURACIÓN Y RERUN
                re_load_global_config() 
                st.success("✅ Reglas de descuento por día actualizadas. **⚠️ Nota:** Los cambios de configuración solo aplican a las aventuras que se registren o editen a partir de este momento. Los registros históricos no se modifican.")
                time.sleep(4)
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar reglas: {e}")


    st.markdown("---")

    # ----------------------------------------------------
    # 3. COMISIONES DE PAGO (COMISIONES_PAGO)
    # ----------------------------------------------------
    
    with st.expander("💳 Administrar Comisiones por Método de Pago"):
        st.subheader("Comisiones por Tarjeta y Otros Medios")

        df_comisiones = pd.DataFrame(
            list(COMISIONES_PAGO.items()), 
            columns=["Método de Pago", "Comisión (%)"]
        )
        
        edited_df_comisiones = st.data_editor(
            df_comisiones,
            num_rows="dynamic",
            column_config={
                "Comisión (%)": st.column_config.NumberColumn(
                    "Comisión (Ej: 0.03 para 3%)",
                    help="Factor de comisión aplicado al Valor Bruto (0.00 a 1.00).",
                    min_value=0.00,
                    max_value=1.00,
                    step=0.005,
                    format="%.3f"
                ),
                "Método de Pago": st.column_config.TextColumn("Método de Pago", required=True)
            },
            key="comisiones_editor",
            use_container_width=True
        )

        if st.button("💾 Guardar Comisiones de Pago", type="primary", key="save_comisiones"):
            try:
                new_comisiones_config = {}
                for _, row in edited_df_comisiones.iterrows():
                    metodo = str(row['Método de Pago']).upper() 
                    
                    # Usamos np.nan_to_num para asegurar que los NaN se traten como 0.0
                    comision = float(np.nan_to_num(row['Comisión (%)'])) 
                    
                    if metodo:
                        new_comisiones_config[metodo] = comision
                
                save_config(new_comisiones_config, COMISIONES_FILE)
                
                # FORZAR RECARGA DE CONFIGURACIÓN Y RERUN
                re_load_global_config() 
                st.success("✅ Comisiones de pago actualizadas correctamente. **⚠️ Nota:** Los cambios de configuración solo aplican a las aventuras que se registren o editen a partir de este momento. Los registros históricos no se modifican.")
                time.sleep(4)
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar comisiones: {e}")
