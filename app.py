import streamlit as st
import pandas as pd
import time
# Nota: Se eliminó 'locale' para evitar errores de despliegue, el formato de moneda se hace con f-strings

# ===============================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ===============================================
st.set_page_config(
    page_title="Dashboard Fonoaudiología",
    layout="wide",
    initial_sidebar_state="expanded"
)
# ===============================================
# 2. FUNCIONES DE PERSISTENCIA (CONEXIÓN Y CARGA)
# ===============================================

# ¡CONEXIÓN DIRECTA ESTABILIZADA!
# Se corrigen el Host y el Username para la conexión directa a 5432.
conn = st.connection(
    "supabase_direct",  
    type="sql",
    dialect="postgresql",
    # *** CAMBIO CLAVE 1: HOST sin prefijo 'db.' ***
    host="emnqztaxybhbmkuryhem.supabase.co", 
    port=5432, 
    database="atenciones",
    # *** CAMBIO CLAVE 2: USERNAME SIMPLE 'postgres' ***
    username="postgres", 
    # El password parece tener mayúscula, se mantiene como está si es correcta
    password="DomiLeo1702" 
)
# ...

@st.cache_data(ttl=3600)
def load_data_from_db():
    try:
        # Consulta SQL estable con limpieza de columnas
        df = conn.query('SELECT * FROM public."atenciones";')
        df.columns = df.columns.str.strip().str.lower()
        df = df.sort_values(by="fecha", ascending=False)
        df['fecha'] = pd.to_datetime(df['fecha']) 
        return df
    except Exception as e:
        st.error(f"Error CRÍTICO al cargar datos de Supabase. Mensaje: {e}")
        return pd.DataFrame()

# ===============================================
# 3. CUERPO PRINCIPAL DE LA APLICACIÓN (SECCIÓN)
# ===============================================

st.title("📊 Dashboard de Gestión Fonoaudiológica")

# Cargar los datos
data_load_state = st.text('Cargando datos de Supabase...')
df = load_data_from_db()
data_load_state.text('¡Datos cargados y listos!')

if df.empty:
    st.warning("No se pudieron cargar los datos o el DataFrame está vacío. Por favor, revisa la conexión y la tabla.")
else:
    # Si los datos se cargaron, mostramos la sección del dashboard
    st.success(f"Datos cargados exitosamente. Total de atenciones: {len(df)}")

    # ----------------------------------------------------
    # SECCIÓN PRINCIPAL DEL DASHBOARD 
    # ----------------------------------------------------
    
    # Formato de moneda simplificado para evitar errores de locale
    def format_currency(value):
        return f"${value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")

    col1, col2, col3 = st.columns(3)
    
    # KPI 1: Total de Ingresos
    # Nota: Usamos el nombre limpio 'total_recibido'
    total_ingresos = df['total_recibido'].sum()
    col1.metric(
        label="💰 Total de Ingresos Recibidos", 
        value=format_currency(total_ingresos)
    )

    # KPI 2: Número Total de Atenciones
    total_atenciones = len(df)
    col2.metric(
        label="👥 Total de Atenciones Registradas", 
        value=f"{total_atenciones:,}".replace(",", ".")
    )
    
    # KPI 3: Valor Bruto Promedio
    # Nota: Usamos el nombre limpio 'valor_bruto'
    valor_bruto_promedio = df['valor_bruto'].mean()
    col3.metric(
        label="💸 Valor Bruto Promedio", 
        value=format_currency(valor_bruto_promedio)
    )

    st.markdown("---")
    
    # Gráfico de Tendencia de Ingresos
    st.header("📈 Tendencia de Ingresos por Fecha")
    
    # Agrupar los ingresos por la columna limpia 'fecha'
    ingresos_diarios = df.groupby('fecha')['total_recibido'].sum().reset_index()
    ingresos_diarios.columns = ['Fecha', 'Ingresos'] # Renombrar para claridad
    
    st.line_chart(ingresos_diarios.set_index('Fecha')['Ingresos'])

    # Vista previa de la tabla de datos
    st.header("📋 Vista Previa de Datos Crudos")
    st.dataframe(df, use_container_width=True)
