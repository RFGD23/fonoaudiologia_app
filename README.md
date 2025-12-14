# 💸 Sistema Interactivo de Control de Ingresos Fonoaudiología

Este proyecto es una aplicación web interactiva desarrollada con Streamlit y persistencia local (CSV) para el registro y análisis de atenciones fonoaudiológicas, aplicando reglas de negocio complejas (precios base, descuentos condicionales y comisiones) de manera automática.

## 🚀 Características Principales

* **Registro en Tiempo Real:** Interfaz simple para ingresar atenciones y pacientes.
* **Cálculo Automático:** Calcula el valor final **Líquido** automáticamente, aplicando descuentos por centro y comisiones por método de pago.
* **Análisis Detallado:** Dashboard con KPIs clave, evolución mensual de ingresos y distribución por centro de atención (Gráfico de Torta).
* **Mantenibilidad Modular:** Todas las reglas de negocio (precios y descuentos) se gestionan a través de archivos JSON, sin necesidad de modificar el código Python.

## ⚙️ Estructura del Proyecto

El proyecto está organizado de forma modular:

* `app.py`: El código principal de la aplicación Streamlit y la lógica de cálculo.
* `atenciones_registradas.csv`: Base de datos donde se guardan todas las atenciones registradas. **(Este archivo se genera automáticamente.)**
* `requirements.txt`: Lista de dependencias de Python (`streamlit`, `pandas`, `plotly`).
* **Archivos de Configuración (JSON):** Contienen las reglas de negocio editables.

## 🛠️ Cómo Actualizar las Reglas de Negocio

La gran ventaja de este sistema es que **no necesita tocar `app.py`** para cambiar precios o descuentos. Simplemente edite los archivos JSON:

### 1. `precios_base.json` (Precios Brutos por Lugar e Ítem)

Para cambiar el precio, modifique el valor asociado al par `Lugar` y `Ítem`:

```json
{
  "LIBEDUL": {
    "PACIENTE": 4500,
    "ADOS2": 30000 
  },
  "AMAR AUSTRAL": {
    "PACIENTE": 30000
    //...
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
