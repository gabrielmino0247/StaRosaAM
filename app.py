import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import numpy as np
from api import consultar_magic_loops
import requests

# Configuración inicial
st.set_page_config(
    page_title="Dashboard Automotor", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Función universal para limpiar columnas numéricas
def limpiar_columnas_numericas(df, columnas):
    """Fuerza a numérico todas las columnas especificadas, reemplazando valores inválidos con 0"""
    df_clean = df.copy()
    for col in columnas:
        if col in df_clean.columns:
            try:
                valores_numericos = []
                for valor in df_clean[col]:
                    try:
                        valores_numericos.append(float(valor) if pd.notna(valor) else 0.0)
                    except (ValueError, TypeError):
                        valores_numericos.append(0.0)
                df_clean[col] = valores_numericos
            except Exception:
                df_clean[col] = 0.0
    return df_clean

# Función para cargar datos desde Dropbox
@st.cache_data
def cargar_datos():
    try:
        url_import = st.secrets["DROPBOX_IMPORT_URL"]
        url_matric = st.secrets["DROPBOX_MATRIC_URL"]

        # Cargar Excel directamente desde Dropbox
        df_import = pd.read_excel(url_import, sheet_name=0)
        df_matric = pd.read_excel(url_matric, sheet_name=0)

        # Procesamiento similar al de cargar.py
        df_import["Fecha"] = pd.to_datetime(df_import["Fecha"], errors="coerce")
        df_import = df_import.dropna(subset=["Fecha"])
        df_import["Año"] = df_import["Fecha"].dt.year
        df_import["Mes"] = df_import["Fecha"].dt.month
        df_import["Marca"] = df_import["Marca"].astype(str).str.strip().str.upper()
        if "Valor" in df_import.columns:
            df_import["Valor"] = pd.to_numeric(df_import["Valor"], errors="coerce").fillna(0)

        df_matric["fecha"] = pd.to_datetime(df_matric["fecha"], errors="coerce")
        df_matric = df_matric.dropna(subset=["fecha"])
        if "valor" in df_matric.columns:
            df_matric = df_matric.rename(columns={"valor": "VALOR"})
        elif "Valor" in df_matric.columns:
            df_matric = df_matric.rename(columns={"Valor": "VALOR"})
        df_matric["Año"] = df_matric["fecha"].dt.year
        df_matric["Mes"] = df_matric["fecha"].dt.month
        df_matric["Marca"] = df_matric["Marca"].astype(str).str.strip().str.upper()
        if "VALOR" in df_matric.columns:
            df_matric["VALOR"] = pd.to_numeric(df_matric["VALOR"], errors="coerce").fillna(0)

        return df_import, df_matric
    except Exception as e:
        st.error(f"Error al cargar datos desde Dropbox: {e}")
        st.stop()

# Función para mostrar estadísticas básicas
def mostrar_estadisticas(importaciones, matriculaciones):
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"""
        ** Importaciones**
        - Registros: {len(importaciones):,}
        - Periodo: {importaciones['Fecha'].min().strftime('%Y-%m-%d')} a {importaciones['Fecha'].max().strftime('%Y-%m-%d')}
        - Marcas: {importaciones['Marca'].nunique()}
        """)
    with col2:
        st.info(f"""
        ** Matriculaciones**
        - Registros: {len(matriculaciones):,}
        - Periodo: {matriculaciones['fecha'].min().strftime('%Y-%m-%d')} a {matriculaciones['fecha'].max().strftime('%Y-%m-%d')}
        - Marcas: {matriculaciones['Marca'].nunique()}
        """)

# Cargar datos
tuple_datos = cargar_datos()
if tuple_datos is None:
    st.error("❌ Error: No se pudieron cargar los datos")
    st.stop()
importaciones, matriculaciones = tuple_datos

# Sidebar de navegación
st.sidebar.title(" Dashboard Automotor")
pagina = st.sidebar.radio("Navegación", [
    " Resumen General", 
    " Comparativos Temporales",
    " Análisis por Marca",
    " Proyección de Matriculaciones",
    " Highlights"
])

# Filtros globales en sidebar
st.sidebar.markdown("---")
st.sidebar.header("🔍 Filtros")

# Filtro de fechas
try:
    fechas_todas = pd.concat([
        importaciones["Fecha"].dropna(),
        matriculaciones["fecha"].dropna()
    ])
    fecha_min = fechas_todas.min().date()
    fecha_max = fechas_todas.max().date()
    rango_fechas = st.sidebar.date_input(
        "Rango de fechas",
        value=[fecha_min, fecha_max],
        min_value=fecha_min,
        max_value=fecha_max
    )
    if len(rango_fechas) == 2:
        fecha_inicio, fecha_fin = rango_fechas
    elif len(rango_fechas) == 1:
        fecha_inicio = fecha_fin = rango_fechas[0]
    else:
        fecha_inicio = fecha_fin = fecha_min
except Exception as e:
    st.sidebar.error(f"Error en filtro de fechas: {e}")
    fecha_inicio = fecha_fin = datetime.now().date()

# Filtro de marcas
try:
    marcas_disponibles = sorted(
        set(importaciones["Marca"].dropna().unique()) | 
        set(matriculaciones["Marca"].dropna().unique())
    )
    marcas_seleccionadas = st.sidebar.multiselect(
        "Marcas",
        options=marcas_disponibles,
        default=marcas_disponibles[:10] if len(marcas_disponibles) > 10 else marcas_disponibles
    )
except Exception as e:
    st.sidebar.error(f"Error en filtro de marcas: {e}")
    marcas_seleccionadas = []

# === PÁGINA: RESUMEN GENERAL ===
if pagina == " Resumen General":
    st.title(" Resumen General")
    mostrar_estadisticas(importaciones, matriculaciones)
    try:
        imp_filtrado = importaciones[
            (importaciones["Fecha"].dt.date >= fecha_inicio) &
            (importaciones["Fecha"].dt.date <= fecha_fin) &
            (importaciones["Marca"].isin(marcas_seleccionadas))
        ] if marcas_seleccionadas else importaciones[
            (importaciones["Fecha"].dt.date >= fecha_inicio) &
            (importaciones["Fecha"].dt.date <= fecha_fin)
        ]
        mat_filtrado = matriculaciones[
            (matriculaciones["fecha"].dt.date >= fecha_inicio) &
            (matriculaciones["fecha"].dt.date <= fecha_fin) &
            (matriculaciones["Marca"].isin(marcas_seleccionadas))
        ] if marcas_seleccionadas else matriculaciones[
            (matriculaciones["fecha"].dt.date >= fecha_inicio) &
            (matriculaciones["fecha"].dt.date <= fecha_fin)
        ]
    except Exception as e:
        st.error(f"Error al filtrar datos: {e}")
        imp_filtrado = importaciones.copy()
        mat_filtrado = matriculaciones.copy()
    # Gráficos por marca
    if not imp_filtrado.empty and not mat_filtrado.empty:
        col1, col2 = st.columns(2)
        with col1:
            try:
                fig_imp = crear_grafico_marcas(imp_filtrado, "Valor", " Top 10 Marcas - Importaciones")
                st.plotly_chart(fig_imp, use_container_width=True)
            except Exception as e:
                st.error(f"Error en gráfico de importaciones: {e}")
        with col2:
            try:
                fig_mat = crear_grafico_marcas(mat_filtrado, "VALOR", " Top 10 Marcas - Matriculaciones")
                st.plotly_chart(fig_mat, use_container_width=True)
            except Exception as e:
                st.error(f"Error en gráfico de matriculaciones: {e}")
    # Detalles de datos
    with st.expander(" Ver Detalle de Importaciones"):
        if not imp_filtrado.empty:
            st.dataframe(
                imp_filtrado.sort_values(by="Fecha", ascending=False),
                use_container_width=True
            )
        else:
            st.info("No hay datos de importaciones para mostrar")
    with st.expander(" Ver Detalle de Matriculaciones"):
        if not mat_filtrado.empty:
            st.dataframe(
                mat_filtrado.sort_values(by="fecha", ascending=False),
                use_container_width=True
            )
        else:
            st.info("No hay datos de matriculaciones para mostrar")

# === PÁGINA: COMPARATIVOS TEMPORALES ===
elif pagina == " Comparativos Temporales":
    st.title(" Comparativos Temporales")
    st.markdown("**Análisis de tendencias y variaciones temporales**")
    try:
        if importaciones.empty or matriculaciones.empty:
            st.error("❌ No hay datos disponibles para el análisis temporal")
            st.stop()
        col_valor_imp = "Valor" if "Valor" in importaciones.columns else None
        col_valor_mat = "VALOR" if "VALOR" in matriculaciones.columns else None
        if not col_valor_imp or not col_valor_mat:
            st.error("❌ No se encontraron las columnas de valor necesarias")
            st.stop()
        st.success(f"✅ Columnas detectadas: Importaciones='{col_valor_imp}', Matriculaciones='{col_valor_mat}'")
        st.subheader(" Controles de Filtrado")
        imp_clean = importaciones[['Fecha', 'Marca', col_valor_imp]].copy()
        mat_clean = matriculaciones[['fecha', 'Marca', col_valor_mat]].copy()
        imp_clean['Fecha'] = pd.to_datetime(imp_clean['Fecha'], errors='coerce')
        mat_clean['fecha'] = pd.to_datetime(mat_clean['fecha'], errors='coerce')
        imp_clean[col_valor_imp] = pd.to_numeric(imp_clean[col_valor_imp], errors='coerce')
        mat_clean[col_valor_mat] = pd.to_numeric(mat_clean[col_valor_mat], errors='coerce')
        imp_clean[col_valor_imp] = imp_clean[col_valor_imp].fillna(0)
        mat_clean[col_valor_mat] = mat_clean[col_valor_mat].fillna(0)
        imp_clean = imp_clean.dropna(subset=['Fecha'])
        mat_clean = mat_clean.dropna(subset=['fecha'])
    except Exception as e:
        st.error(f"Error preparando datos: {e}")
        st.stop()
    # ... (resto de la lógica de la página, igual que antes)

# === PÁGINA: HIGHLIGHTS ===
elif pagina == " Highlights":
    st.title(" Destacados del Mes")
    user_query = st.text_input(
        "Consulta a la IA:",
        placeholder="Ejemplo: ¿Cómo está el desempeño de Jetour vs competidores chinos?"
    )
    if importaciones.empty or matriculaciones.empty:
        st.error("No hay datos disponibles para consultar. Por favor, carga los datos primero.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            años_disponibles = sorted(importaciones['Año'].unique())
            años_seleccionados = st.multiselect(
                "Años:",
                años_disponibles,
                default=[años_disponibles[-1]] if años_disponibles else [],
                help="Selecciona uno o más años para analizar"
            )
        with col2:
            if años_seleccionados:
                meses_disponibles = sorted(importaciones[importaciones['Año'].isin(años_seleccionados)]['Mes'].unique())
                meses_seleccionados = st.multiselect(
                    "Meses:",
                    meses_disponibles,
                    default=meses_disponibles,
                    help="Selecciona uno o más meses para analizar"
                )
            else:
                meses_seleccionados = []
        # ... (resto de la lógica de la página, igual que antes)

DROPBOX_URL = st.secrets["DROPBOX_DB_URL"]
DB_PATH = "automotor.db"

def descargar_db():
    if not os.path.exists(DB_PATH):
        print("Descargando base de datos desde Dropbox...")
        r = requests.get(DROPBOX_URL)
        with open(DB_PATH, "wb") as f:
            f.write(r.content)
        print("Base de datos descargada.")

descargar_db()