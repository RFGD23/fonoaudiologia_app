import streamlit as st
import pandas as pd
from datetime import date
import os
import io
import plotly.express as px 
import json 

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
        st.error(f"Error CRÍTICO: No se encontró el archivo de configuración {filename}.")
        return {} 
    except json.JSONDecodeError:
        st.error(f"Error: El archivo {filename} tiene un formato JSON inválido.")
        return {}

# --- Cargar Variables Globales desde JSON (Asumiendo que existen 'precios_base.json', 'descuentos_lugar.json', etc.) ---
try:
    PRECIOS_BASE_CONFIG = load_config('precios_base.json')
    DESCUENTOS_LUGAR = load_config('descuentos_lugar.json')
    COMISIONES_PAGO = load_config('comisiones_pago.json')
except:
    # Fallback si no existen los archivos JSON (solo para que el código compile si faltan las bases de datos externas)
    PRECIOS_BASE_CONFIG = {'ALERCE': {'Item1': 30000}, 'AMAR AUSTRAL': {'ItemA': 25000}}
    DESCUENTOS_LUGAR = {'ALERCE': 5000, 'AMAR AUSTRAL': 7000}
    COMISIONES_PAGO = {'EFECTIVO': 0.00, 'TRANSFERENCIA': 0.00, 'TARJETA': 0.03}


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

# --- Herramientas de Mantenimiento (Limpiar Caché) ---
if st.sidebar.button("🧹 Limpiar Caché y Recargar Datos", type="secondary"):
    st.cache_data.clear() 
    st.cache_resource.clear() 
    st.success("Caché limpiada. Recargando aplicación...")
    st.rerun() 

st.sidebar.markdown("---") 

# Cargar los datos y asignarlos al estado de la sesión
if 'atenciones_df' not in st.session_state:
    st.session_state.atenciones_df = load_data()
    
# --- Variable para gestionar la edición ---
if 'edit_index' not in st.session_state:
    st.session_state.edit_index = None 

# --- Variable para almacenar el lugar seleccionado en la edición (CORRECCIÓN DEPENDENCIA) ---
if 'edited_lugar_state' not in st.session_state:
    st.session_state.edited_lugar_state = None 

# --- FORMULARIO DE INGRESO ---
with st.expander("➕ Ingresar Nueva Atención", expanded=True):
    col1, col2 = st.columns([1, 1])

    with col1:
        fecha = st.date_input("🗓️ Fecha de Atención", date.today())
        lugar_seleccionado = st.selectbox("📍 Lugar de Atención", options=LUGARES, key="new_lugar")
        
        items_filtrados = list(PRECIOS_BASE_CONFIG.get(lugar_seleccionado, {}).keys())
        item_seleccionado = st.selectbox("📋 Ítem/Procedimiento", options=items_filtrados, key="new_item")
        
        paciente = st.text_input("👤 Nombre del Paciente/Asociado", "")
        metodo_pago = st.radio("💳 Método de Pago", options=METODOS_PAGO, key="new_metodo_pago")

    with col2:
        precio_base = PRECIOS_BASE_CONFIG.get(lugar_seleccionado, {}).get(item_seleccionado, 0)
        
        valor_bruto_input = st.number_input(
            "💰 **Valor Bruto (Sistema)**", 
            min_value=0, 
            value=int(precio_base), 
            step=1000,
            key="new_valor_bruto"
        )

        desc_adicional_manual = st.number_input(
            "✂️ **Descuento Adicional/Ajuste**", 
            min_value=-500000, 
            value=0, 
            step=1000, 
            key="new_desc_adic",
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
# 4. DASHBOARD DE RESUMEN (CON TODOS LOS FILTROS Y GESTIÓN)
# ===============================================
st.markdown("---")
st.header("📊 Resumen y Análisis de Ingresos")

df = st.session_state.atenciones_df

# Bloque principal que solo se ejecuta si hay datos en el DataFrame cargado
if not df.empty:
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')

    # --- FILTROS DINÁMICOS EN LA BARRA LATERAL (Lugar e Ítem) ---
    st.sidebar.header("🔍 Filtros de Análisis")
    
    # 1. Filtro por Lugar
    lugares_disponibles = ['Todos'] + sorted(df['Lugar'].unique().tolist())
    filtro_lugar = st.sidebar.selectbox(
        "📍 Seleccionar Centro de Atención", 
        options=lugares_disponibles
    )
    
    # 2. Filtro por Ítem (Dependiente de Lugar)
    if filtro_lugar != 'Todos':
        df_lugar = df[df['Lugar'] == filtro_lugar]
        items_disponibles = ['Todos'] + sorted(df_lugar['Ítem'].unique().tolist())
    else:
        items_disponibles = ['Todos'] + sorted(df['Ítem'].unique().tolist())
        
    filtro_item = st.sidebar.selectbox(
        "📋 Seleccionar Ítem/Procedimiento", 
        options=items_disponibles
    )
    st.sidebar.markdown("---") 
    
    # ----------------------------------------------------
    # APLICACIÓN DE FILTROS 1 Y 2 (Lugar e Ítem)
    # ----------------------------------------------------
    
    if filtro_lugar != 'Todos':
        df = df[df['Lugar'] == filtro_lugar]
        
    if filtro_item != 'Todos':
        df = df[df['Ítem'] == filtro_item]
    
    # ----------------------------------------------------
    # FILTRO POR RANGO DE FECHA (SOLUCIÓN DEFINITIVA DE ERRORES)
    # ----------------------------------------------------
    
    # Si después de los filtros Lugar/Ítem el DF está vacío, detenemos la ejecución
    if df.empty:
        st.warning("No hay datos disponibles para la combinación de Lugar/Ítem seleccionada.")
        st.stop()
        
    # --- LÓGICA DE VALIDACIÓN DE FECHAS SEGURA ---
    
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
    # -------------------------------------------------------------------------

    st.subheader("Filtro de Periodo")
    col_start, col_end = st.columns(2)
    
    fecha_default_inicio = min_date
    if min_date > max_date:
        fecha_default_inicio = max_date 
        
    fecha_inicio = col_start.date_input(
        "📅 Fecha de Inicio", 
        fecha_default_inicio, 
        min_value=min_date, 
        max_value=max_date
    )
    fecha_fin = col_end.date_input(
        "📅 Fecha de Fin", 
        max_date, 
        min_value=min_date, 
        max_value=max_date
    )
    
    # --- CORRECCIÓN FINAL PARA EL TypeError: Limpiar NaN/NaT antes de comparar ---
    df = df.dropna(subset=['Fecha']) 
    
    # Aplicar el filtro final al DataFrame
    df_filtrado = df[
        (df['Fecha'].dt.date >= fecha_inicio) & 
        (df['Fecha'].dt.date <= fecha_fin)
    ]
    
    if df_filtrado.empty:
        st.warning("No hay datos registrados en el rango de fechas seleccionado.")
        st.stop()
        
    # Usamos el DataFrame filtrado para todos los cálculos
    df = df_filtrado
    
    # ----------------------------------------------------
    # MÉTRICAS PRINCIPALES (KPIs)
    # ----------------------------------------------------
    
    def format_currency(value):
        return f"${value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    
    total_liquido_historico = df["Total Recibido"].sum()
    col_kpi1.metric("Total Líquido", format_currency(total_liquido_historico))
    
    total_bruto_historico = df["Valor Bruto"].sum()
    col_kpi2.metric("Total Bruto", format_currency(total_bruto_historico))
    
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
    
    # Análisis Mensual
    st.subheader("📈 Evolución Mensual de Ingresos Líquidos")
    df['Mes_Año'] = df['Fecha'].dt.to_period('M').astype(str)
    resumen_mensual = df.groupby('Mes_Año')['Total Recibido'].sum().reset_index()
    
    st.bar_chart(resumen_mensual.set_index('Mes_Año'), color="#4c78a8")

    # Análisis por Lugar (Plotly)
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

    # ----------------------------------------------------
    # GESTIÓN: VISTA PREVIA, EDICIÓN Y ELIMINACIÓN DE DATOS
    # ----------------------------------------------------
    st.header("📋 Gestión de Atenciones Registradas")

    df_display = df.copy() 
    
    st.subheader("Atenciones Registradas (✏️ Editar, 🗑️ Eliminar)")

    # Títulos de columna
    cols_title = st.columns([0.15, 0.15, 0.15, 0.3, 0.1, 0.1])
    cols_title[0].write("**Fecha**")
    cols_title[1].write("**Lugar**")
    cols_title[2].write("**Líquido**")
    cols_title[3].write("**Paciente**")
    cols_title[4].write("**Editar**") 
    cols_title[5].write("**Eliminar**") 
    
    st.markdown("---") 

    # Iterar sobre las filas y crear los botones
    for index, row in df_display.iterrows():
        
        # Crear una estructura de columnas para cada fila
        cols = st.columns([0.15, 0.15, 0.15, 0.3, 0.1, 0.1])
        
        # Mostrar la información clave de la fila
        cols[0].write(row['Fecha'].strftime('%Y-%m-%d'))
        cols[1].write(row['Lugar'])
        cols[2].write(f"${row['Total Recibido']:,.0f}".replace(",", "."))
        cols[3].write(row['Paciente'])
        
        # --- BOTÓN DE EDICIÓN ---
        if cols[4].button("✏️", key=f"edit_{index}", help="Editar esta atención"):
            st.session_state.edit_index = index
            st.session_state.edited_lugar_state = row['Lugar'] # Inicializar el estado de edición del lugar
            st.rerun()

        # --- BOTÓN DE ELIMINACIÓN ---
        if cols[5].button("🗑️", key=f"delete_{index}", help="Eliminar esta atención de forma permanente"):
            st.session_state.atenciones_df = st.session_state.atenciones_df.drop(index)
            save_data(st.session_state.atenciones_df)
            st.success(f"Atención del paciente {row['Paciente']} eliminada. Recargando...")
            st.rerun()

    st.markdown("---") 
    
    # Botón de Descarga
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="⬇️ Descargar Datos Filtrados (CSV)",
        data=csv,
        file_name='reporte_control_ingresos_filtrado.csv',
        mime='text/csv',
    )
else:
    st.info("Aún no hay datos. Registra tu primera atención para ver el resumen.")

# ===============================================
# 5. MODAL DE EDICIÓN DE REGISTRO (CON GESTIÓN DE DEPENDENCIA)
# ===============================================

# Función de Callback para actualizar el estado del lugar
def update_edited_lugar():
    """Actualiza el lugar seleccionado inmediatamente y fuerza el re-renderizado del Ítem."""
    st.session_state.edited_lugar_state = st.session_state.edit_lugar

if st.session_state.edit_index is not None:
    
    index_to_edit = st.session_state.edit_index
    try:
        data_to_edit = st.session_state.atenciones_df.loc[index_to_edit]
    except KeyError:
        st.error("Error: El índice de la fila a editar no fue encontrado.")
        st.session_state.edit_index = None
        st.session_state.edited_lugar_state = None
        st.rerun()

    # Si el estado intermedio no está seteado (primera carga del modal), inicializarlo
    if st.session_state.edited_lugar_state is None:
        st.session_state.edited_lugar_state = data_to_edit['Lugar']

    with st.expander(f"📝 Editar Atención para {data_to_edit['Paciente']}", expanded=True):
        
        with st.form("edit_form", clear_on_submit=False):
            st.subheader("Modificar Datos de la Atención")
            
            col_edit1, col_edit2 = st.columns(2)

            with col_edit1:
                edited_fecha = st.date_input("🗓️ Fecha de Atención", value=data_to_edit['Fecha'].date())
                
                # --- WIDGET LUGAR CON CALLBACK ---
                try:
                    lugar_idx = LUGARES.index(st.session_state.edited_lugar_state)
                except ValueError:
                    lugar_idx = 0
                    
                edited_lugar = st.selectbox(
                    "📍 Lugar de Atención", 
                    options=LUGARES, 
                    index=lugar_idx, 
                    key="edit_lugar", # Clave para el valor dentro del form
                    on_change=update_edited_lugar # Llama a la función al cambiar
                )
                
                # --- WIDGET ÍTEM DEPENDIENTE DEL ESTADO INTERMEDIO ---
                
                # Usamos el lugar que está en el estado intermedio (edited_lugar_state)
                items_edit = list(PRECIOS_BASE_CONFIG.get(st.session_state.edited_lugar_state, {}).keys())
                
                # 1. Calcular el valor preseleccionado.
                try:
                    # Si el ítem original existe en la nueva lista de opciones
                    current_item_index = items_edit.index(data_to_edit['Ítem'])
                except ValueError:
                    # Si el ítem original NO existe en la lista actual, seleccionamos el primero (índice 0)
                    current_item_index = 0
                
                # 2. Clave dinámica: DEBE depender del lugar que está en el estado intermedio.
                item_key = f"edit_item_for_{st.session_state.edited_lugar_state}" 

                edited_item = st.selectbox(
                    "📋 Ítem/Procedimiento", 
                    options=items_edit, 
                    index=current_item_index, 
                    key=item_key 
                )
                
                # --- FIN DE DEPENDENCIA ---
                
                edited_paciente = st.text_input("👤 Nombre del Paciente", value=data_to_edit['Paciente'], key="edit_paciente")
                
                try:
                    pago_idx = METODOS_PAGO.index(data_to_edit['Método Pago'])
                except ValueError:
                    pago_idx = 0
                edited_metodo_pago = st.radio("💳 Método de Pago", options=METODOS_PAGO, index=pago_idx, key="edit_metodo")

            with col_edit2:
                edited_valor_bruto = st.number_input(
                    "💰 **Valor Bruto (Manual)**", 
                    min_value=0, 
                    value=int(data_to_edit['Valor Bruto']), 
                    step=1000,
                    key="edit_valor_bruto"
                )
                edited_desc_adicional_manual = st.number_input(
                    "✂️ **Descuento Adicional/Ajuste**", 
                    min_value=-500000, 
                    value=int(data_to_edit['Desc. Adicional']), 
                    step=1000,
                    key="edit_desc_adic"
                )
                
                # Recalcular el total líquido: USAMOS LOS VALORES DE LAS CLAVES DEL WIDGET (st.session_state.clave)
                # NOTA: Usamos el valor del Ítem y Lugar que están en el estado, ya que son los que se muestran
                recalculo = calcular_ingreso(
                    st.session_state.edit_lugar, 
                    st.session_state[item_key], # Usamos el valor del Ítem con la clave dinámica
                    st.session_state.edit_metodo, 
                    st.session_state.edit_desc_adic, 
                    fecha_atencion=edited_fecha, 
                    valor_bruto_override=st.session_state.edit_valor_bruto 
                )
                
                st.markdown("###")
                st.metric(
                    label="## NUEVO TOTAL LÍQUIDO", 
                    value=f"${recalculo['total_recibido']:,.0f}".replace(",", ".")
                )

            col_btn1, col_btn2 = st.columns([1, 1])

            # Botón de Guardar
            if col_btn1.form_submit_button("💾 Guardar Cambios y Actualizar", type="primary"):
                # 3. Guardar los cambios (Usamos los valores finales del state)
                st.session_state.atenciones_df.loc[index_to_edit] = {
                    "Fecha": edited_fecha.strftime('%Y-%m-%d'), 
                    "Lugar": st.session_state.edit_lugar, 
                    "Ítem": st.session_state[item_key], # Valor final del ítem
                    "Paciente": st.session_state.edit_paciente, 
                    "Método Pago": st.session_state.edit_metodo,
                    "Valor Bruto": recalculo['valor_bruto'],
                    "Desc. Fijo Lugar": recalculo['desc_fijo_lugar'],
                    "Desc. Tarjeta": recalculo['desc_tarjeta'],
                    "Desc. Adicional": st.session_state.edit_desc_adic,
                    "Total Recibido": recalculo['total_recibido']
                }
                
                save_data(st.session_state.atenciones_df)
                st.session_state.edit_index = None 
                st.session_state.edited_lugar_state = None 
                st.success(f"🎉 Atención para {st.session_state.edit_paciente} actualizada exitosamente. Recargando...")
                st.rerun()
                
            # Botón de Cancelar
            if col_btn2.form_submit_button("❌ Cancelar Edición"):
                st.session_state.edit_index = None 
                st.session_state.edited_lugar_state = None 
                st.rerun()
