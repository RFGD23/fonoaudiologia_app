import streamlit as st
import pandas as pd
from datetime import date
import os
import io
import plotly.express as px 
import json # <-- NUEVA LIBRERÍA

# ===============================================
# CONFIGURACIÓN Y BASES DE DATOS (MAESTRAS)
# ===============================================

DATA_FILE = 'atenciones_registradas.csv'

def load_config(filename):
    """Carga la configuración desde un archivo JSON."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"Error CRÍTICO: No se encontró el archivo de configuración {filename}. Asegúrate de que existe en la carpeta raíz.")
        return {} # Retorna un diccionario vacío para evitar fallos
    except json.JSONDecodeError:
        st.error(f"Error: El archivo {filename} tiene un formato JSON inválido.")
        return {}

# --- Cargar Variables Globales desde JSON ---
PRECIOS_BASE_CONFIG = load_config('precios_base.json')
DESCUENTOS_LUGAR = load_config('descuentos_lugar.json')
COMISIONES_PAGO = load_config('comisiones_pago.json')

# Variables de la aplicación (derivadas de la configuración)
LUGARES = sorted(list(PRECIOS_BASE_CONFIG.keys()))
METODOS_PAGO = list(COMISIONES_PAGO.keys())


# ===============================================
# 2. FUNCIONES DE PERSISTENCIA Y CÁLCULO
# ===============================================

@st.cache_data
def load_data():
    """Carga los datos del archivo CSV de forma segura."""
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce') 
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
    
    # *** CAMBIO CLAVE: Acceso anidado a precios ***
    # Accedemos a PRECIOS_BASE_CONFIG[Lugar][Ítem] de forma segura.
    precio_base = PRECIOS_BASE_CONFIG.get(lugar, {}).get(item, 0)
    valor_bruto = valor_bruto_override if valor_bruto_override is not None else precio_base
    
    # 1. Descuento Fijo por Lugar (Base)
    desc_fijo_lugar = DESCUENTOS_LUGAR.get(lugar, 0)
    
    # LÓGICA CONDICIONAL: AMAR AUSTRAL (Martes/Viernes)
    if lugar == 'AMAR AUSTRAL':
        dia_semana = fecha_atencion.weekday() 
        
        if dia_semana == 1:  # Martes
            desc_fijo_lugar = 8000
        elif dia_semana == 4:  # Viernes
            desc_fijo_lugar = 6500

    # 2. Aplicar Comisión de Tarjeta
    comision_pct = COMISIONES_PAGO.get(metodo_pago, 0.00)
    desc_tarjeta = valor_bruto * comision_pct
    
    # 3. Cálculo final del total recibido (Líquido)
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

# ===============================================
# 3. INTERFAZ DE USUARIO (FRONTEND)
# ===============================================

st.set_page_config(page_title="Control de Ingresos Fonoaudiología", layout="wide")
st.title("💸 Sistema Interactivo de Ingreso de Atenciones")
st.markdown("---")

# Cargar los datos y asignarlos al estado de la sesión
if 'atenciones_df' not in st.session_state:
    st.session_state.atenciones_df = load_data()
# --- Herramientas de Mantenimiento ---
if st.sidebar.button("🧹 Limpiar Caché y Recargar Datos", type="secondary"):
    # Limpia la caché de st.cache_data
    st.cache_data.clear() 
    # Limpia la caché de st.cache_resource (si se usara)
    st.cache_resource.clear() 
    st.success("Caché limpiada. Recargando aplicación...")
    # *** CORRECCIÓN: Usamos la función actual st.rerun() ***
    st.rerun() 
st.sidebar.markdown("---")
# --- FORMULARIO DE INGRESO ---
with st.expander("➕ Ingresar Nueva Atención", expanded=True):
    col1, col2 = st.columns([1, 1])

    with col1:
        fecha = st.date_input("🗓️ Fecha de Atención", date.today())
        lugar_seleccionado = st.selectbox("📍 Lugar de Atención", options=LUGARES)
        
        # *** CAMBIO CLAVE: Filtrado inteligente de ítems usando la nueva estructura anidada ***
        items_filtrados = list(PRECIOS_BASE_CONFIG.get(lugar_seleccionado, {}).keys())
        item_seleccionado = st.selectbox("📋 Ítem/Procedimiento", options=items_filtrados)
        
        paciente = st.text_input("👤 Nombre del Paciente/Asociado", "")
        metodo_pago = st.radio("💳 Método de Pago", options=METODOS_PAGO)

    with col2:
        # *** CAMBIO CLAVE: Obtener el precio base con la nueva estructura ***
        precio_base = PRECIOS_BASE_CONFIG.get(lugar_seleccionado, {}).get(item_seleccionado, 0)
        
        valor_bruto_input = st.number_input(
            "💰 **Valor Bruto (Sistema)**", 
            min_value=0, 
            value=int(precio_base), 
            step=1000
        )

        desc_adicional_manual = st.number_input(
            "✂️ **Descuento Adicional/Ajuste**", 
            min_value=-500000, 
            value=0, 
            step=1000, 
            help="Ingresa un valor positivo para descuentos o negativo para cargos."
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
        st.warning(f"**Desc. Tarjeta ({COMISIONES_PAGO.get(metodo_pago, 0.00)*100:.0f}%):** ${resultados['desc_tarjeta']:,.0f}".replace(",", "."))
        
        desc_lugar_label = f"Desc. Fijo Lugar ({lugar_seleccionado})"
        # Muestra el día de la semana si es AMAR AUSTRAL para clarificar
        if lugar_seleccionado == 'AMAR AUSTRAL':
            dias_semana = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
            desc_lugar_label += f" ({dias_semana.get(fecha.weekday())})" 

        st.info(f"**{desc_lugar_label}:** ${resultados['desc_fijo_lugar']:,.0f}".replace(",", "."))
        
        st.markdown("###")
        st.metric(
            label="## TOTAL LÍQUIDO A INGRESAR", 
            value=f"${resultados['total_recibido']:,.0f}".replace(",", ".")
        )
        
        # Botón para registrar la atención
        if st.button("✅ Registrar Atención y Guardar", use_container_width=True, type="primary"):
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
                st.success(f"🎉 Atención registrada para {paciente} por ${resultados['total_recibido']:,.0f}.".replace(",", "."))
                st.balloons()

# ===============================================
# 4. DASHBOARD DE RESUMEN
# ===============================================

# ... (El resto del código de la sección 4 es idéntico a la versión anterior y es estable)
# ...
st.markdown("---")
st.header("📊 Resumen y Análisis de Ingresos")

df = st.session_state.atenciones_df
# ===============================================
# 4. DASHBOARD DE RESUMEN (CON MEJORAS Y FILTRO)
# ===============================================
st.markdown("---")
st.header("📊 Resumen y Análisis de Ingresos")

df = st.session_state.atenciones_df

if not df.empty:
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    
    # ----------------------------------------------------
    # FILTRO POR RANGO DE FECHA (NUEVA IMPLEMENTACIÓN)
    # ----------------------------------------------------
    
    min_date = df['Fecha'].min().date()
    max_date = df['Fecha'].max().date()
    
    st.subheader("Filtro de Periodo")
    col_start, col_end = st.columns(2)
    
    fecha_inicio = col_start.date_input(
        "📅 Fecha de Inicio", 
        min_date, 
        min_value=min_date, 
        max_value=max_date
    )
    fecha_fin = col_end.date_input(
        "📅 Fecha de Fin", 
        max_date, 
        min_value=min_date, 
        max_value=max_date
    )
    
    # Aplicar el filtro al DataFrame
    df_filtrado = df[
        (df['Fecha'].dt.date >= fecha_inicio) & 
        (df['Fecha'].dt.date <= fecha_fin)
    ]
    
   if df_filtrado.empty:
        st.warning("No hay datos registrados en el rango de fechas seleccionado.")
        # Usamos st.stop() para detener la ejecución de Streamlit de forma segura
        st.stop()

    # A partir de aquí, usamos df_filtrado en lugar de df
    df = df_filtrado

    # ----------------------------------------------------
    # MÉTRICAS PRINCIPALES (KPIs) (APLICADAS A df_filtrado)
    # ----------------------------------------------------
    
    def format_currency(value):
        return f"${value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    
    # ... (El resto del código de las métricas, gráficos y tablas sigue abajo, 
    # pero ahora usando el DataFrame 'df' que contiene los datos filtrados)
if not df.empty:
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce') 

    def format_currency(value):
        return f"${value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    
    total_liquido_historico = df["Total Recibido"].sum()
    col_kpi1.metric("Total Líquido Histórico", format_currency(total_liquido_historico))
    
    total_bruto_historico = df["Valor Bruto"].sum()
    col_kpi2.metric("Total Bruto Histórico", format_currency(total_bruto_historico))
    
    total_atenciones_historico = len(df)
    col_kpi3.metric("Total de Atenciones", f"{total_atenciones_historico:,}".replace(",", "."))
    
    st.markdown("---")
    st.subheader("Detalle de Descuentos y Comisiones")
    
    col_det1, col_det2 = st.columns(2)
    
    total_desc_tarjeta = df["Desc. Tarjeta"].sum()
    col_det1.metric(
        "💳 Total Comisiones de Tarjeta", 
        format_currency(total_desc_tarjeta)
    )
    
    total_desc_fijo_lugar = df["Desc. Fijo Lugar"].sum()
    col_det2.metric(
        "📍 Total Desc. Fijo Lugar (Base)", 
        format_currency(total_desc_fijo_lugar)
    )

    st.markdown("---")
    
    st.subheader("📈 Evolución Mensual de Ingresos Líquidos")
    df['Mes_Año'] = df['Fecha'].dt.to_period('M').astype(str)
    resumen_mensual = df.groupby('Mes_Año')['Total Recibido'].sum().reset_index()
    
    st.bar_chart(resumen_mensual.set_index('Mes_Año'), color="#4c78a8")

    st.subheader("🥧 Distribución de Ingresos por Centro de Atención")
    resumen_lugar = df.groupby("Lugar")["Total Recibido"].sum().reset_index()
    
    fig_lugar = px.pie(
        resumen_lugar,
        values='Total Recibido',
        names='Lugar',
        title='Proporción de Ingresos Líquidos por Centro',
        color_discrete_sequence=px.colors.sequential.RdBu
    )
    fig_lugar.update_traces(textposition='inside', textinfo='percent+label')
    st.plotly_chart(fig_lugar, use_container_width=True)

    st.header("📋 Vista Previa de Datos Crudos")
    st.dataframe(df, use_container_width=True)
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="⬇️ Descargar Todos los Datos Registrados (CSV)",
        data=csv,
        file_name='reporte_control_ingresos.csv',
        mime='text/csv',
    )
else:
    st.info("Aún no hay datos. Registra tu primera atención para ver el resumen.")
