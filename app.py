import streamlit as st
import pandas as pd
from datetime import date
import io
# Se importa el módulo para trabajar con la conexión SQL de Streamlit
from streamlit import connections 
import time

# ===============================================
# CONFIGURACIÓN Y BASES DE DATOS (MAESTRAS)
# ===============================================

# --- Bases de Datos Maestras (Precios Brutos por Lugar + Item) ---
PRECIOS_BASE = {
    ('LIBEDUL', 'PACIENTE'): 4500,('LIBEDUL', 'VISITA ESTABLECIMIENTO'): 20000,('LIBEDUL', 'ADOS2'): 30000, ('LIBEDUL', 'DUPLA'): 7000, 
    ('LIBEDUL', 'ADIR+ADOS2'): 37500, ('LIBEDUL', 'LAVADO OIDO'): 6000,
    ('AMAR AUSTRAL', 'PACIENTE'): 30000,('AMAR AUSTRAL', 'DUPLA'): 25000,('AMAR AUSTRAL', 'LAVADO OIDO'): 20000,('AMAR AUSTRAL', 'VISITA ESTABLECIMIENTO'): 35000,('AMAR AUSTRAL', 'FALTO'): 0, ('AMAR AUSTRAL', 'ADIR+ADOS2'): 100000,
    ('CPM', 'PACIENTE'): 30000, ('CPM', 'HOSPITALIZADO'): 30000, ('CPM', 'ADIR+ADOS2'): 190000,
    ('DOMICILIO', 'PACIENTE'): 30000, ('DOMICILIO', 'LAVADO OIDO'): 25000,
    ('ALERCE', '5 SABADOS'): 25000, ('ALERCE', '4 SABADOS'): 31250,
}

# --- Reglas de Descuento (Fijas por Lugar) ---
DESCUENTOS_LUGAR = {
    'LIBEDUL': 0, 'ALERCE': 0, 'DOMICILIO': 0, 
    'CPM': 14610, 
}

# --- Reglas de Comisión por Método de Pago ---
COMISIONES_PAGO = {
    'EFECTIVO': 0.00, 'TRANSFERENCIA': 0.00, 'TARJETA': 0.05, 
}

# Variables de la aplicación
LUGARES = sorted(list(set(l for l, i in PRECIOS_BASE.keys())))
METODOS_PAGO = list(COMISIONES_PAGO.keys())

# ===============================================
# 2. FUNCIONES DE PERSISTENCIA (AÑADIDO PARA SUPABASE)
# ===============================================

# ¡SOLUCIÓN FINAL: CONEXIÓN DIRECTA USANDO EL POOLER DE SESIONES!
conn = st.connection(
    "supabase_pooler", 
    type="sql",
    dialect="postgresql",
    # HOST Y PUERTO DEL POOLER:
    host="aws-1-us-east-1.pooler.supabase.com", 
    port=5432, 
    database="postgres",
    # USUARIO COMPLETO (Pooler requiere la referencia del proyecto):
    username="postgres.emnqztaxybhbmkuryhem", 
    # CONTRASEÑA REAL:
    password="DomiLeo1702" # Asegúrate de que esta sea correcta
)
@st.cache_data(ttl=3600) # Carga los datos y los guarda en caché por 1 hora
def load_data_from_db():
    """Carga todos los datos de la tabla 'atenciones'."""
    try:
        df = conn.query('SELECT * FROM public."atenciones" ORDER BY "fecha" DESC;', ttl=600)
        # Asegura que las columnas numéricas sean float para los cálculos
        cols_to_numeric = ["valor_bruto", "desc_fijo_lugar", "desc_tarjeta", "desc_adicional", "total_recibido"]
        for col in cols_to_numeric:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Error al cargar datos de Supabase. Revisa la tabla y las credenciales. Error: {e}")
        return pd.DataFrame()

def save_data_to_db(nueva_atencion):
    """Inserta una nueva fila en la tabla 'atenciones'."""
    # Deshabilitar cache para asegurar que se inserta la nueva data
    load_data_from_db.clear()
    
    try:
        with conn.session as session:
            # Los nombres de las columnas en la consulta deben coincidir con la tabla de Supabase
            session.execute(
                """
                INSERT INTO atenciones 
                (fecha, lugar, item, paciente, metodo_pago, valor_bruto, desc_fijo_lugar, desc_tarjeta, desc_adicional, total_recibido) 
                VALUES 
                (:fecha, :lugar, :item, :paciente, :metodo_pago, :valor_bruto, :desc_fijo_lugar, :desc_tarjeta, :desc_adicional, :total_recibido);
                """,
                params=nueva_atencion
            )
            session.commit()
        return True
    except Exception as e:
        st.error(f"Error al guardar datos en Supabase. Asegúrate de que los tipos de datos en la tabla 'atenciones' sean correctos. Error: {e}")
        return False

# ===============================================
# 3. FUNCIÓN DE CÁLCULO
# ===============================================

def calcular_ingreso(lugar, item, metodo_pago, desc_adicional_manual, fecha_atencion, valor_bruto_override=None):
    """Calcula el ingreso final líquido, permitiendo valores negativos."""
    valor_bruto = valor_bruto_override if valor_bruto_override is not None else PRECIOS_BASE.get((lugar, item), 0)
    
    desc_fijo_lugar = DESCUENTOS_LUGAR.get(lugar, 0)
    
    # LÓGICA CONDICIONAL: AMAR AUSTRAL (Martes/Viernes)
    if lugar == 'AMAR AUSTRAL':
        dia_semana = fecha_atencion.weekday() # Lunes=0, Martes=1, Viernes=4
        if dia_semana == 1:  # Martes
            desc_fijo_lugar = 8000
        elif dia_semana == 4:  # Viernes
            desc_fijo_lugar = 6500

    comision_pct = COMISIONES_PAGO.get(metodo_pago, 0.00)
    desc_tarjeta = valor_bruto * comision_pct
    
    total_recibido = valor_bruto - desc_fijo_lugar - desc_tarjeta - desc_adicional_manual
    
    return {
        'valor_bruto': valor_bruto,
        'desc_fijo_lugar': desc_fijo_lugar,
        'desc_tarjeta': desc_tarjeta,
        'total_recibido': total_recibido # Permite negativos
    }

# ===============================================
# 4. INTERFAZ DE USUARIO (FRONTEND)
# ===============================================

st.set_page_config(page_title="Control de Ingresos Fonoaudiología", layout="wide")
st.title("💸 Sistema Interactivo de Ingreso de Atenciones")
st.markdown("---")

# Cargar los datos desde la BD al inicio de la sesión
df_global = load_data_from_db()
st.session_state.atenciones_df = df_global

# --- FORMULARIO DE INGRESO ---
with st.expander("➕ Ingresar Nueva Atención", expanded=True):
    col1, col2 = st.columns([1, 1])

    with col1:
        fecha = st.date_input("🗓️ Fecha de Atención", date.today())
        lugar_seleccionado = st.selectbox("📍 Lugar de Atención", options=LUGARES)
        
        items_filtrados = [item for (lugar, item), precio in PRECIOS_BASE.items() if lugar == lugar_seleccionado]
        item_seleccionado = st.selectbox("📋 Ítem/Procedimiento", options=items_filtrados)
        
        paciente = st.text_input("👤 Nombre del Paciente/Asociado", "")
        metodo_pago = st.radio("💳 Método de Pago", options=METODOS_PAGO)

    with col2:
        # Lógica de Cálculo
        precio_base = PRECIOS_BASE.get((lugar_seleccionado, item_seleccionado), 0)
        
        valor_bruto_input = st.number_input(
            "💰 **Valor Bruto (Sistema)**", min_value=0, value=int(precio_base), step=1000
        )

        desc_adicional_manual = st.number_input(
            "✂️ **Descuento Adicional/Ajuste**", min_value=-500000, value=0, step=1000, help="Negativo para cargos, positivo para descuentos."
        )
        
        resultados = calcular_ingreso(
            lugar_seleccionado, item_seleccionado, metodo_pago, desc_adicional_manual, fecha_atencion=fecha, valor_bruto_override=valor_bruto_input
        )
        
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
        if st.button("✅ Registrar Atención y Guardar en BD", use_container_width=True, type="primary"):
            if paciente == "":
                st.error("Por favor, ingresa el nombre del paciente.")
            else:
                nueva_atencion = {
                    "fecha": fecha.strftime('%Y-%m-%d'), 
                    "lugar": lugar_seleccionado, 
                    "item": item_seleccionado, 
                    "paciente": paciente, 
                    "metodo_pago": metodo_pago,
                    "valor_bruto": float(resultados['valor_bruto']),
                    "desc_fijo_lugar": float(resultados['desc_fijo_lugar']),
                    "desc_tarjeta": float(resultados['desc_tarjeta']),
                    "desc_adicional": float(desc_adicional_manual),
                    "total_recibido": float(resultados['total_recibido'])
                }
                
                if save_data_to_db(nueva_atencion):
                    st.success(f"🎉 Atención registrada para {paciente} por ${resultados['total_recibido']:,.0f}. (Guardado en Supabase)".replace(",", "."))
                    time.sleep(1) # Pequeña pausa para asegurar la recarga
                    st.rerun() # Recargar la página para ver el dashboard actualizado
                
# ===============================================
# 5. DASHBOARD DE RESUMEN
# ===============================================
st.markdown("---")
st.header("📊 Resumen y Análisis de Ingresos Histórico")

df = st.session_state.atenciones_df

if not df.empty:
    df['Fecha'] = pd.to_datetime(df['fecha']) # Usa 'fecha' de la DB
    
    total_liquido_historico = df["total_recibido"].sum()
    st.metric("Total Líquido Histórico", f"${total_liquido_historico:,.0f}".replace(",", "."))
    
    # Análisis Mensual
    df['Mes_Año'] = df['Fecha'].dt.to_period('M').astype(str)
    resumen_mensual = df.groupby('Mes_Año')['total_recibido'].sum().reset_index()
    
    st.subheader("Evolución Mensual de Ingresos Líquidos")
    # 
    st.bar_chart(resumen_mensual.set_index('Mes_Año'), color="#4c78a8")

    # Análisis por Lugar
    st.subheader("Distribución de Ingresos por Centro de Atención")
    resumen_lugar = df.groupby("lugar")["total_recibido"].sum().reset_index()
    # 
    st.dataframe(resumen_lugar, use_container_width=True)

    # Descarga de datos (todos los datos cargados de la BD)
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="⬇️ Descargar Todos los Datos Registrados (CSV)",
        data=csv,
        file_name='reporte_control_ingresos_supabase.csv',
        mime='text/csv',
    )
else:
    st.info("No se pudo cargar la base de datos o aún no hay datos registrados.")
