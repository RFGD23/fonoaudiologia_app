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
        # Consulta SQL correcta
        df = conn.query('SELECT * FROM public."atenciones";')

        # Limpieza de nombres de columna
        df.columns = df.columns.str.strip().str.lower()
        
        # ----------------------------------------------------------------------
        # *** ÚLTIMA COMPROBACIÓN Y CORRECCIÓN ***
        # ----------------------------------------------------------------------
        
        # 1. Comprobamos si la columna 'fecha' existe en el DataFrame limpio
        if 'fecha' not in df.columns:
            # Si 'fecha' no está, mostramos un error con las columnas REALES
            columnas_reales = df.columns.tolist()
            
            # Buscamos el nombre más probable que contenga 'fecha'
            nombre_fecha_encontrado = next((col for col in columnas_reales if 'fecha' in col), None)

            if nombre_fecha_encontrado:
                # Si encontramos algo que se parece a 'fecha', lo usamos
                st.warning(f"La columna 'fecha' no se encontró. Usando el nombre más probable: '{nombre_fecha_encontrado}'")
                columna_orden = nombre_fecha_encontrado
                
            else:
                # Si no encontramos nada, usamos una columna por defecto para que la app no falle
                st.error(f"¡Error Crítico! La columna de fecha no se encuentra. Columnas disponibles: {columnas_reales}")
                # Usaremos la columna desc_adicional (que existe según la metadata) para ordenar y evitar el crash
                columna_orden = 'desc_adicional' 
        else:
            columna_orden = 'fecha'

        # 2. Ordenación y Conversión
        df = df.sort_values(by=columna_orden, ascending=False)
        
        # Solo intentamos convertir a fecha si el nombre encontrado contiene 'fecha'
        if 'fecha' in columna_orden:
            df[columna_orden] = pd.to_datetime(df[columna_orden]) 
        
        return df
        
    except Exception as e:
        # Mensaje de error final
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
