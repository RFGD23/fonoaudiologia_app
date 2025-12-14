import streamlit as st
import pandas as pd
from datetime import date
import os
import json 
import time 
import plotly.express as px

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
        st.warning(f"Archivo de configuración '{filename}' no encontrado. Creando uno por defecto.")
        
        # --- Configuración por defecto para inicialización ---
        if filename == PRECIOS_FILE:
            default_data = {'ALERCE': {'Item1': 30000, 'Item2': 40000}, 'AMAR AUSTRAL': {'ADIR+ADOS2': 30000}}
        elif filename == DESCUENTOS_FILE:
            default_data = {'ALERCE': 5000, 'AMAR AUSTRAL': 7000}
        elif filename == COMISIONES_FILE:
            default_data = {'EFECTIVO': 0.00, 'TRANSFERENCIA': 0.00, 'TARJETA': 0.03}
        elif filename == REGLAS_FILE:
            # Días en MAYÚSCULAS para coincidir con la lista DIAS_SEMANA
            default_data = {'AMAR AUSTRAL': {'LUNES': 0, 'MARTES': 8000, 'VIERNES': 6500}}
        else:
            default_data = {}
            
        save_config(default_data, filename)
        return default_data
    
    except json.JSONDecodeError as e:
        st.error(f"Error: El archivo {filename} tiene un formato JSON inválido. Revisa su contenido. Error: {e}")
        return {} 

# --- Cargar Variables Globales desde JSON ---
PRECIOS_BASE_CONFIG = load_config(PRECIOS_FILE)
DESCUENTOS_LUGAR = load_config(DESCUENTOS_FILE)
COMISIONES_PAGO = load_config(COMISIONES_FILE)
DESCUENTOS_REGLAS = load_config(REGLAS_FILE)


# Asegurarse de que las listas globales no estén vacías antes de usarlas
LUGARES = sorted(list(PRECIOS_BASE_CONFIG.keys())) if PRECIOS_BASE_CONFIG else []
METODOS_PAGO = list(COMISIONES_PAGO.keys()) if COMISIONES_PAGO else []
DIAS_SEMANA = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO', 'DOMINGO']


# ===============================================
# 2. FUNCIONES DE PERSISTENCIA, CÁLCULO Y ESTILO
# ===============================================

@st.cache_data
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
    
    # Manejo de casos límite si no hay configuración
    if not lugar or not item or not PRECIOS_BASE_CONFIG:
         return {
            'valor_bruto': 0,
            'desc_fijo_lugar': 0,
            'desc_tarjeta': 0,
            'total_recibido': 0
        }
    
    # El lugar (lugar_key) ya viene en MAYÚSCULAS desde el formulario de registro
    precio_base = PRECIOS_BASE_CONFIG.get(lugar, {}).get(item, 0)
    valor_bruto = valor_bruto_override if valor_bruto_override is not None else precio_base
    
    # --- LÓGICA DE DESCUENTO FIJO CONDICIONAL ---
    desc_fijo_lugar = DESCUENTOS_LUGAR.get(lugar, 0)
    
    if lugar in DESCUENTOS_REGLAS:
        # Asegurarse de que fecha_atencion es un objeto date o datetime
        if isinstance(fecha_atencion, pd.Timestamp):
            dia_semana_num = fecha_atencion.weekday()
        elif isinstance(fecha_atencion, date):
            dia_semana_num = fecha_atencion.weekday()
        else:
            # Si no es un formato válido, usamos la fecha de hoy
            dia_semana_num = date.today().weekday()
            
        # El nombre del día debe estar en MAYÚSCULAS para coincidir con el JSON
        dia_nombre = DIAS_SEMANA[dia_semana_num].upper()
        
        regla_especial = DESCUENTOS_REGLAS[lugar].get(dia_nombre)
        if regla_especial is not None:
            desc_fijo_lugar = regla_especial 

    # Aplicar Comisión de Tarjeta
    comision_pct = COMISIONES_PAGO.get(metodo_pago, 0.00)
    desc_tarjeta = valor_bruto * comision_pct
    
    # Cálculo final
    total_recibido = (
        valor_bruto 
        - desc_fijo_lugar 
        - desc_tarjeta 
        - desc_adicional_manual
    )
    
    return {
        'valor_bruto': valor_bruto,
        'desc_fijo_lugar': desc_fijo_lugar,
        'desc_tarjeta': desc_tarjeta,
        'total_recibido': total_recibido
    }

def update_edited_lugar():
    """Actualiza el lugar seleccionado en el modal de edición."""
    st.session_state.edited_lugar_state = st.session_state.edit_lugar

def set_dark_mode_theme():
    """Establece transparencia y ajusta la apariencia de los contenedores para el tema oscuro."""
    dark_mode_css = '''
    <style>
    .stApp, [data-testid="stAppViewBlock"], .main { background-color: transparent !important; background-image: none !important; }
    [data-testid="stSidebarContent"] { background-color: rgba(30, 30, 30, 0.9) !important; color: white; }
    .css-1r6dm1, .streamlit-expander, 
    [data-testid="stMetric"], [data-testid="stVerticalBlock"],
    .stSelectbox > div:first-child, .stDateInput > div:first-child, .stTextInput > div:first-child, .stNumberInput > div:first-child { 
        background-color: rgba(10, 10, 10, 0.6) !important; border-radius: 10px; padding: 10px;
    } 
    .stDataFrame, .stTable { background-color: rgba(0, 0, 0, 0.4) !important; }
    h1, h2, h3, h4, h5, h6, label, .css-1d391kg, [data-testid="stSidebarContent"] *, [data-testid="stHeader"] * { color: white !important; }
    .streamlit-expander label, div.stRadio > label { color: white !important; }
    </style>
    '''
    st.markdown(dark_mode_css, unsafe_allow_html=True)

def format_currency(value):
    """Función para formatear números como moneda en español con punto y coma."""
    return f"${value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
if st.sidebar.button("🧹 Limpiar Cenicienta (Caché)", type="secondary"):
    st.cache_data.clear() 
    st.cache_resource.clear() 
    st.success("Caché limpiada. ¡La magia continúa!")
    st.rerun() 

st.sidebar.markdown("---") 

# Cargar los datos y asignarlos al estado de la sesión
if 'atenciones_df' not in st.session_state:
    st.session_state.atenciones_df = load_data()
    
if 'edit_index' not in st.session_state:
    st.session_state.edit_index = None 

if 'edited_lugar_state' not in st.session_state:
    st.session_state.edited_lugar_state = None 

# --- Pestañas Principales ---
tab_registro, tab_dashboard, tab_config = st.tabs(["📝 Registrar Aventura", "📊 Mapa del Tesoro", "⚙️ Configuración Maestra"])

with tab_registro:
    # --- FORMULARIO DE INGRESO ---
    st.subheader("🎉 Nueva Aventura de Ingreso (Atención)")
    
    # Manejo de configuración vacía (para no fallar al acceder a LUGARES[0])
    if not LUGARES or not METODOS_PAGO:
        st.error("🚨 ¡Fallo de Configuración! La lista de Lugares o Métodos de Pago está vacía. Por favor, revisa la pestaña 'Configuración Maestra' para agregar datos iniciales.")
        # No se usa st.stop() aquí para permitir que el usuario navegue a Configuración.
    
    # --- LÓGICA DE INICIALIZACIÓN ROBUSTA DE SELECTBOXES (CORRECCIÓN CRÍTICA) ---
    lugar_key_initial = LUGARES[0] if LUGARES else ''
    
    # 1. Inicializar form_lugar si no existe
    if 'form_lugar' not in st.session_state:
        st.session_state.form_lugar = lugar_key_initial
        
    current_lugar_value = st.session_state.form_lugar
    current_lugar_value_upper = current_lugar_value.upper()
    
    # Obtener ítems disponibles para el lugar actual
    items_filtrados_initial = list(PRECIOS_BASE_CONFIG.get(current_lugar_value_upper, {}).keys())
    item_key_initial = items_filtrados_initial[0] if items_filtrados_initial else ''
    
    # 2. Inicializar form_item si no existe
    if 'form_item' not in st.session_state:
        st.session_state.form_item = item_key_initial
        
    
    with st.form("registro_atencion_form", clear_on_submit=True): 
        with st.expander("Detalles del Registro", expanded=True):
            
            if not LUGARES or not METODOS_PAGO or not items_filtrados_initial:
                st.warning("No se puede registrar sin Lugares, Ítems o Métodos de Pago. Configure la pestaña.")
                st.form_submit_button("Añadir datos antes de registrar", disabled=True)
                st.stop()


            col1, col2 = st.columns([1, 1])

            with col1:
                fecha = st.date_input("🗓️ Fecha de Atención", date.today(), key="form_fecha")
                
                # 1. SELECTBOX LUGAR
                try:
                    lugar_index = LUGARES.index(st.session_state.form_lugar)
                except ValueError:
                    lugar_index = 0

                lugar_seleccionado = st.selectbox("📍 Castillo/Lugar de Atención", 
                                                options=LUGARES, 
                                                key="form_lugar",
                                                index=lugar_index)
                
                # 2. SELECTBOX ÍTEM
                lugar_key_current = st.session_state.form_lugar.upper()
                items_filtrados_current = list(PRECIOS_BASE_CONFIG.get(lugar_key_current, {}).keys())
                
                # Sincronización del ítem seleccionado
                try:
                    # Si el ítem actual existe en la nueva lista de ítems del lugar, lo seleccionamos.
                    item_index = items_filtrados_current.index(st.session_state.form_item)
                except (ValueError, KeyError):
                    # Si no existe (porque cambiamos de lugar), seleccionamos el primer ítem de la nueva lista.
                    item_index = 0 
                    
                item_seleccionado = st.selectbox("📋 Poción/Procedimiento", 
                                                options=items_filtrados_current, 
                                                key="form_item",
                                                index=item_index)
                
                # --- CÁLCULO DE PRECIO SUGERIDO ---
                item_calc_for_price = st.session_state.form_item
                precio_base_sugerido = PRECIOS_BASE_CONFIG.get(lugar_key_current, {}).get(item_calc_for_price, 0)
                
                paciente = st.text_input("👤 Héroe/Heroína (Paciente/Asociado)", "", key="form_paciente")
                
                try:
                    pago_idx = METODOS_PAGO.index(st.session_state.get('form_metodo_pago', METODOS_PAGO[0]))
                except ValueError:
                    pago_idx = 0
                metodo_pago = st.radio("💳 Método de Pago Mágico", options=METODOS_PAGO, key="form_metodo_pago", index=pago_idx)

            with col2:
                
                # 3. VALOR BRUTO (Se actualiza con el precio sugerido al cambiar lugar/ítem)
                valor_bruto_input = st.number_input(
                    "💰 **Valor Bruto (Recompensa)**", 
                    min_value=0, 
                    value=int(precio_base_sugerido), 
                    step=1000,
                    key="form_valor_bruto" 
                )

                desc_adicional_manual = st.number_input(
                    "✂️ **Polvo Mágico Extra (Ajuste)**", 
                    min_value=-500000, 
                    value=st.session_state.get('form_desc_adic', 0), 
                    step=1000, 
                    key="form_desc_adic",
                    help="Ingresa un valor positivo para descuentos (más magia) o negativo para cargos."
                )
                
                # Ejecutar el cálculo central en tiempo real
                resultados = calcular_ingreso(
                    lugar_key_current, 
                    item_calc_for_price, 
                    st.session_state.form_metodo_pago,
                    st.session_state.form_desc_adic,  
                    fecha_atencion=st.session_state.form_fecha, 
                    valor_bruto_override=st.session_state.form_valor_bruto
                )

                st.warning(f"**Desc. Tarjeta 🧙‍♀️ ({COMISIONES_PAGO.get(st.session_state.form_metodo_pago, 0.00)*100:.0f}%):** {format_currency(resultados['desc_tarjeta'])}")
                
                desc_lugar_label = f"Tributo al Castillo ({st.session_state.form_lugar})"
                if st.session_state.form_lugar.upper() in DESCUENTOS_REGLAS:
                    dias_semana = {0: 'LUNES', 1: 'MARTES', 2: 'MIÉRCOLES', 3: 'JUEVES', 4: 'VIERNES', 5: 'SÁBADO', 6: 'DOMINGO'}
                    dia_atencion = dias_semana.get(st.session_state.form_fecha.weekday(), "DÍA")
                    desc_lugar_label += f" ({dia_atencion})" 

                st.info(f"**Tributo al Castillo ({st.session_state.form_lugar}):** {format_currency(resultados['desc_fijo_lugar'])}")
                
                st.markdown("###")
                st.success(
                    f"## 💎 Tesoro Total (Líquido): {format_currency(resultados['total_recibido'])}"
                )
                
            # --- BOTÓN DE ENVÍO DEL FORMULARIO ---
            submit_button = st.form_submit_button(
                "✅ ¡Guardar Aventura y Tesoro!", 
                use_container_width=True, 
                type="primary"
            )

            if submit_button:
                if st.session_state.form_paciente == "":
                    st.error("Por favor, ingresa el nombre del paciente.")
                else:
                    # 1. Recalculo final
                    resultados_finales = calcular_ingreso(
                        st.session_state.form_lugar.upper(), 
                        st.session_state.form_item, 
                        st.session_state.form_metodo_pago, 
                        st.session_state.form_desc_adic, 
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
                        "Desc. Adicional": st.session_state.form_desc_adic,
                        "Total Recibido": resultados_finales['total_recibido']
                    }
                    
                    # 3. Actualizar DataFrame y CSV
                    df_actualizado = pd.concat([
                        st.session_state.atenciones_df, 
                        pd.DataFrame([nueva_atencion])
                    ], ignore_index=True)
                    
                    st.session_state.atenciones_df = df_actualizado
                    save_data(st.session_state.atenciones_df)
                    st.success(f"🎉 ¡Aventura registrada para {st.session_state.form_paciente}! El tesoro es {format_currency(resultados_finales['total_recibido'])}")
                    
                    # 4. Forzar recarga para actualizar dashboard/listado de registros
                    st.rerun() 


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
            max_value=max_date
        )
        fecha_fin = col_end.date_input(
            "📅 Hasta el Final del Cuento", 
            max_date, 
            min_value=min_date, 
            max_value=max_date
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
        
        avg_cost_reduction = total_cost_reductions / total_atenciones
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

        # Títulos de columna con emojis
        cols_title = st.columns([0.15, 0.15, 0.15, 0.3, 0.1, 0.1])
        cols_title[0].write("**Fecha**")
        cols_title[1].write("**Lugar**")
        cols_title[2].write("**Líquido**")
        cols_title[3].write("**Héroe**")
        cols_title[4].write("**Editar**") 
        cols_title[5].write("**Eliminar**") 
        
        st.markdown("---") 

        # Iterar sobre las filas y crear los botones
        for index, row in df_display.iterrows():
            
            cols = st.columns([0.15, 0.15, 0.15, 0.3, 0.1, 0.1])
            
            cols[0].write(row['Fecha'].strftime('%Y-%m-%d'))
            cols[1].write(row['Lugar'])
            cols[2].write(format_currency(row['Total Recibido']))
            cols[3].write(row['Paciente'])
            
            # --- BOTÓN DE EDICIÓN ---
            if cols[4].button("✏️", key=f"edit_{index}", help="Editar esta aventura"):
                st.session_state.edit_index = index
                st.session_state.edited_lugar_state = row['Lugar'] 
                st.rerun()

            # --- BOTÓN DE ELIMINACIÓN ---
            if cols[5].button("🗑️", key=f"delete_{index}", help="Eliminar esta aventura (¡Cuidado con la magia negra!)"):
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
            
            # --- WIDGETS DE CAMBIO DE ESTADO FUERA DEL FORMULARIO ---
            with col_edit1_out:
                edited_fecha = st.date_input("🗓️ Fecha de Atención", 
                                            value=initial_date, 
                                            key="edit_fecha")
                
                try:
                    lugar_idx = LUGARES.index(st.session_state.edited_lugar_state)
                except ValueError:
                    lugar_idx = 0
                
                edited_lugar_display = st.selectbox(
                    "📍 Castillo/Lugar de Atención", 
                    options=LUGARES, 
                    index=lugar_idx, 
                    key="edit_lugar", 
                    on_change=update_edited_lugar 
                )
                
                lugar_key_edit = st.session_state.edit_lugar.upper()
                items_edit = list(PRECIOS_BASE_CONFIG.get(lugar_key_edit, {}).keys())
                
                try:
                    current_item_index = items_edit.index(data_to_edit['Ítem'])
                except ValueError:
                    current_item_index = 0
                
                item_key = "edit_item" 
                
                edited_item_display = st.selectbox(
                    "📋 Poción/Procedimiento", 
                    options=items_edit, 
                    index=current_item_index, 
                    key=item_key 
                )
                
                edited_paciente = st.text_input("👤 Héroe/Heroína (Paciente)", value=data_to_edit['Paciente'], key="edit_paciente")
                
                try:
                    pago_idx = METODOS_PAGO.index(data_to_edit['Método Pago'])
                except ValueError:
                    pago_idx = 0
                edited_metodo_pago = st.radio("💳 Método de Pago Mágico", options=METODOS_PAGO, index=pago_idx, key="edit_metodo")
            
            with col_edit2_out: 
                
                # --- MANEJO DEL VALOR BRUTO ---
                if 'edit_valor_bruto' not in st.session_state:
                    initial_valor_bruto = int(data_to_edit['Valor Bruto'])
                else:
                    initial_valor_bruto = st.session_state.edit_valor_bruto
                    
                edited_valor_bruto = st.number_input(
                    "💰 **Valor Bruto (Recompensa Manual)**", 
                    min_value=0, 
                    value=initial_valor_bruto, 
                    step=1000,
                    key="edit_valor_bruto"
                )
                
                edited_desc_adicional_manual = st.number_input(
                    "✂️ **Polvo Mágico Extra (Ajuste)**", 
                    min_value=-500000, 
                    value=int(data_to_edit['Desc. Adicional']), 
                    step=1000,
                    key="edit_desc_adic"
                )

                # CÁLCULO Y DISPLAY DE RESULTADOS EN TIEMPO REAL 
                recalculo = calcular_ingreso(
                    st.session_state.edit_lugar.upper(), 
                    st.session_state.edit_item, 
                    st.session_state.edit_metodo, 
                    st.session_state.edit_desc_adic, 
                    fecha_atencion=st.session_state.edit_fecha, 
                    valor_bruto_override=st.session_state.edit_valor_bruto 
                )

                st.warning(
                    f"**Desc. Tarjeta 🧙‍♀️ ({COMISIONES_PAGO.get(st.session_state.edit_metodo, 0.00)*100:.0f}%):** {format_currency(recalculo['desc_tarjeta'])}"
                )
                
                desc_lugar_label = f"Tributo al Castillo ({st.session_state.edit_lugar})"
                if st.session_state.edit_lugar.upper() in DESCUENTOS_REGLAS:
                    dias_semana = {0: 'LUNES', 1: 'MARTES', 2: 'MIÉRCOLES', 3: 'JUEVES', 4: 'VIERNES', 5: 'SÁBADO', 6: 'DOMINGO'}
                    desc_lugar_label += f" ({dias_semana.get(st.session_state.edit_fecha.weekday())})" 

                st.info(f"**{desc_lugar_label}:** {format_currency(recalculo['desc_fijo_lugar'])}")
                
                st.markdown("###")
                st.success(
                    f"## 💎 NUEVO TOTAL LÍQUIDO: {format_currency(recalculo['total_recibido'])}"
                )
            
            # 2. BOTONES DE ACCIÓN DENTRO DEL FORMULARIO DE EDICIÓN
            with st.form("edit_form", clear_on_submit=False):
                
                col_btn1, col_btn2 = st.columns([1, 1])
                
                submit_button = col_btn1.form_submit_button("💾 Guardar Cambios y Actualizar", type="primary")
                cancel_button = col_btn2.form_submit_button("❌ Cancelar Edición")


                if submit_button:
                    # Recalculamos con los valores del estado de sesión finales
                    recalculo_final = calcular_ingreso(
                        st.session_state.edit_lugar.upper(), 
                        st.session_state.edit_item, 
                        st.session_state.edit_metodo, 
                        st.session_state.edit_desc_adic, 
                        fecha_atencion=st.session_state.edit_fecha, 
                        valor_bruto_override=st.session_state.edit_valor_bruto 
                    )

                    st.session_state.atenciones_df.loc[index_to_edit] = {
                        "Fecha": st.session_state.edit_fecha.strftime('%Y-%m-%d'), 
                        "Lugar": st.session_state.edit_lugar, 
                        "Ítem": st.session_state.edit_item, 
                        "Paciente": st.session_state.edit_paciente, 
                        "Método Pago": st.session_state.edit_metodo,
                        "Valor Bruto": recalculo_final['valor_bruto'], 
                        "Desc. Fijo Lugar": recalculo_final['desc_fijo_lugar'], 
                        "Desc. Tarjeta": recalculo_final['desc_tarjeta'], 
                        "Desc. Adicional": st.session_state.edit_desc_adic,
                        "Total Recibido": recalculo_final['total_recibido'] 
                    }
                    
                    save_data(st.session_state.atenciones_df)
                    st.session_state.edit_index = None 
                    st.session_state.edited_lugar_state = None 
                    st.success(f"🎉 Aventura para {st.session_state.edit_paciente} actualizada exitosamente. Recargando el mapa...")
                    time.sleep(0.5) 
                    st.rerun()
                    
                if cancel_button:
                    st.session_state.edit_index = None 
                    st.session_state.edited_lugar_state = None 
                    st.rerun()

with tab_config:
    # ===============================================
    # 6. ADMINISTRACIÓN DE DATOS MAESTROS (JSON)
    # ===============================================
    st.header("⚙️ Configuración de Datos Maestros")
    st.markdown("⚠️ **¡Atención!** Esta sección modifica los precios base, descuentos y comisiones. Se requiere una clave de seguridad.")
    
    CLAVE_MAESTRA = "DOMI1702"
    
    clave_ingresada = st.text_input(
        "🔑 Ingrese la Clave Maestra para Guardar Cambios", 
        type="password", 
        key="admin_password"
    )
    
    tab_precios, tab_descuentos_fijos, tab_comisiones, tab_reglas = st.tabs([
        "💰 Precios Base/Ítems", 
        "📍 Descuentos Fijos por Lugar", 
        "💳 Comisiones por Pago",
        "📅 Reglas Condicionales" 
    ])

    with tab_precios:
        st.subheader("Editar Precios Base por Castillo/Lugar")

        if not PRECIOS_BASE_CONFIG:
            st.warning("No hay configuración de precios cargada. Intente recargar la aplicación o ingrese datos manualmente en el data_editor.")
            df_precios = pd.DataFrame(columns=['Castillo/Lugar', 'Poción/Ítem', 'Precio Base ($)'])
        else:
            data_for_edit = []
            for lugar, items in PRECIOS_BASE_CONFIG.items():
                for item, precio in items.items():
                    data_for_edit.append({'Castillo/Lugar': lugar, 'Poción/Ítem': item, 'Precio Base ($)': precio})
            
            df_precios = pd.DataFrame(data_for_edit)
        
        # Envuelto en un form para manejar el submit correctamente si se edita el data_editor
        with st.form("form_precios", clear_on_submit=False):
            edited_df = st.data_editor(
                df_precios,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Precio Base ($)": st.column_config.NumberColumn(
                        "Precio Base ($)",
                        help="Valor de la atención sin descuentos ni comisiones.",
                        format="$%d",
                        min_value=0,
                        step=1000
                    )
                },
                key="precios_data_editor"
            )
            submit_precios = st.form_submit_button("💾 Guardar Precios Actualizados", type="primary")

            if submit_precios:
                if clave_ingresada == CLAVE_MAESTRA:
                    try:
                        new_precios_config = {}
                        for index, row in edited_df.iterrows():
                            lugar = str(row['Castillo/Lugar']).upper() 
                            item = str(row['Poción/Ítem'])
                            precio = int(row['Precio Base ($)'])
                            
                            if lugar and item and precio >= 0: 
                                if lugar not in new_precios_config:
                                    new_precios_config[lugar] = {}
                                new_precios_config[lugar][item] = precio

                        save_config(new_precios_config, PRECIOS_FILE)
                        st.success("✅ Precios y Castillos/Lugares actualizados correctamente.")
                        st.cache_data.clear() 
                        time.sleep(1)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error al guardar los precios: {e}")
                else:
                    st.error("❌ Clave de seguridad incorrecta. No se guardaron los cambios.")


    with tab_descuentos_fijos:
        st.subheader("Editar Descuentos Fijos por Castillo/Lugar (Aplicación Constante)")
        
        if not DESCUENTOS_LUGAR:
             df_descuentos = pd.DataFrame(columns=['Castillo/Lugar', 'Desc. Fijo ($)'])
        else:
            df_descuentos = pd.DataFrame(
                {'Castillo/Lugar': DESCUENTOS_LUGAR.keys(), 
                 'Desc. Fijo ($)': DESCUENTOS_LUGAR.values()}
            )
        
        with st.form("form_descuentos", clear_on_submit=False):
            edited_df_desc = st.data_editor(
                df_descuentos,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Desc. Fijo ($)": st.column_config.NumberColumn(
                        "Descuento Fijo ($)",
                        help="Descuento fijo aplicado antes de comisiones (Solo se usa si no hay regla condicional).",
                        format="$%d",
                        min_value=0,
                        step=1000
                    )
                },
                key="descuentos_data_editor"
            )
            submit_descuentos = st.form_submit_button("💾 Guardar Descuentos Fijos", type="primary")

            if submit_descuentos:
                if clave_ingresada == CLAVE_MAESTRA:
                    try:
                        new_descuentos_config = {}
                        for index, row in edited_df_desc.iterrows():
                            lugar = str(row['Castillo/Lugar']).upper()
                            descuento = int(row['Desc. Fijo ($)'])
                            
                            if lugar and descuento >= 0:
                                new_descuentos_config[lugar] = descuento
                        
                        save_config(new_descuentos_config, DESCUENTOS_FILE)
                        st.success("✅ Descuentos fijos por lugar actualizados correctamente.")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error al guardar los descuentos: {e}")
                else:
                    st.error("❌ Clave de seguridad incorrecta. No se guardaron los cambios.")

    with tab_comisiones:
        st.subheader("Editar Comisiones por Método de Pago")
        
        if not COMISIONES_PAGO:
             df_comisiones = pd.DataFrame(columns=['Método de Pago', 'Comisión (%)'])
        else:
            df_comisiones = pd.DataFrame(
                {'Método de Pago': COMISIONES_PAGO.keys(), 
                 'Comisión (%)': [v * 100 for v in COMISIONES_PAGO.values()]}
            )

        with st.form("form_comisiones", clear_on_submit=False):
            edited_df_com = st.data_editor(
                df_comisiones,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Comisión (%)": st.column_config.NumberColumn(
                        "Comisión (%)",
                        help="Porcentaje de comisión a aplicar (ej: 3 para 3%).",
                        format="%.2f%%",
                        min_value=0.00,
                        step=0.01
                    )
                },
                key="comisiones_data_editor"
            )
            submit_comisiones = st.form_submit_button("💾 Guardar Comisiones de Pago", type="primary")
        
            if submit_comisiones:
                if clave_ingresada == CLAVE_MAESTRA:
                    try:
                        new_comisiones_config = {}
                        for index, row in edited_df_com.iterrows():
                            metodo = str(row['Método de Pago']).upper()
                            comision_pct = float(row['Comisión (%)']) / 100.0
                            
                            if metodo and comision_pct >= 0:
                                new_comisiones_config[metodo] = comision_pct
                        
                        save_config(new_comisiones_config, COMISIONES_FILE)
                        st.success("✅ Comisiones por método de pago actualizadas correctamente.")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error al guardar las comisiones: {e}")
                else:
                    st.error("❌ Clave de seguridad incorrecta. No se guardaron los cambios.")

    with tab_reglas:
        st.subheader("📅 Descuentos Condicionales por Día de la Semana")
        st.info("Aquí se definen descuentos específicos por día que **SOBRESCRIBEN** el Descuento Fijo del Lugar. Use 0 para mantener el descuento fijo normal del lugar.")
        
        if not LUGARES:
            df_reglas = pd.DataFrame(columns=['Castillo/Lugar', 'Día de la Semana', 'Desc. Condicional ($)'])
            st.warning("No hay lugares configurados para definir reglas condicionales.")
        else:
            data_reglas = []
            for lugar in LUGARES: 
                reglas_lugar = DESCUENTOS_REGLAS.get(lugar.upper(), {})
                for dia in DIAS_SEMANA:
                    data_reglas.append({
                        'Castillo/Lugar': lugar,
                        'Día de la Semana': dia,
                        'Desc. Condicional ($)': reglas_lugar.get(dia, 0)
                    })
                    
            df_reglas = pd.DataFrame(data_reglas)
        
        with st.form("form_reglas", clear_on_submit=False):
            edited_df_reglas = st.data_editor(
                df_reglas,
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "Desc. Condicional ($)": st.column_config.NumberColumn(
                        "Descuento Condicional ($)",
                        help="Descuento aplicado ÚNICAMENTE si la fecha de atención coincide con el día.",
                        format="$%d",
                        min_value=0,
                        step=1000
                    ),
                    "Castillo/Lugar": st.column_config.TextColumn(disabled=True),
                    "Día de la Semana": st.column_config.TextColumn(disabled=True),
                },
                key="reglas_data_editor"
            )
            submit_reglas = st.form_submit_button("💾 Guardar Reglas Condicionales", type="primary")
        
            if submit_reglas:
                if clave_ingresada == CLAVE_MAESTRA:
                    try:
                        new_reglas_config = {}
                        
                        for index, row in edited_df_reglas.iterrows():
                            lugar = str(row['Castillo/Lugar']).upper()
                            dia = str(row['Día de la Semana']).upper()
                            descuento = int(row['Desc. Condicional ($)'])
                            
                            if lugar and dia and descuento >= 0:
                                if lugar not in new_reglas_config:
                                    new_reglas_config[lugar] = {}
                                new_reglas_config[lugar][dia] = descuento
                                
                        save_config(new_reglas_config, REGLAS_FILE)
                        st.success("✅ Reglas condicionales por día actualizadas correctamente.")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error al guardar las reglas: {e}")
                else:
                    st.error("❌ Clave de seguridad incorrecta. No se guardaron los cambios.")
