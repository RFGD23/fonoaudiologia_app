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
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
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
        st.info(f"Archivo de configuración '{filename}' no encontrado. Creando uno por defecto.")
        
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
            default_data = {'AMAR AUSTRAL': {'LUNES': 0, 'MARTES': 8000, 'VIERNES': 6500}} 
        else:
            default_data = {}
            
        save_config(default_data, filename)
        return default_data
    
    except json.JSONDecodeError as e:
        st.error(f"Error: El archivo {filename} tiene un formato JSON inválido. Revisa su contenido. Detalle: {e}")
        return {} 

# --- Cargar Variables Globales desde JSON ---

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
        reglas_upper = {dia.upper(): monto for dia, monto in reglas.items()}
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
    """
    Callback llamado cuando 'form_lugar' o 'form_item' cambia.
    Actualiza st.session_state (y fuerza un rerun porque actualiza el estado).
    """
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
    
    # Al modificar estos valores, Streamlit forzará un rerun automáticamente
    st.session_state.form_valor_bruto = int(precio_base_sugerido)
    
def force_recalculate():
    """
    Función de callback simple para asegurar que el estado de la sesión
    se ha actualizado. Usado en widgets reactivos fuera de st.form.
    """
    pass

def update_edit_price():
    """
    Callback llamado cuando 'edit_lugar' o 'edit_item' cambia en el modal de edición.
    Actualiza st.session_state sin necesidad de st.rerun().
    """
    lugar_key_edit = st.session_state.get('edit_lugar', '').upper()
    item_key_edit = st.session_state.get('edit_item', '')
    
    if not lugar_key_edit or not item_key_edit:
        st.session_state.edit_valor_bruto = 0
        return
        
    precio_base_sugerido_edit = PRECIOS_BASE_CONFIG.get(lugar_key_edit, {}).get(item_key_edit, 0)
    
    st.session_state.edit_valor_bruto = int(precio_base_sugerido_edit)

def reset_reactive_widgets():
    """
    🚨 CORRECCIÓN CLAVE: Resetea los widgets REACTIVOS (fuera del form) 
    a sus valores iniciales usando on_click del submit button.
    """
    
    # Obtener el primer ítem disponible para el lugar por defecto
    default_lugar = LUGARES[0] if LUGARES else ''
    items_default = list(PRECIOS_BASE_CONFIG.get(default_lugar, {}).keys())
    default_item = items_default[0] if items_default else ''
    
    # Calcular el valor bruto inicial después del reinicio
    default_valor_bruto = int(PRECIOS_BASE_CONFIG.get(default_lugar, {}).get(default_item, 0))

    # Resetear el estado de sesión de los inputs FUERA del form
    if LUGARES: st.session_state.form_lugar = default_lugar
    st.session_state.form_item = default_item
    st.session_state.form_valor_bruto = default_valor_bruto
    st.session_state.form_desc_adic_input = 0
    st.session_state.form_fecha = date.today()
    if METODOS_PAGO: st.session_state.form_metodo_pago = METODOS_PAGO[0]
    
    # Limpiar el campo Paciente, que es el único que queda DENTRO del form 
    # y que Streamlit no limpia porque usamos su propia key.
    # NOTA: En este caso, el `clear_on_submit=True` debería limpiar el `form_paciente` 
    # ya que no tiene una key explícita, pero lo incluimos por si acaso.
    # Ya que el input del paciente tiene una key:
    if 'form_paciente' in st.session_state:
        st.session_state.form_paciente = ''
    
    # El st.rerun se hace automáticamente después de este callback.

def format_currency(value):
    """Función para formatear números como moneda en español con punto y coma."""
    if value is None or not isinstance(value, (int, float)):
         value = 0
    return f"${int(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")

def sanitize_number_input(value):
    """Convierte un valor de input de tabla (que puede ser NaN o string) a int."""
    if pd.isna(value) or value is None:
        return 0
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0 

# ( ... Funciones de estilo set_dark_mode_theme ... ) # (Omitido por brevedad en la corrección)

# ===============================================
# 3. INTERFAZ DE USUARIO (FRONTEND)
# ===============================================

# 🚀 Configuración de la Página y Título
st.set_page_config(
    page_title="🏰 Control de Ingresos Mágicos 🪄", 
    layout="wide"
)

# set_dark_mode_theme() # Se mantiene en el código original

st.title("🏰 Tesoro de Ingresos Fonoaudiológicos 💰")
st.markdown("✨ ¡Transforma cada atención en un diamante! ✨")

# --- Herramientas de Mantenimiento ---
if st.sidebar.button("🧹 Limpiar Cenicienta (Caché y Config)", type="secondary"):
    st.cache_data.clear() 
    st.cache_resource.clear() 
    
    re_load_global_config() 
    st.session_state.atenciones_df = load_data() 
    
    # Usar la función de reinicio general aquí también
    reset_reactive_widgets() 
    
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
    
    if not LUGARES or not METODOS_PAGO:
        st.error("🚨 ¡Fallo de Configuración! La lista de Lugares o Métodos de Pago está vacía. Por favor, revisa la pestaña 'Configuración Maestra' para agregar datos iniciales.")
    
    # 1. Definir valores iniciales y forzar la inicialización si faltan
    
    # Intenta inicializar el lugar con el primero disponible
    lugar_key_initial = LUGARES[0] if LUGARES else ''
    if 'form_lugar' not in st.session_state:
        st.session_state.form_lugar = lugar_key_initial
    
    current_lugar_value_upper = st.session_state.form_lugar 
    items_filtrados_initial = list(PRECIOS_BASE_CONFIG.get(current_lugar_value_upper, {}).keys())
    
    # Intenta inicializar el ítem
    item_key_initial = items_filtrados_initial[0] if items_filtrados_initial else ''
    if 'form_item' not in st.session_state or st.session_state.form_item not in items_filtrados_initial:
        st.session_state.form_item = item_key_initial
    
    # 2. Calcular el valor bruto inicial basado en los valores de arriba
    precio_base_sugerido = PRECIOS_BASE_CONFIG.get(current_lugar_value_upper, {}).get(st.session_state.form_item, 0)
    
    if 'form_valor_bruto' not in st.session_state:
        st.session_state.form_valor_bruto = int(precio_base_sugerido)
        
    if 'form_desc_adic_input' not in st.session_state:
        st.session_state.form_desc_adic_input = 0

    if 'form_fecha' not in st.session_state:
        st.session_state.form_fecha = date.today()

    if 'form_metodo_pago' not in st.session_state:
        st.session_state.form_metodo_pago = METODOS_PAGO[0] if METODOS_PAGO else ''

    # ----------------------------------------------------------------------
    # WIDGETS REACTIVOS FUERA DEL FORMULARIO 
    # ----------------------------------------------------------------------
    # ( ... Los widgets de Lugar, Ítem, Valor Bruto y Descuento Adicional se mantienen fuera ... )
    col_reactivo_1, col_reactivo_2, col_reactivo_3, col_reactivo_4 = st.columns(4)

    # 1. SELECTBOX LUGAR
    with col_reactivo_1:
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
    with col_reactivo_2:
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
    with col_reactivo_3:
        st.number_input(
            "💰 **Valor Bruto (Recompensa)**", 
            min_value=0, 
            step=1000,
            key="form_valor_bruto", 
            on_change=force_recalculate 
        )

    # 4. DESCUENTO ADICIONAL (FUERA DEL FORMULARIO)
    with col_reactivo_4:
        st.number_input(
            "✂️ **Polvo Mágico Extra (Ajuste)**", 
            min_value=-500000, 
            value=st.session_state.get('form_desc_adic_input', 0), 
            step=1000, 
            key="form_desc_adic_input",
            on_change=force_recalculate, 
            help="Ingresa un valor positivo para descuentos (más magia) o negativo para cargos."
        )

    st.markdown("---") # Separador visual

    col_fecha, col_pago = st.columns([1, 1])

    with col_fecha:
        # FECHA DE ATENCIÓN (FUERA DEL FORMULARIO)
        fecha = st.date_input(
            "🗓️ Fecha de Atención", 
            st.session_state.form_fecha, 
            key="form_fecha_reactive", 
            on_change=force_recalculate 
        ) 
        st.session_state.form_fecha = fecha


    with col_pago:
        try:
            pago_idx = METODOS_PAGO.index(st.session_state.get('form_metodo_pago', METODOS_PAGO[0]))
        except ValueError:
            pago_idx = 0
            
        # MÉTODO DE PAGO (FUERA DEL FORMULARIO)
        metodo_pago = st.radio(
            "💳 Método de Pago Mágico", 
            options=METODOS_PAGO, 
            key="form_metodo_pago_reactive", 
            index=pago_idx,
            on_change=force_recalculate 
        )
        st.session_state.form_metodo_pago = metodo_pago

    st.markdown("---") # Separador visual

    # ----------------------------------------------------------------------
    # FORMULARIO PARA DATOS RESTANTES Y BOTÓN DE ENVÍO
    # ----------------------------------------------------------------------
    
    with st.form("registro_atencion_form", clear_on_submit=True): 
        
        # Paciente (el único widget dentro del form con input)
        paciente = st.text_input("👤 Héroe/Heroína (Paciente/Asociado)", "", key="form_paciente")
        
        with st.expander("Detalles Adicionales y Cálculo Final", expanded=True):
            
            if not LUGARES or not items_filtrados_initial:
                st.info("Configuración de Lugar/Ítem incompleta. Revisa la pestaña de Configuración.")
            else:
                
                # Obtener valores reactivos del session_state para el cálculo
                desc_adicional_calc = st.session_state.form_desc_adic_input 
                valor_bruto_calc = st.session_state.form_valor_bruto
                
                # Ejecutar el cálculo central en tiempo real. 
                resultados = calcular_ingreso(
                    st.session_state.form_lugar, 
                    st.session_state.form_item,              
                    st.session_state.form_metodo_pago, 
                    desc_adicional_calc,
                    fecha_atencion=st.session_state.form_fecha, 
                    valor_bruto_override=valor_bruto_calc 
                )

                st.warning(f"**Desc. Tarjeta 🧙‍♀️ ({COMISIONES_PAGO.get(st.session_state.form_metodo_pago, 0.00)*100:.0f}%):** {format_currency(resultados['desc_tarjeta'])}")
                
                # --- LÓGICA DE ETIQUETADO DEL TRIBUTO ---
                # ( ... esta lógica se mantiene igual ... )
                current_lugar_upper = st.session_state.form_lugar 
                
                try:
                    current_day_name = DIAS_SEMANA[st.session_state.form_fecha.weekday()] 
                except Exception:
                    current_day_name = "N/A"
                    
                desc_lugar_label = f"Tributo al Castillo ({current_lugar_upper})"
                is_rule_applied = False
                if current_lugar_upper in DESCUENTOS_REGLAS:
                    try: 
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
                
        # --- BOTÓN DE ENVÍO DEL FORMULARIO ---
        submit_button = st.form_submit_button(
            "✅ ¡Guardar Aventura y Tesoro!", 
            use_container_width=True, 
            type="primary",
            # 🚨 CORRECCIÓN CLAVE: Usar on_click para resetear los inputs reactivos 
            # ANTES del rerun de submit.
            on_click=reset_reactive_widgets 
        )

        if submit_button:
            if st.session_state.form_paciente == "":
                st.error("Por favor, ingresa el nombre del paciente.")
                # No se llama a rerun aquí, porque el on_click ya lo hizo.
            else:
                # 1. Recalculo final 
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
                    "Paciente": st.session_state.form_paciente, 
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
                st.success(f"🎉 ¡Aventura registrada para {nueva_atencion['Paciente']}! El tesoro es {format_currency(resultados_finales['total_recibido'])}")
                
                # 4. 🚨 ELIMINAR CÓDIGO PROBLEMÁTICO: Ya no necesitamos el código de reinicio manual aquí
                # El reset_reactive_widgets() se encarga de esto via on_click.

                # st.rerun() # Ya no es necesario, el on_click lo fuerza.

# ( ... El resto de las pestañas Dashboard y Configuración se mantienen igual ... )
