import streamlit as st
import pandas as pd
from datetime import date
import os
import io

# ===============================================
# CONFIGURACIÓN Y BASES DE DATOS (MAESTRAS)
# ===============================================

# --- Bases de Datos Maestras (Extraídas de Control Ingresos.xlsx - Atenciones.csv) ---
PRECIOS_BASE = {
    ('LIBEDUL', 'PACIENTE'): 4500, ('LIBEDUL', 'DUPLA'): 7000, 
    ('LIBEDUL', 'ADIR+ADOS2'): 37500, ('LIBEDUL', 'LAVADO OIDO'): 6000,
    ('AMAR AUSTRAL', 'PACIENTE'): 30000, ('AMAR AUSTRAL', 'ADIR+ADOS2'): 100000,
    ('CPM', 'PACIENTE'): 30000, ('CPM', 'ADIR+ADOS2'): 190000,
    ('DOMICILIO', 'PACIENTE'): 30000, ('DOMICILIO', 'LAVADO OIDO'): 25000,
    ('ALERCE', '5 SABADOS'): 25000, ('ALERCE', '4 SABADOS'): 31250,
}

# --- Reglas de Descuento (Fijas por Lugar) ---
DESCUENTOS_LUGAR = {
    'LIBEDUL': 0, 'ALERCE': 0, 'DOMICILIO': 0, 
    # El valor de AMAR AUSTRAL y CPM debe ser confirmado, este es un valor estimado por liquidación.
    'AMAR AUSTRAL': 5000, # Arriendo de box fijo.
    'CPM': 14610, # Esto refleja el 48.7% que queda líquido de los 30000.
}

# --- Reglas de Comisión por Método de Pago ---
COMISIONES_PAGO = {
    'EFECTIVO': 0.00,
    'TRANSFERENCIA': 0.00,
    'TARJETA': 0.05, # 5% de comisión.
}

LUGARES = sorted(list(set(l for l, i in PRECIOS_BASE.keys())))
METODOS_PAGO = list(COMISIONES_PAGO.keys())
DATA_FILE = 'atenciones_registradas.csv'

# ===============================================
# 2. FUNCIONES DE PERSISTENCIA Y CÁLCULO
# ===============================================

@st.cache_data
def load_data():
    """Carga los datos del archivo CSV o crea un DataFrame vacío si no existe."""
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    else:
        return pd.DataFrame(columns=[
            "Fecha", "Lugar", "Ítem", "Paciente", "Método Pago", 
            "Valor Bruto", "Desc. Fijo Lugar", "Desc. Tarjeta", 
            "Desc. Adicional", "Total Recibido"
        ])

def save_data(df):
    """Guarda el DataFrame actualizado en el archivo CSV."""
    df.to_csv(DATA_FILE, index=False)

def calcular_ingreso(lugar, item, metodo_pago, desc_adicional_manual, valor_bruto_override=None):
    """Calcula el ingreso final líquido."""
    valor_bruto = valor_bruto_override if valor_bruto_override is not None else PRECIOS_BASE.get((lugar, item), 0)
    
    desc_fijo_lugar = DESCUENTOS_LUGAR.get(lugar, 0)
    
    comision_pct = COMISIONES_PAGO.get(metodo_pago, 0.00)
    desc_tarjeta = valor_bruto * comision_pct
    
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
        'total_recibido': max(0, total_recibido)
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

# --- FORMULARIO DE INGRESO ---
with st.expander("➕ Ingresar Nueva Atención", expanded=True):
    col1, col2 = st.columns([1, 1])

    with col1:
        # Inputs para el registro
        fecha = st.date_input("🗓️ Fecha de Atención", date.today())
        lugar_seleccionado = st.selectbox("📍 Lugar de Atención", options=LUGARES)
        
        # Filtrado inteligente de ítems
        items_filtrados = [item for (lugar, item), precio in PRECIOS_BASE.items() if lugar == lugar_seleccionado]
        item_seleccionado = st.selectbox("📋 Ítem/Procedimiento", options=items_filtrados)
        
        paciente = st.text_input("👤 Nombre del Paciente/Asociado", "")
        metodo_pago = st.radio("💳 Método de Pago", options=METODOS_PAGO)

    with col2:
        # Lógica de Cálculo
        precio_base = PRECIOS_BASE.get((lugar_seleccionado, item_seleccionado), 0)
        
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
            valor_bruto_override=valor_bruto_input
        )
        
        # Mostrar el resultado final
        st.info(f"**Desc. Fijo Lugar:** ${resultados['desc_fijo_lugar']:,.0f}".replace(",", "."))
        st.warning(f"**Desc. Tarjeta ({COMISIONES_PAGO.get(metodo_pago, 0.00)*100:.0f}%):** ${resultados['desc_tarjeta']:,.0f}".replace(",", "."))
        
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
                
                # Agregar al DataFrame y guardar
                st.session_state.atenciones_df.loc[len(st.session_state.atenciones_df)] = nueva_atencion
                save_data(st.session_state.atenciones_df)
                st.success(f"🎉 Atención registrada para {paciente} por ${resultados['total_recibido']:,.0f}.".replace(",", "."))
                st.balloons()

# ===============================================
# 4. DASHBOARD DE RESUMEN
# ===============================================
st.markdown("---")
st.header("📊 Resumen y Análisis de Ingresos")

df = st.session_state.atenciones_df

if not df.empty:
    df['Fecha'] = pd.to_datetime(df['Fecha'])
    
    # Métricas principales
    total_liquido_historico = df["Total Recibido"].sum()
    st.metric("Total Líquido Histórico", f"${total_liquido_historico:,.0f}".replace(",", "."))
    
    # Análisis Mensual
    df['Mes_Año'] = df['Fecha'].dt.to_period('M').astype(str)
    resumen_mensual = df.groupby('Mes_Año')['Total Recibido'].sum().reset_index()
    
    # Mostrar Gráfico de Evolución Mensual 
    st.subheader("Evolución Mensual de Ingresos Líquidos")
    st.bar_chart(resumen_mensual.set_index('Mes_Año'), color="#4c78a8")

    # Análisis por Lugar (Tipo Torta)
    st.subheader("Distribución de Ingresos por Centro de Atención")
    resumen_lugar = df.groupby("Lugar")["Total Recibido"].sum().reset_index()
    # Muestra un gráfico de torta con la distribución de ingresos por lugar. 
    st.dataframe(resumen_lugar, use_container_width=True) # Mostrar tabla de datos

    # Descarga de datos
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="⬇️ Descargar Todos los Datos Registrados (CSV)",
        data=csv,
        file_name='reporte_control_ingresos.csv',
        mime='text/csv',
    )
else:
    st.info("Aún no hay datos. Registra tu primera atención para ver el resumen.")
