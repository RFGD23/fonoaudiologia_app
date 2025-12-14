import streamlit as st
import pandas as pd
from datetime import date
import os
import json 
import time 
import base64 
import plotly.express as px

# ===============================================
# 1. CONFIGURACIÓN Y BASES DE DATOS (MAESTRAS)
# ===============================================

DATA_FILE = 'atenciones_registradas.csv'

def load_config(filename):
    """Carga la configuración desde un archivo JSON."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {} 
    except json.JSONDecodeError:
        return {}

# --- Cargar Variables Globales desde JSON ---
try:
    PRECIOS_BASE_CONFIG = load_config('precios_base.json')
    DESCUENTOS_LUGAR = load_config('descuentos_lugar.json')
    COMISIONES_PAGO = load_config('comisiones_pago.json')
except:
    # Fallback si no existen los archivos JSON o hay error
    PRECIOS_BASE_CONFIG = {'ALERCE': {'Item1': 30000, 'Item2': 40000}, 'AMAR AUSTRAL': {'ItemA': 25000, 'ItemB': 35000}}
    DESCUENTOS_LUGAR = {'ALERCE': 5000, 'AMAR AUSTRAL': 7000}
    COMISIONES_PAGO = {'EFECTIVO': 0.00, 'TRANSFERENCIA': 0.00, 'TARJETA': 0.03}


LUGARES = sorted(list(PRECIOS_BASE_CONFIG.keys()))
METODOS_PAGO = list(COMISIONES_PAGO.keys())


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
    
    if not lugar or not item:
         return {
            'valor_bruto': 0,
            'desc_fijo_lugar': 0,
            'desc_tarjeta': 0,
            'total_recibido': 0
        }
    
    precio_base = PRECIOS_BASE_CONFIG.get(lugar, {}).get(item, 0)
    valor_bruto = valor_bruto_override if valor_bruto_override is not None else precio_base
    desc_fijo_lugar = DESCUENTOS_LUGAR.get(lugar, 0)
    
    # LÓGICA CONDICIONAL: AMAR AUSTRAL (Martes/Viernes)
    if lugar == 'AMAR AUSTRAL':
        if isinstance(fecha_atencion, pd.Timestamp):
            dia_semana = fecha_atencion.weekday()
        elif isinstance(fecha_atencion, date):
            dia_semana = fecha_atencion.weekday()
        else:
            dia_semana = date.today().weekday()
            
        if dia_semana == 1:  # Martes
            desc_fijo_lugar = 8000
        elif dia_semana == 4:  # Viernes
            desc_fijo_lugar = 6500

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
    """Actualiza el lugar seleccionado inmediatamente."""
    st.session_state.edited_lugar_state = st.session_state.edit_lugar

# ❌ ELIMINAMOS get_base64_of_file y set_background

# --- FUNCIONES PARA FONDO SÓLIDO (BLANCO) ---
def set_solid_white_theme():
    """Establece un fondo blanco puro y ajusta la apariencia de los contenedores."""
    # Nota: El tema principal ya está en "light" en st.set_page_config

    solid_white_css = '''
    <style>
    /* 1. Fondo Blanco Puro en el Contenedor Raíz */
    /* stApp: Contenedor principal de Streamlit */
    .stApp, [data-testid="stAppViewBlock"], .main {
        background-color: #FFFFFF !important; /* Blanco puro */
        background-image: none !important; /* Elimina cualquier rastro del fondo de imagen anterior */
    }
    
    /* 2. Barra Lateral (Sidebar) - Fondo Claro */
    [data-testid="stSidebarContent"] {
        background-color: #F8F8F8 !important; /* Gris muy claro para diferenciar */
        color: black;
    }

    /* 3. Bloques de Contenido (Forms, Expander, Metrics) */
    /* Hacemos los contenedores ligeramente más oscuros para que resalten sobre el blanco */
    .css-1r6dm1, .streamlit-expander, 
    [data-testid="stMetric"], [data-testid="stVerticalBlock"],
    .stSelectbox > div:first-child, .stDateInput > div:first-child, .stTextInput > div:first-child, .stNumberInput > div:first-child { 
        background-color: #F0F0F0 !important; /* Gris claro suave */
        border-radius: 10px;
        padding: 10px;
    } 

    /* 4. Tablas y Dataframes */
    .stDataFrame, .stTable {
        background-color: #EAEAEA !important; /* Gris ligeramente más oscuro para las tablas */
    }
    
    /* 5. Asegurar que el texto sea oscuro sobre el fondo claro */
    h1, h2, h3, h4, h5, h6, label, .css-1d391kg, [data-testid="stSidebarContent"] * { /* Aplicamos color oscuro a todos los textos */
        color: #333333 !important;
    }

    /* 6. Ajuste para que las tablas dentro de la sidebar sean visibles */
    [data-testid="stSidebarContent"] .stDataFrame, [data-testid="stSidebarContent"] .stTable {
        background-color: #E0E0E0 !important;
    }
    
    </style>
    '''
    st.markdown(solid_white_css, unsafe_allow_html=True)


# ===============================================
# 3. INTERFAZ DE USUARIO (FRONTEND) - ESTILO LÚDICO
# ===============================================

# 🚀 Configuración de la Página y Título
st.set_page_config(
    page_title="🏰 Control de Ingresos Mágicos 🪄", 
    layout="wide",
    # ➡️ CONFIGURACIÓN A TEMA CLARO
    theme="light" 
)

# ➡️ EJECUTAR LA FUNCIÓN DEL TEMA CLARO AQUÍ:
set_solid_white_theme()

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

# --- FORMULARIO DE INGRESO ---
with st.expander("➕ 🎉 Nueva Aventura de Ingreso (Atención)", expanded=True):
    col1, col2 = st.columns([1, 1])

    with col1:
        fecha = st.date_input("🗓️ Fecha de Atención", date.today())
        lugar_seleccionado = st.selectbox("📍 Castillo/Lugar de Atención", options=LUGARES, key="new_lugar")
        
        items_filtrados = list(PRECIOS_BASE_CONFIG.get(lugar_seleccionado, {}).keys())
        item_seleccionado = st.selectbox("📋 Poción/Procedimiento", options=items_filtrados, key="new_item")
        
        paciente = st.text_input("👤 Héroe/Heroína (Paciente/Asociado)", "")
        metodo_pago = st.radio("💳 Método de Pago Mágico", options=METODOS_PAGO, key="new_metodo_pago")

    with col2:
        precio_base = PRECIOS_BASE_CONFIG.get(lugar_seleccionado, {}).get(item_seleccionado, 0)
        
        valor_bruto_input = st.number_input(
            "💰 **Valor Bruto (Recompensa)**", 
            min_value=0, 
            value=int(precio_base), 
            step=1000,
            key="new_valor_bruto"
        )

        desc_adicional_manual = st.number_input(
            "✂️ **Polvo Mágico Extra (Ajuste)**", 
            min_value=-500000, 
            value=0, 
            step=1000, 
            key="new_desc_adic",
            help="Ingresa un valor positivo para descuentos (más magia) o negativo para cargos."
        )
        
        # Ejecutar el cálculo central en tiempo real
        resultados = calcular_ingreso(
            lugar_seleccionado, 
            item_seleccionado, 
            metodo_pago, 
            desc_adicional_manual,
            fecha_atencion=fecha, 
            valor_bruto_override=valor_bruto_input
        )
        
        # Mostrar el resultado final y los detalles del descuento
        st.warning(f"**Desc. Tarjeta 🧙‍♀️ ({COMISIONES_PAGO.get(metodo_pago, 0.00)*100:.0f}%):** ${resultados['desc_tarjeta']:,.0f}".replace(",", "."))
        
        desc_lugar_label = f"Tributo al Castillo ({lugar_seleccionado})"
        if lugar_seleccionado == 'AMAR AUSTRAL':
            dias_semana = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
            desc_lugar_label += f" ({dias_semana.get(fecha.weekday())})" 

        st.info(f"**{desc_lugar_label}:** ${resultados['desc_fijo_lugar']:,.0f}".replace(",", "."))
        
        st.markdown("###")
        # Cambio de color a verde (success) para resaltar el ingreso
        st.success(
            f"## 💎 Tesoro Total (Líquido): ${resultados['total_recibido']:,.0f}".replace(",", ".")
        )
        
        # Botón para registrar la atención
        if st.button("✅ ¡Guardar Aventura y Tesoro!", use_container_width=True, type="primary"):
            if paciente == "":
                st.error("Por favor, ingresa el nombre del paciente.")
            else:
                nueva_atencion = {
                    "Fecha": fecha.strftime('%Y-%m-%d'), 
                    "Lugar": lugar_seleccionado, 
                    "Ítem": item_seleccionado, 
                    "Paciente": paciente, 
                    "Método Pago": metodo_pago,
                    "Valor Bruto": resultados['valor_bruto'],
                    "Desc. Fijo Lugar": resultados['desc_fijo_lugar'],
                    "Desc. Tarjeta": resultados['desc_tarjeta'],
                    "Desc. Adicional": desc_adicional_manual,
                    "Total Recibido": resultados['total_recibido']
                }
                
                st.session_state.atenciones_df.loc[len(st.session_state.atenciones_df)] = nueva_atencion
                save_data(st.session_state.atenciones_df)
                st.success(f"🎉 ¡Aventura registrada para {paciente}! El tesoro es ${resultados['total_recibido']:,.0f}".replace(",", "."))
                st.balloons()


# ===============================================
# 4. DASHBOARD DE RESUMEN (ESTILO LÚDICO Y EXPORTACIÓN SIMPLE)
# ===============================================
st.markdown("---")
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
    if filtro_lugar != 'Todos los Reinos':
        df = df[df['Lugar'] == filtro_lugar]
        
    if filtro_item != 'Todas las Pociones':
        df = df[df['Ítem'] == filtro_item]
    
    if df.empty:
        st.warning("No hay datos disponibles para la combinación mágica seleccionada.")
        st.stop()
        
    # LÓGICA DE VALIDACIÓN DE FECHAS SEGURA 
    df_valid_dates = df.dropna(subset=['Fecha'])

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
    
    df = df.dropna(subset=['Fecha']) 
    
    df_filtrado = df[
        (df['Fecha'].dt.date >= fecha_inicio) & 
        (df['Fecha'].dt.date <= fecha_fin)
    ]
    
    if df_filtrado.empty:
        st.warning("No hay tesoros registrados en este periodo de tiempo.")
        st.stop()
        
    df = df_filtrado
    
    # ----------------------------------------------------
    # MÉTRICAS PRINCIPALES (KPIs) - ESTILO MÁS VISUAL
    # ----------------------------------------------------
    
    def format_currency(value):
        return f"${value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
    st.markdown("### 🔑 Metas Clave")
    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    
    total_liquido_historico = df["Total Recibido"].sum()
    col_kpi1.metric("💎 Tesoro Neto (Líquido)", format_currency(total_liquido_historico))
    
    total_bruto_historico = df["Valor Bruto"].sum()
    col_kpi2.metric("✨ Recompensa Bruta", format_currency(total_bruto_historico))
    
    total_atenciones_historico = len(df)
    col_kpi3.metric("👸 Total Héroes Atendidos", f"{total_atenciones_historico:,}".replace(",", "."))
    
    st.markdown("---")
    st.subheader("💔 Los Maleficios y Tributos (Descuentos)")
    
    col_det1, col_det2 = st.columns(2)
    
    total_desc_tarjeta = df["Desc. Tarjeta"].sum()
    col_det1.metric(
        "💳 Comisiones del Hada Madrina (Tarjeta)", 
        format_currency(total_desc_tarjeta)
    )
    
    total_desc_fijo_lugar = df["Desc. Fijo Lugar"].sum()
    col_det2.metric(
        "📍 Tributo Fijo al Castillo", 
        format_currency(total_desc_fijo_lugar)
    )

    st.markdown("---")
    
    # Análisis Mensual
    st.subheader("🚀 El Viaje en el Tiempo (Evolución Mensual)")
    df['Mes_Año'] = df['Fecha'].dt.to_period('M').astype(str)
    resumen_mensual = df.groupby('Mes_Año')['Total Recibido'].sum().reset_index()
    
    st.bar_chart(resumen_mensual.set_index('Mes_Año'), color="#ff7f0e") 
    
    # Análisis por Lugar (Plotly)
    st.subheader("🗺️ Mapa de Castillos (Distribución de Ingresos)")
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
        cols[2].write(f"${row['Total Recibido']:,.0f}".replace(",", "."))
        cols[3].write(row['Paciente'])
        
        # --- BOTÓN DE EDICIÓN ---
        if cols[4].button("✏️", key=f"edit_{index}", help="Editar esta aventura"):
            st.session_state.edit_index = index
            st.session_state.edited_lugar_state = row['Lugar'] 
            st.rerun()

        # --- BOTÓN DE ELIMINACIÓN ---
        if cols[5].button("🗑️", key=f"delete_{index}", help="Eliminar esta aventura (¡Cuidado con la magia negra!)"):
            st.session_state.atenciones_df = st.session_state.atenciones_df.drop(index)
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
# 5. MODAL DE EDICIÓN DE REGISTRO (CORREGIDO)
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
            
            # ** SELECTBOX DE LUGAR DEBE ESTAR FUERA DEL FORMULARIO **
            edited_lugar_display = st.selectbox(
                "📍 Castillo/Lugar de Atención", 
                options=LUGARES, 
                index=lugar_idx, 
                key="edit_lugar", 
                on_change=update_edited_lugar 
            )

            items_edit = list(PRECIOS_BASE_CONFIG.get(st.session_state.edited_lugar_state, {}).keys())
            
            try:
                current_item_index = items_edit.index(data_to_edit['Ítem'])
            except ValueError:
                current_item_index = 0
            
            item_key = f"edit_item_for_{st.session_state.edited_lugar_state}" 
            
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
            current_lugar = st.session_state.edit_lugar
            current_item = st.session_state[item_key]
            precio_base_sugerido = PRECIOS_BASE_CONFIG.get(current_lugar, {}).get(current_item, 0)
            
            if ('edit_valor_bruto' not in st.session_state or 
                st.session_state.edit_lugar != data_to_edit['Lugar'] or 
                st.session_state[item_key] != data_to_edit['Ítem']):
                
                initial_valor_bruto = int(precio_base_sugerido)
                st.session_state.edit_valor_bruto = initial_valor_bruto
                
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

            # ------------------------------------------------------------------
            # CÁLCULO Y DISPLAY DE RESULTADOS EN TIEMPO REAL 
            # ------------------------------------------------------------------
            
            recalculo = calcular_ingreso(
                st.session_state.edit_lugar, 
                st.session_state[item_key], 
                st.session_state.edit_metodo, 
                st.session_state.edit_desc_adic, 
                fecha_atencion=st.session_state.edit_fecha, 
                valor_bruto_override=st.session_state.edit_valor_bruto 
            )

            st.warning(
                f"**Desc. Tarjeta 🧙‍♀️ ({COMISIONES_PAGO.get(st.session_state.edit_metodo, 0.00)*100:.0f}%):** ${recalculo['desc_tarjeta']:,.0f}".replace(",", ".")
            )
            
            desc_lugar_label = f"Tributo al Castillo ({st.session_state.edit_lugar})"
            if st.session_state.edit_lugar == 'AMAR AUSTRAL':
                dias_semana = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
                desc_lugar_label += f" ({dias_semana.get(st.session_state.edit_fecha.weekday())})" 

            st.info(f"**{desc_lugar_label}:** ${recalculo['desc_fijo_lugar']:,.0f}".replace(",", "."))
            
            st.markdown("###")
            st.success(
                f"## 💎 NUEVO TOTAL LÍQUIDO: ${recalculo['total_recibido']:,.0f}".replace(",", ".")
            )
            # ------------------------------------------------------------------
        
        # 2. BOTONES DE ACCIÓN DENTRO DEL FORMULARIO
        with st.form("edit_form", clear_on_submit=False):
            # Clonamos valores finales del estado de sesión para el guardado dentro del form
            st.session_state.form_lugar = st.session_state.edit_lugar
            st.session_state.form_item = st.session_state[item_key]
            st.session_state.form_paciente = st.session_state.edit_paciente
            st.session_state.form_metodo = st.session_state.edit_metodo
            st.session_state.form_valor_bruto = st.session_state.edit_valor_bruto
            st.session_state.form_desc_adic = st.session_state.edit_desc_adic
            
            col_btn1, col_btn2 = st.columns([1, 1])
            
            submit_button = col_btn1.form_submit_button("💾 Guardar Cambios y Actualizar", type="primary")
            cancel_button = col_btn2.form_submit_button("❌ Cancelar Edición")


            if submit_button:
                # Recalculamos con los valores del estado de sesión finales
                recalculo_final = calcular_ingreso(
                    st.session_state.form_lugar, 
                    st.session_state.form_item, 
                    st.session_state.form_metodo, 
                    st.session_state.form_desc_adic, 
                    fecha_atencion=st.session_state.edit_fecha, 
                    valor_bruto_override=st.session_state.form_valor_bruto 
                )

                st.session_state.atenciones_df.loc[index_to_edit] = {
                    "Fecha": st.session_state.edit_fecha.strftime('%Y-%m-%d'), 
                    "Lugar": st.session_state.form_lugar, 
                    "Ítem": st.session_state.form_item, 
                    "Paciente": st.session_state.form_paciente, 
                    "Método Pago": st.session_state.form_metodo,
                    "Valor Bruto": recalculo_final['valor_bruto'], 
                    "Desc. Fijo Lugar": recalculo_final['desc_fijo_lugar'], 
                    "Desc. Tarjeta": recalculo_final['desc_tarjeta'], 
                    "Desc. Adicional": st.session_state.form_desc_adic,
                    "Total Recibido": recalculo_final['total_recibido'] 
                }
                
                save_data(st.session_state.atenciones_df)
                st.session_state.edit_index = None 
                st.session_state.edited_lugar_state = None 
                st.success(f"🎉 Aventura para {st.session_state.form_paciente} actualizada exitosamente. Recargando el mapa...")
                time.sleep(0.5) 
                st.rerun()
                
            if cancel_button:
                st.session_state.edit_index = None 
                st.session_state.edited_lugar_state = None 
                st.rerun()
