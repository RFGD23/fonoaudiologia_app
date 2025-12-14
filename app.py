import streamlit as st
import pandas as pd
import time
import locale

# Establecer la configuración regional para formato de moneda (ajusta si es necesario)
try:
    locale.setlocale(locale.LC_ALL, 'es_CL.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'es_ES.UTF-8')
    except locale.Error:
        pass # Usa la configuración predeterminada si falla

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

# Conexión al Pooler de Sesiones de Supabase
conn = st.connection(
    "supabase_pooler", 
    type="sql",
    dialect="postgresql",
    host="aws-1-us-east-1.pooler.supabase.com", 
    port=5432, 
    database="postgres",
    username="postgres.emnqztaxybhbmkuryhem", 
    password="Domileo1702" 
)

@st.cache_data(ttl=3600)
def load_data_from_db():
    try:
        # Consulta SQL: Se ejecuta sin ORDER BY para evitar el error inicial de PostgreSQL
        df = conn.query('SELECT * FROM public."atenciones";')

        # ----------------------------------------------------------------------
        # *** SOLUCIÓN FINAL AL ERROR DE 'fecha' (KeyError) ***
        # 1. str.strip(): Elimina espacios en blanco o caracteres invisibles.
        # 2. str.lower(): Asegura que todo esté en minúsculas.
        df.columns = df.columns.str.strip().str.lower()
        # ----------------------------------------------------------------------
        
        # Ordenación segura con Pandas usando el nombre limpio 'fecha'
        df = df.sort_values(by="fecha", ascending=False)
        
        # Convertir la columna de fecha a formato datetime
        df['fecha'] = pd.to_datetime(df['fecha']) 
        
        return df
        
    except Exception as e:
        # Mensaje de error simplificado si la corrección funciona
        st.error(f"Error al cargar datos de Supabase. Mensaje: {e}")
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
    
    col1, col2, col3 = st.columns(3)
    
    # KPI 1: Total de Ingresos
    # Nota: Asumiendo que la columna de ingresos se llama 'total_recibido'
    total_ingresos = df['total_recibido'].sum()
    col1.metric(
        label="💰 Total de Ingresos Recibidos", 
        value=locale.currency(total_ingresos, grouping=True)
    )

    # KPI 2: Número Total de Atenciones
    total_atenciones = len(df)
    col2.metric(
        label="👥 Total de Atenciones Registradas", 
        value=f"{total_atenciones:,}"
    )
    
    # KPI 3: Valor Bruto Promedio
    # Nota: Asumiendo que la columna de valor bruto se llama 'valor_bruto'
    valor_bruto_promedio = df['valor_bruto'].mean()
    col3.metric(
        label="💸 Valor Bruto Promedio", 
        value=locale.currency(valor_bruto_promedio, grouping=True)
    )

    st.markdown("---")
    
    # Gráfico de Tendencia de Ingresos
    st.header("📈 Tendencia de Ingresos por Fecha")
    
    # Agrupar los ingresos por la columna limpia 'fecha'
    ingresos_diarios = df.groupby('fecha')['total_recibido'].sum().reset_index()
    ingresos_diarios.columns = ['Fecha', 'Ingresos'] # Renombrar para claridad en el gráfico
    
    st.line_chart(ingresos_diarios.set_index('Fecha')['Ingresos'])

    # Vista previa de la tabla de datos
    st.header("📋 Vista Previa de Datos Crudos")
    st.dataframe(df, use_container_width=True)
