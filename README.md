# 💸 Sistema Interactivo de Control de Ingresos Fonoaudiología

Este proyecto es una aplicación web interactiva desarrollada con Streamlit y persistencia local (CSV) para el registro y análisis de atenciones fonoaudiológicas. Calcula automáticamente los ingresos netos aplicando reglas de negocio complejas (precios base, descuentos condicionales y comisiones).

## 🚀 Características Principales

* **Registro en Tiempo Real:** Interfaz simple para ingresar atenciones y pacientes.
* **Cálculo Automático:** Calcula el valor final **Líquido** automáticamente.
* **Análisis Multidimensional:** Dashboard con filtros interactivos por **Rango de Fecha, Centro de Atención** e **Ítem/Procedimiento**.
* **KPIs Detallados:** Muestra el Total Bruto, Total Líquido, Comisiones Pagadas y Descuentos Fijos Aplicados.
* **Mantenibilidad Modular:** Todas las reglas de negocio (precios y descuentos) se gestionan a través de archivos JSON, sin necesidad de modificar el código Python.

## ⚙️ Estructura del Proyecto

El proyecto está organizado de forma modular. Para su funcionamiento, es esencial contar con estos archivos en la raíz del repositorio:

* `app.py`: El código principal de la aplicación Streamlit y la lógica de cálculo.
* `atenciones_registradas.csv`: Base de datos donde se guardan todas las atenciones registradas.
* `requirements.txt`: Lista de dependencias de Python (`streamlit`, `pandas`, `plotly`).
* **Archivos de Configuración (JSON):** Contienen las reglas de negocio editables.

## 🏃‍♀️ Cómo Ejecutar la Aplicación Localmente

1.  **Clonar el Repositorio:**
    ```bash
    git clone [ENLACE_A_SU_REPOSITORIO]
    cd fonoaudiologia_app
    ```

2.  **Instalar Dependencias:** Asegúrese de tener Python instalado y luego ejecute:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Ejecutar Streamlit:**
    ```bash
    streamlit run app.py
    ```

## 📊 Guía de Uso del Dashboard

La sección de **Resumen y Análisis de Ingresos** ahora permite un análisis profundo mediante filtros combinables:

1.  **Filtros Dinámicos (Barra Lateral):** Use los selectores de **Centro de Atención** e **Ítem/Procedimiento** en la barra lateral izquierda para acotar los datos.
2.  **Filtro de Periodo (Cuerpo Principal):** Use los campos **Fecha de Inicio** y **Fecha de Fin** para limitar el análisis a un rango temporal específico.

**Nota:** Si los datos no se actualizan después de modificar los archivos JSON o CSV, use el botón **"🧹 Limpiar Caché y Recargar Datos"** en la barra lateral.

## 🛠️ Cómo Actualizar las Reglas de Negocio

La configuración se encuentra en los archivos JSON:

### 1. `precios_base.json` (Precios Brutos por Lugar e Ítem)

Modifique la estructura anidada `Lugar` -> `Ítem` -> `Precio` para cambiar los valores:

```json
{
  "LIBEDUL": {
    "PACIENTE": 4500,
    "ADOS2": 30000 
  },
  "AMAR AUSTRAL": {
    "PACIENTE": 30000
  }
}

2. descuentos_lugar.json (Descuento Fijo Base)
Modifique el valor del descuento fijo que se aplica por defecto en cada centro:
{
  "LIBEDUL": 0,
  "CPM": 14610 
}
3. comisiones_pago.json (Comisiones de Tarjeta)
Cambie el porcentaje de comisión (en formato decimal) para el método de pago:
{
  "TARJETA": 0.05, 
  "AMAR AUSTRAL": 0.05
}
🧠 Lógica de Negocio Condicional
La aplicación maneja la siguiente lógica específica en la función calcular_ingreso:
Centro	Condición	Regla
AMAR AUSTRAL	Día Martes	Aplica un descuento fijo de $8.000.
AMAR AUSTRAL	Día Viernes	Aplica un descuento fijo de $6.500.
Otros Días/Centros	N/A	Aplica el descuento fijo definido en descuentos_lugar.json.
