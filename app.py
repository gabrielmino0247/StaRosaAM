import streamlit as st
import pandas as pd
import sqlite3
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

# Función para verificar si existe la base de datos
def verificar_base_y_tablas():
    if not os.path.exists("automotor.db"):
        st.error("❌ No se encontró la base de datos 'automotor.db'")
        st.stop()
    try:
        conn = sqlite3.connect("automotor.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tablas = [tabla[0] for tabla in cursor.fetchall()]
        if "IMPORT_2019_2024" not in tablas or "MATRICULACION_ANUAL_" not in tablas:
            st.error("❌ Faltan tablas requeridas en la base de datos.")
            conn.close()
            st.stop()
        conn.close()
    except Exception as e:
        st.error(f"❌ Error al verificar la base de datos: {e}")
        st.stop()

# Función para cargar datos con manejo de errores
@st.cache_data
def cargar_datos():
    try:
        conn = sqlite3.connect("automotor.db")
        
        # Verificar que las tablas existen
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tablas = [tabla[0] for tabla in cursor.fetchall()]
        
        if "IMPORT_2019_2024" not in tablas:
            st.error("❌ Tabla IMPORT_2019_2024 no encontrada en la base de datos")
            conn.close()
            st.stop()
            
        if "MATRICULACION_ANUAL_" not in tablas:
            st.error("❌ Tabla MATRICULACION_ANUAL_ no encontrada en la base de datos")
            conn.close()
            st.stop()
        
        # Cargar datos
        importaciones = pd.read_sql_query(
            "SELECT * FROM IMPORT_2019_2024", 
            conn, 
            parse_dates=["Fecha"]
        )
        
        matriculaciones = pd.read_sql_query(
            "SELECT * FROM MATRICULACION_ANUAL_", 
            conn, 
            parse_dates=["fecha"]
        )
        
        conn.close()
        
        # Validar que los datos no estén vacíos
        if importaciones.empty:
            st.warning("⚠️ No hay datos de importaciones")
        if matriculaciones.empty:
            st.warning("⚠️ No hay datos de matriculaciones")
            
        # Asegura que las columnas existen
        if 'Año' not in importaciones.columns:
            importaciones['Año'] = importaciones['Fecha'].dt.year
        if 'Mes' not in importaciones.columns:
            importaciones['Mes'] = importaciones['Fecha'].dt.month
        if 'Año' not in matriculaciones.columns:
            matriculaciones['Año'] = matriculaciones['fecha'].dt.year
        if 'Mes' not in matriculaciones.columns:
            matriculaciones['Mes'] = matriculaciones['fecha'].dt.month
        
        return importaciones, matriculaciones
        
    except Exception as e:
        st.error(f"❌ Error al cargar datos: {e}")
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

# Función para crear gráficos de tendencia mejorada
def crear_grafico_tendencia(df_comp):
    fig = go.Figure()
    
    # Detectar nombres correctos de columnas
    valor_imp_col = "Valor" if "Valor" in df_comp.columns else "Valor_imp"
    valor_mat_col = "VALOR" if "VALOR" in df_comp.columns else "VALOR_mat"
    
    fig.add_trace(go.Scatter(
        x=df_comp['Fecha'],
        y=df_comp[valor_imp_col],
        mode='lines+markers',
        name='Importaciones',
        line=dict(color='#2E86AB', width=3),
        marker=dict(size=8),
        hovertemplate='<b>Importaciones</b><br>Fecha: %{x}<br>Valor: $%{y:,.0f}<extra></extra>'
    ))
    
    fig.add_trace(go.Scatter(
        x=df_comp['Fecha'],
        y=df_comp[valor_mat_col],
        mode='lines+markers',
        name='Matriculaciones',
        line=dict(color='#A23B72', width=3),
        marker=dict(size=8),
        hovertemplate='<b>Matriculaciones</b><br>Fecha: %{x}<br>Valor: $%{y:,.0f}<extra></extra>'
    ))
    
    fig.update_layout(
        title={
            'text': ' Tendencia Temporal: Importaciones vs Matriculaciones',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20}
        },
        xaxis_title='Fecha',
        yaxis_title='Valor ($)',
        hovermode='x unified',
        height=500,
        template='plotly_white',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig

# Función para crear gráficos de variaciones YoY, MoM, QoQ
def crear_graficos_variaciones(df_comp):
    """Crear gráficos separados para cada tipo de variación"""
    
    # Detectar nombres correctos de columnas
    valor_imp_col = "Valor" if "Valor" in df_comp.columns else "Valor_imp"
    valor_mat_col = "VALOR" if "VALOR" in df_comp.columns else "VALOR_mat"
    
    # Función mejorada para calcular variaciones
    def calcular_variaciones_seguras(df, col_imp, col_mat):
        try:
            df_var = df.copy()
            
            # LIMPIEZA NUMÉRICA INICIAL - GARANTIZAR TIPOS CORRECTOS
            df_var = limpiar_columnas_numericas(df_var, [col_imp, col_mat])
            
            # Calcular variaciones con manejo de errores
            def calcular_pct_change_seguro(series, periods):
                try:
                    # Reemplazar 0 con NaN temporalmente para evitar divisiones por cero
                    series_temp = series.replace(0, np.nan)
                    result = series_temp.pct_change(periods=periods) * 100
                    # Reemplazar infinitos con NaN
                    result = result.replace([np.inf, -np.inf], np.nan)
                    return result
                except:
                    return pd.Series([np.nan] * len(series), index=series.index)
            
            # Calcular variaciones YoY (12 meses)
            if len(df_var) >= 12:
                df_var["YoY_Imp"] = calcular_pct_change_seguro(df_var[col_imp], 12)
                df_var["YoY_Mat"] = calcular_pct_change_seguro(df_var[col_mat], 12)
            else:
                df_var["YoY_Imp"] = np.nan
                df_var["YoY_Mat"] = np.nan
            
            # Calcular variaciones MoM (1 mes)
            df_var["MoM_Imp"] = calcular_pct_change_seguro(df_var[col_imp], 1)
            df_var["MoM_Mat"] = calcular_pct_change_seguro(df_var[col_mat], 1)
            
            # Calcular variaciones QoQ (3 meses)
            if len(df_var) >= 3:
                df_var["QoQ_Imp"] = calcular_pct_change_seguro(df_var[col_imp], 3)
                df_var["QoQ_Mat"] = calcular_pct_change_seguro(df_var[col_mat], 3)
            else:
                df_var["QoQ_Imp"] = np.nan
                df_var["QoQ_Mat"] = np.nan
            
            # LIMPIEZA NUMÉRICA FINAL - TODAS LAS COLUMNAS DE VARIACIÓN
            columnas_variacion = ["YoY_Imp", "YoY_Mat", "MoM_Imp", "MoM_Mat", "QoQ_Imp", "QoQ_Mat"]
            df_var = limpiar_columnas_numericas(df_var, columnas_variacion)
            
            return df_var
            
        except Exception as e:
            st.error(f"Error calculando variaciones: {e}")
            return df

    # Función para crear gráfico de variaciones mejorado
    def crear_grafico_variacion_mejorado(df, col_imp, col_mat, titulo, color_imp, color_mat):
        try:
            # Los datos ya están limpios, no necesitamos conversiones adicionales
            # Filtrar datos válidos
            df_clean = df.dropna(subset=[col_imp, col_mat])
            if df_clean.empty:
                return None

            # Limitar valores extremos (opcional)
            def limpiar_outliers(series, limite=1000):
                if isinstance(series, pd.Series):
                    return series.clip(-limite, limite)
                else:
                    return series  # Si es escalar, lo devuelve tal cual

            df_clean[col_imp] = limpiar_outliers(df_clean[col_imp])
            df_clean[col_mat] = limpiar_outliers(df_clean[col_mat])

            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('Importaciones', 'Matriculaciones'),
                vertical_spacing=0.15,
                shared_xaxes=True
            )

            # Gráfico para Importaciones
            fig.add_trace(
                go.Bar(
                    x=df_clean['Fecha'],
                    y=df_clean[col_imp],
                    name='Importaciones',
                    marker_color=color_imp,
                    opacity=0.7,
                    hovertemplate='<b>Importaciones</b><br>Fecha: %{x}<br>Variación: %{y:.1f}%<extra></extra>'
                ),
                row=1, col=1
            )

            # Gráfico para Matriculaciones
            fig.add_trace(
                go.Bar(
                    x=df_clean['Fecha'],
                    y=df_clean[col_mat],
                    name='Matriculaciones',
                    marker_color=color_mat,
                    opacity=0.7,
                    hovertemplate='<b>Matriculaciones</b><br>Fecha: %{x}<br>Variación: %{y:.1f}%<extra></extra>'
                ),
                row=2, col=1
            )

            # Líneas de referencia en 0%
            for row_num in [1, 2]:
                fig.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5, row=str(row_num), col="1")

            fig.update_layout(
                title={
                    'text': titulo,
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18}
                },
                height=600,
                template='plotly_white',
                showlegend=True
            )

            fig.update_yaxes(title_text="Variación (%)", row=1, col=1)
            fig.update_yaxes(title_text="Variación (%)", row=2, col=1)
            fig.update_xaxes(title_text="Fecha", row=2, col=1)

            return fig

        except Exception as e:
            st.error(f"Error creando gráfico de variación: {e}")
            return None
    
    # Calcular variaciones
    df_comp = calcular_variaciones_seguras(df_comp, valor_imp_col, valor_mat_col)
    
    # Crear los tres gráficos
    fig_yoy = crear_grafico_variacion_mejorado(
        df_comp, "YoY_Imp", "YoY_Mat", 
        " Variación Año sobre Año (YoY)", 
        "#2E86AB", "#A23B72"
    )
    
    fig_mom = crear_grafico_variacion_mejorado(
        df_comp, "MoM_Imp", "MoM_Mat", 
        " Variación Mes sobre Mes (MoM)", 
        "#F18F01", "#C73E1D"
    )
    
    fig_qoq = crear_grafico_variacion_mejorado(
        df_comp, "QoQ_Imp", "QoQ_Mat", 
        " Variación Trimestre sobre Trimestre (QoQ)", 
        "#6A994E", "#BC4749"
    )
    
    return fig_yoy, fig_mom, fig_qoq, df_comp

def crear_grafico_marcas(df, valor_col, titulo):
    df_marcas = df.groupby('Marca')[valor_col].sum().sort_values(ascending=False).head(10)
    
    fig = px.bar(
        x=df_marcas.values,
        y=df_marcas.index,
        orientation='h',
        title=titulo,
        labels={'x': 'Unidades', 'y': 'Marca'},
        color=df_marcas.values,
        color_continuous_scale='viridis'
    )
    
    # Agregar etiquetas de datos en blanco
    fig.update_traces(
        texttemplate='%{x:,.0f}',
        textposition='outside',
        textfont=dict(color='white', size=12)
    )
    
    fig.update_layout(
        height=400,
        template='plotly_white',
        title={'x': 0.5, 'xanchor': 'center'},
        yaxis={'categoryorder': 'total ascending'}  # Ordenar de mayor a menor
    )
    return fig



# Cargar datos
try:
    resultado = cargar_datos()
    if resultado is None:
        st.error("❌ Error: No se pudieron cargar los datos")
        st.stop()
    importaciones, matriculaciones = resultado
except Exception as e:
    st.error(f"❌ Error al cargar datos: {e}")
    st.stop()
# Verificar base de datos
verificar_base_y_tablas()
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
    
    # CORREGIDO: Validar que rango_fechas no esté vacío
    if len(rango_fechas) == 2:
        fecha_inicio, fecha_fin = rango_fechas
    elif len(rango_fechas) == 1:
        fecha_inicio = fecha_fin = rango_fechas[0]
    else:
        # Si no hay fechas seleccionadas, usar fechas por defecto
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

# Función para descargar base de datos desde Dropbox
def descargar_db():
    try:
        DROPBOX_URL = st.secrets["DROPBOX_DB_URL"]
        DB_PATH = "automotor.db"
        if not os.path.exists(DB_PATH):
            with st.spinner("Descargando base de datos desde Dropbox..."):
                r = requests.get(DROPBOX_URL)
                r.raise_for_status()
                with open(DB_PATH, "wb") as f:
                    f.write(r.content)
            st.success("✅ Base de datos descargada exitosamente")
    except Exception as e:
        st.error(f"❌ Error al descargar la base de datos: {e}")
        st.stop()

# Descargar base de datos si no existe
descargar_db()

# === PÁGINA: RESUMEN GENERAL ===
if pagina == " Resumen General":
    st.title(" Resumen General")
    
    # Mostrar estadísticas básicas
    mostrar_estadisticas(importaciones, matriculaciones)
    
    # Aplicar filtros
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

    # KPIs
    try:
        total_import = imp_filtrado["Valor"].sum() if "Valor" in imp_filtrado.columns else 0
        total_mat = mat_filtrado["VALOR"].sum() if "VALOR" in mat_filtrado.columns else 0
        diferencia = total_import - total_mat
        ratio_mat_imp = (total_mat / total_import * 100) if total_import > 0 else 0
        
        st.markdown("###  Indicadores Clave")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Total Importaciones", 
                f"{total_import:,.0f}",
                help="Cantidad total de unidades importadas en el período seleccionado"
            )
        with col2:
            st.metric(
                "Total Matriculaciones", 
                f"{total_mat:,.0f}",
                help="Cantidad total de unidades matriculadas en el período seleccionado"
            )
        with col3:
            st.metric(
                "Diferencia",
                f"{diferencia:,.0f}",
                delta=f"{100 - ratio_mat_imp:.1f}%",
                help="Diferencia entre importaciones y matriculaciones (delta muestra % que falta matricular)"
            )
            
    except Exception as e:
        st.error(f"Error calculando KPIs: {e}")

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

# === PÁGINA: COMPARATIVOS TEMPORALES - VERSIÓN SIMPLE Y ROBUSTA ===

elif pagina == " Comparativos Temporales":
    st.title(" Comparativos Temporales")
    st.markdown("**Análisis de tendencias y variaciones temporales**")

    try:
        # Verificar datos básicos
        if importaciones.empty or matriculaciones.empty:
            st.error("❌ No hay datos disponibles para el análisis temporal")
            st.stop()

        # Detectar columnas automáticamente
        col_valor_imp = "Valor" if "Valor" in importaciones.columns else None
        col_valor_mat = "VALOR" if "VALOR" in matriculaciones.columns else None
        
        if not col_valor_imp or not col_valor_mat:
            st.error("❌ No se encontraron las columnas de valor necesarias")
            st.stop()

        st.success(f"✅ Columnas detectadas: Importaciones='{col_valor_imp}', Matriculaciones='{col_valor_mat}'")

        # === CONTROLES DE FILTRADO GLOBALES ===
        st.subheader(" Controles de Filtrado")
        
        # Preparar datos base para los controles
        imp_clean = importaciones[['Fecha', 'Marca', col_valor_imp]].copy()
        mat_clean = matriculaciones[['fecha', 'Marca', col_valor_mat]].copy()
        
        # Convertir fechas
        imp_clean['Fecha'] = pd.to_datetime(imp_clean['Fecha'], errors='coerce')
        mat_clean['fecha'] = pd.to_datetime(mat_clean['fecha'], errors='coerce')
        
        # Convertir valores a numérico
        imp_clean[col_valor_imp] = pd.to_numeric(imp_clean[col_valor_imp], errors='coerce')
        mat_clean[col_valor_mat] = pd.to_numeric(mat_clean[col_valor_mat], errors='coerce')
        
        # Rellenar valores nulos con 0
        imp_clean[col_valor_imp] = imp_clean[col_valor_imp].fillna(0)
        mat_clean[col_valor_mat] = mat_clean[col_valor_mat].fillna(0)
        
        # Eliminar filas con fechas inválidas
        imp_clean = imp_clean.dropna(subset=['Fecha'])
        mat_clean = mat_clean.dropna(subset=['fecha'])
        
        if imp_clean.empty or mat_clean.empty:
            st.error("❌ No hay datos válidos después de la limpieza")
            st.stop()

        # Agregar por fecha para obtener rango
        imp_trend = imp_clean.groupby('Fecha')[col_valor_imp].sum().reset_index()
        mat_trend = mat_clean.groupby('fecha')[col_valor_mat].sum().reset_index()
        mat_trend = mat_trend.rename(columns={'fecha': 'Fecha'})
        
        # Combinar datos para rango completo
        df_trend = pd.merge(imp_trend, mat_trend, on='Fecha', how='outer').fillna(0)
        df_trend = df_trend.sort_values('Fecha')
        
        # Control deslizante para rango de fechas
        fecha_min = df_trend['Fecha'].min().date()
        fecha_max = df_trend['Fecha'].max().date()
        
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            rango_fechas = st.slider(
                " Rango de fechas",
                min_value=fecha_min,
                max_value=fecha_max,
                value=(fecha_min, fecha_max),
                format="YYYY-MM-DD"
            )
        
        with col2:
            # Obtener marcas disponibles
            marcas_imp = sorted(imp_clean['Marca'].unique())
            marcas_mat = sorted(mat_clean['Marca'].unique())
            marcas_todas = sorted(list(set(marcas_imp + marcas_mat)))
            
            marcas_seleccionadas = st.multiselect(
                " Seleccionar Marcas",
                options=marcas_todas,
                default=marcas_todas[:10] if len(marcas_todas) > 10 else marcas_todas,
                help="Selecciona las marcas que quieres analizar"
            )
        
        with col3:
            st.write("**Período seleccionado:**")
            st.write(f"Desde: {rango_fechas[0].strftime('%Y-%m-%d')}")
            st.write(f"Hasta: {rango_fechas[1].strftime('%Y-%m-%d')}")
            st.write(f"Marcas: {len(marcas_seleccionadas)}")

        # Filtrar datos por fecha y marca
        imp_filtrado = imp_clean[
            (imp_clean['Fecha'].dt.date >= rango_fechas[0]) & 
            (imp_clean['Fecha'].dt.date <= rango_fechas[1]) &
            (imp_clean['Marca'].isin(marcas_seleccionadas))
        ]
        
        mat_filtrado = mat_clean[
            (mat_clean['fecha'].dt.date >= rango_fechas[0]) & 
            (mat_clean['fecha'].dt.date <= rango_fechas[1]) &
            (mat_clean['Marca'].isin(marcas_seleccionadas))
        ]

        # === 1. GRÁFICO DE TENDENCIA CON CONTROL DESLIZANTE ===
        st.subheader(" Tendencia Temporal")
        
        try:
            # Agregar por fecha usando datos filtrados
            imp_trend_filtrado = imp_filtrado.groupby('Fecha')[col_valor_imp].sum().reset_index()
            mat_trend_filtrado = mat_filtrado.groupby('fecha')[col_valor_mat].sum().reset_index()
            mat_trend_filtrado = mat_trend_filtrado.rename(columns={'fecha': 'Fecha'})
            
            # Combinar datos
            df_trend_final = pd.merge(imp_trend_filtrado, mat_trend_filtrado, on='Fecha', how='outer').fillna(0)
            df_trend_final = df_trend_final.sort_values('Fecha')
            
            # Crear gráfico de tendencia
            fig_trend = go.Figure()
            
            fig_trend.add_trace(go.Scatter(
                x=df_trend_final['Fecha'],
                y=df_trend_final[col_valor_imp],
                    mode='lines+markers+text',
                    name='Importaciones',
                    line=dict(color='#2E86AB', width=3),
                marker=dict(size=6),
                    text=df_trend_final[col_valor_imp].apply(lambda x: f'{x:,.0f}' if x > 0 else ''),
                    textposition='top center',
                    textfont=dict(color='#2E86AB', size=15),
                    hovertemplate='<b>Importaciones</b><br>Fecha: %{x}<br>Valor: $%{y:,.0f}<extra></extra>'
                ))
                
            fig_trend.add_trace(go.Scatter(
                x=df_trend_final['Fecha'],
                y=df_trend_final[col_valor_mat],
                    mode='lines+markers+text',
                    name='Matriculaciones',
                    line=dict(color='#A23B72', width=3),
                marker=dict(size=6),
                    text=df_trend_final[col_valor_mat].apply(lambda x: f'{x:,.0f}' if x > 0 else ''),
                    textposition='bottom center',
                    textfont=dict(color='#A23B72', size=15),
                    hovertemplate='<b>Matriculaciones</b><br>Fecha: %{x}<br>Valor: $%{y:,.0f}<extra></extra>'
                ))
            
            fig_trend.update_layout(
                title=' Tendencia: Importaciones vs Matriculaciones',
                xaxis_title='Fecha',
                yaxis_title='Valor ($)',
                height=500,
                template='plotly_white',
                hovermode='x unified',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig_trend, use_container_width=True)
            
        except Exception as e:
            st.error(f"❌ Error en gráfico de tendencia: {e}")
            st.stop()

        # === 2. COMPARATIVOS MENSUALES POR MARCA (MoM%) ===
        st.subheader(" Comparativos Mensuales por Marca")
        
        try:
            # Preparar datos mensuales por marca usando datos filtrados
            imp_mensual = imp_filtrado.copy()
            mat_mensual = mat_filtrado.copy()
            
            # Agregar columnas de año y mes
            imp_mensual['Año'] = imp_mensual['Fecha'].dt.year
            imp_mensual['Mes'] = imp_mensual['Fecha'].dt.month
            mat_mensual['Año'] = mat_mensual['fecha'].dt.year
            mat_mensual['Mes'] = mat_mensual['fecha'].dt.month
            
            # Agregar por marca, año y mes
            imp_agg = imp_mensual.groupby(['Marca', 'Año', 'Mes'])[col_valor_imp].sum().reset_index()
            mat_agg = mat_mensual.groupby(['Marca', 'Año', 'Mes'])[col_valor_mat].sum().reset_index()
            
            # Crear fechas para ordenamiento - CORREGIDO
            def crear_fecha_segura(df):
                fechas = []
                for _, row in df.iterrows():
                    try:
                        fecha = datetime(int(row['Año']), int(row['Mes']), 1)
                        fechas.append(fecha)
                    except (ValueError, TypeError):
                        fechas.append(pd.NaT)
                return pd.Series(fechas, index=df.index)
            
            imp_agg['Fecha'] = crear_fecha_segura(imp_agg)
            mat_agg['Fecha'] = crear_fecha_segura(mat_agg)
            
            # Eliminar fechas inválidas
            imp_agg = imp_agg.dropna(subset=['Fecha'])
            mat_agg = mat_agg.dropna(subset=['Fecha'])
            
            # Ordenar por fecha
            imp_agg = imp_agg.sort_values(['Marca', 'Fecha'])
            mat_agg = mat_agg.sort_values(['Marca', 'Fecha'])
            
            # Calcular MoM% para importaciones
            imp_agg['Valor_Anterior'] = imp_agg.groupby('Marca')[col_valor_imp].shift(1)
            imp_agg['MoM_%'] = ((imp_agg[col_valor_imp] - imp_agg['Valor_Anterior']) / imp_agg['Valor_Anterior'] * 100).fillna(0)
            
            # Calcular MoM% para matriculaciones
            mat_agg['Valor_Anterior'] = mat_agg.groupby('Marca')[col_valor_mat].shift(1)
            mat_agg['MoM_%'] = ((mat_agg[col_valor_mat] - mat_agg['Valor_Anterior']) / mat_agg['Valor_Anterior'] * 100).fillna(0)
            
            # Obtener top 10 marcas por valor total
            top_marcas_imp = imp_agg.groupby('Marca')[col_valor_imp].sum().sort_values(ascending=False).head(10).index.tolist()
            top_marcas_mat = mat_agg.groupby('Marca')[col_valor_mat].sum().sort_values(ascending=False).head(10).index.tolist()
            
            # Filtrar por top marcas
            imp_top = imp_agg[imp_agg['Marca'].isin(top_marcas_imp)]
            mat_top = mat_agg[mat_agg['Marca'].isin(top_marcas_mat)]
            
            # Crear gráfico de columnas agrupadas para MoM%
            fig_mom = go.Figure()
            
            # Agregar barras para importaciones
            for marca in top_marcas_imp[:5]:  # Top 5 para claridad
                datos_marca = imp_top[imp_top['Marca'] == marca].tail(12)  # Últimos 12 meses
                if not datos_marca.empty:
                    fig_mom.add_trace(go.Bar(
                        name=f'{marca} (Imp)',
                        x=datos_marca['Fecha'],
                        y=datos_marca['MoM_%'],
                        marker_color='#2E86AB',
                        opacity=0.7,
                        text=datos_marca['MoM_%'].apply(lambda x: f'{x:.1f}%' if abs(x) > 5 else ''),  # Solo mostrar variaciones significativas
                        textposition='outside',
                        textfont=dict(color='#FFFFFF', size=18),
                        hovertemplate=f'<b>{marca}</b><br>Fecha: %{{x}}<br>MoM: %{{y:.1f}}%<extra></extra>'
                    ))
            
            # Agregar barras para matriculaciones
            for marca in top_marcas_mat[:5]:  # Top 5 para claridad
                datos_marca = mat_top[mat_top['Marca'] == marca].tail(12)  # Últimos 12 meses
                if not datos_marca.empty:
                    fig_mom.add_trace(go.Bar(
                        name=f'{marca} (Mat)',
                        x=datos_marca['Fecha'],
                        y=datos_marca['MoM_%'],
                        marker_color='#A23B72',
                        opacity=0.7,
                        text=datos_marca['MoM_%'].apply(lambda x: f'{x:.1f}%' if abs(x) > 5 else ''),  # Solo mostrar variaciones significativas
                        textposition='outside',
                        textfont=dict(color='#FFFFFF', size=18),
                        hovertemplate=f'<b>{marca}</b><br>Fecha: %{{x}}<br>MoM: %{{y:.1f}}%<extra></extra>'
                    ))
            
            fig_mom.update_layout(
                title=' Variación Mes sobre Mes (MoM%) - Top 5 Marcas',
                xaxis_title='Fecha',
                yaxis_title='Variación MoM (%)',
                height=500,
                template='plotly_white',
                barmode='group',
                showlegend=True
            )
            
            # Agregar línea de referencia en 0%
            fig_mom.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5)
            
            st.plotly_chart(fig_mom, use_container_width=True)
            
        except Exception as e:
            st.error(f"❌ Error en comparativos mensuales: {e}")

        # === 3. COMPARACIÓN YOY ===
        st.subheader(" Comparación Año sobre Año (YoY%)")
        
        try:
            # === FILTRO ESPECÍFICO PARA YOY ===
            st.markdown("** Selector de mes para comparación YoY:**")
            
            # Crear una copia completa de los datos originales para YoY
            imp_yoy_df = importaciones.copy()
            mat_yoy_df = matriculaciones.copy()
            
            # Asegurar que las columnas de fecha estén en formato datetime
            imp_yoy_df['Fecha'] = pd.to_datetime(imp_yoy_df['Fecha'], errors='coerce')
            mat_yoy_df['fecha'] = pd.to_datetime(mat_yoy_df['fecha'], errors='coerce')
            
            # Agregar columnas de año y mes
            imp_yoy_df['Año'] = imp_yoy_df['Fecha'].dt.year
            imp_yoy_df['Mes'] = imp_yoy_df['Fecha'].dt.month
            mat_yoy_df['Año'] = mat_yoy_df['fecha'].dt.year
            mat_yoy_df['Mes'] = mat_yoy_df['fecha'].dt.month
            
            # Limpiar valores numéricos
            imp_yoy_df = limpiar_columnas_numericas(imp_yoy_df, [col_valor_imp])
            mat_yoy_df = limpiar_columnas_numericas(mat_yoy_df, [col_valor_mat])
            
            # Eliminar filas con fechas inválidas
            imp_yoy_df = imp_yoy_df.dropna(subset=['Fecha'])
            mat_yoy_df = mat_yoy_df.dropna(subset=['fecha'])
            
            # Obtener años y meses disponibles
            años_disponibles_yoy = sorted(imp_yoy_df['Año'].unique())
            meses_disponibles_yoy = sorted(imp_yoy_df['Mes'].unique())
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Selector de año
                año_seleccionado_yoy = st.selectbox(
                    " Seleccionar Año:",
                    options=años_disponibles_yoy,
                    index=len(años_disponibles_yoy)-1 if len(años_disponibles_yoy) > 0 else 0,
                    key="yoy_year_selector"
                )
            
            with col2:
                # Selector de mes
                mes_seleccionado_yoy = st.selectbox(
                    " Seleccionar Mes:",
                    options=meses_disponibles_yoy,
                    index=0 if len(meses_disponibles_yoy) > 0 else 0,
                    key="yoy_month_selector"
                )
            
            # Mostrar período seleccionado
            st.info(f"** Comparando:** {mes_seleccionado_yoy:02d}-{año_seleccionado_yoy} vs {mes_seleccionado_yoy:02d}-{año_seleccionado_yoy-1}")
            st.info("💡 **Nota:** El análisis YoY muestra todas las marcas disponibles, ignorando el filtro de marcas para una comparación completa")
            
            # NO filtrar por marca - usar todos los datos disponibles para YoY
            imp_yoy_filtrado = imp_yoy_df.copy()
            mat_yoy_filtrado = mat_yoy_df.copy()
            
            # Agregar por marca, año y mes
            imp_yoy_agg = imp_yoy_filtrado.groupby(['Marca', 'Año', 'Mes'])[col_valor_imp].sum().reset_index()
            mat_yoy_agg = mat_yoy_filtrado.groupby(['Marca', 'Año', 'Mes'])[col_valor_mat].sum().reset_index()
            
            # Crear fechas para ordenamiento
            def crear_fecha_segura(df):
                fechas = []
                for _, row in df.iterrows():
                    try:
                        fecha = datetime(int(row['Año']), int(row['Mes']), 1)
                        fechas.append(fecha)
                    except (ValueError, TypeError):
                        fechas.append(pd.NaT)
                return pd.Series(fechas, index=df.index)
            
            imp_yoy_agg['Fecha'] = crear_fecha_segura(imp_yoy_agg)
            mat_yoy_agg['Fecha'] = crear_fecha_segura(mat_yoy_agg)
            
            # Eliminar fechas inválidas
            imp_yoy_agg = imp_yoy_agg.dropna(subset=['Fecha'])
            mat_yoy_agg = mat_yoy_agg.dropna(subset=['Fecha'])
            
            # Obtener datos del mes seleccionado y del año anterior
            imp_mes_actual = imp_yoy_agg[
                (imp_yoy_agg['Año'] == año_seleccionado_yoy) & 
                (imp_yoy_agg['Mes'] == mes_seleccionado_yoy)
            ]
            
            imp_mes_anterior = imp_yoy_agg[
                (imp_yoy_agg['Año'] == año_seleccionado_yoy - 1) & 
                (imp_yoy_agg['Mes'] == mes_seleccionado_yoy)
            ]
            
            mat_mes_actual = mat_yoy_agg[
                (mat_yoy_agg['Año'] == año_seleccionado_yoy) & 
                (mat_yoy_agg['Mes'] == mes_seleccionado_yoy)
            ]
            
            mat_mes_anterior = mat_yoy_agg[
                (mat_yoy_agg['Año'] == año_seleccionado_yoy - 1) & 
                (mat_yoy_agg['Mes'] == mes_seleccionado_yoy)
            ]
            
            # Combinar datos para comparación
            def combinar_datos_actual_anterior(actual, anterior, tipo):
                if actual.empty and anterior.empty:
                    return pd.DataFrame()
                
                # Obtener marcas únicas
                marcas_actual = set(actual['Marca'].unique()) if not actual.empty else set()
                marcas_anterior = set(anterior['Marca'].unique()) if not anterior.empty else set()
                marcas_todas = marcas_actual | marcas_anterior
                
                datos_combinados = []
                for marca in marcas_todas:
                    valor_actual = actual[actual['Marca'] == marca][col_valor_imp if tipo == 'imp' else col_valor_mat].sum() if not actual.empty else 0
                    valor_anterior = anterior[anterior['Marca'] == marca][col_valor_imp if tipo == 'imp' else col_valor_mat].sum() if not anterior.empty else 0
                    
                    # Calcular variación YoY
                    variacion_yoy = ((valor_actual - valor_anterior) / valor_anterior * 100) if valor_anterior > 0 else 0
                    
                    datos_combinados.append({
                        'Marca': marca,
                        f'Valor_{año_seleccionado_yoy-1}': valor_anterior,
                        f'Valor_{año_seleccionado_yoy}': valor_actual,
                        'Variacion_YoY': variacion_yoy
                    })
                
                return pd.DataFrame(datos_combinados)
            
            # Crear DataFrames combinados
            imp_comparacion = combinar_datos_actual_anterior(imp_mes_actual, imp_mes_anterior, 'imp')
            mat_comparacion = combinar_datos_actual_anterior(mat_mes_actual, mat_mes_anterior, 'mat')
            
            # Mostrar métricas resumidas
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_imp_actual = imp_comparacion[f'Valor_{año_seleccionado_yoy}'].sum() if not imp_comparacion.empty else 0
                st.metric(f"Importaciones {año_seleccionado_yoy}", f"{total_imp_actual:,.0f}")
                                
            with col2:
                total_imp_anterior = imp_comparacion[f'Valor_{año_seleccionado_yoy-1}'].sum() if not imp_comparacion.empty else 0
                st.metric(f"Importaciones {año_seleccionado_yoy-1}", f"{total_imp_anterior:,.0f}")
            
            with col3:
                total_mat_actual = mat_comparacion[f'Valor_{año_seleccionado_yoy}'].sum() if not mat_comparacion.empty else 0
                st.metric(f"Matriculaciones {año_seleccionado_yoy}", f"{total_mat_actual:,.0f}")
            
            with col4:
                total_mat_anterior = mat_comparacion[f'Valor_{año_seleccionado_yoy-1}'].sum() if not mat_comparacion.empty else 0
                st.metric(f"Matriculaciones {año_seleccionado_yoy-1}", f"{total_mat_anterior:,.0f}")
            
            # Crear gráfico de líneas para comparación YoY
            if not imp_comparacion.empty or not mat_comparacion.empty:
                # Crear subplots: uno para importaciones y otro para matriculaciones
                fig_yoy = make_subplots(
                    rows=2, cols=1,
                    subplot_titles=('Importaciones', 'Matriculaciones'),
                    vertical_spacing=0.15,
                    shared_xaxes=True
                )
                
                # Combinar datos de importaciones y matriculaciones para obtener top marcas
                todas_las_marcas = set()
                if not imp_comparacion.empty:
                    todas_las_marcas.update(imp_comparacion['Marca'].tolist())
                if not mat_comparacion.empty:
                    todas_las_marcas.update(mat_comparacion['Marca'].tolist())
                
                # Crear DataFrame combinado para el gráfico
                datos_grafico = []
                for marca in todas_las_marcas:
                    # Obtener datos de importaciones
                    imp_actual = imp_comparacion[imp_comparacion['Marca'] == marca][f'Valor_{año_seleccionado_yoy}'].sum() if not imp_comparacion.empty else 0
                    imp_anterior = imp_comparacion[imp_comparacion['Marca'] == marca][f'Valor_{año_seleccionado_yoy-1}'].sum() if not imp_comparacion.empty else 0
                    
                    # Obtener datos de matriculaciones
                    mat_actual = mat_comparacion[mat_comparacion['Marca'] == marca][f'Valor_{año_seleccionado_yoy}'].sum() if not mat_comparacion.empty else 0
                    mat_anterior = mat_comparacion[mat_comparacion['Marca'] == marca][f'Valor_{año_seleccionado_yoy-1}'].sum() if not mat_comparacion.empty else 0
                    
                    datos_grafico.append({
                        'Marca': marca,
                        f'Imp_{año_seleccionado_yoy-1}': imp_anterior,
                        f'Imp_{año_seleccionado_yoy}': imp_actual,
                        f'Mat_{año_seleccionado_yoy-1}': mat_anterior,
                        f'Mat_{año_seleccionado_yoy}': mat_actual
                    })
                
                df_grafico = pd.DataFrame(datos_grafico)
                
                # Obtener top 10 marcas por valor total (importaciones + matriculaciones del año actual)
                df_grafico['Total_Actual'] = df_grafico[f'Imp_{año_seleccionado_yoy}'] + df_grafico[f'Mat_{año_seleccionado_yoy}']
                top_marcas_grafico = df_grafico.nlargest(10, 'Total_Actual')['Marca'].tolist()
                df_grafico_top = df_grafico[df_grafico['Marca'].isin(top_marcas_grafico)]
                
                # Crear posiciones para las barras (cada marca tendrá 2 barras)
                posiciones = list(range(len(df_grafico_top)))
                
                # === GRÁFICO DE IMPORTACIONES ===
                # Barras para año anterior (importaciones)
                fig_yoy.add_trace(go.Bar(
                    x=df_grafico_top['Marca'],
                    y=df_grafico_top[f'Imp_{año_seleccionado_yoy-1}'],
                    name=f'Importaciones {año_seleccionado_yoy-1}',
                    marker_color='#2E86AB',
                    opacity=0.7,
                    text=df_grafico_top[f'Imp_{año_seleccionado_yoy-1}'].apply(lambda x: f'{x:,.0f}' if x > 0 else ''),
                    textposition='outside',
                    textfont=dict(color='#FFFFFF', size=15),
                    hovertemplate='<b>%{x}</b><br>Importaciones %{fullData.name}<br>Valor: %{y:,.0f}<extra></extra>'
                ), row=1, col=1)
                
                # Barras para año actual (importaciones)
                fig_yoy.add_trace(go.Bar(
                    x=df_grafico_top['Marca'],
                    y=df_grafico_top[f'Imp_{año_seleccionado_yoy}'],
                    name=f'Importaciones {año_seleccionado_yoy}',
                    marker_color='#2E86AB',
                    opacity=1.0,
                    text=df_grafico_top[f'Imp_{año_seleccionado_yoy}'].apply(lambda x: f'{x:,.0f}' if x > 0 else ''),
                    textposition='outside',
                    textfont=dict(color='#FFFFFF', size=15),
                    hovertemplate='<b>%{x}</b><br>Importaciones %{fullData.name}<br>Valor: %{y:,.0f}<extra></extra>'
                ), row=1, col=1)
                
                # === GRÁFICO DE MATRICULACIONES ===
                # Barras para año anterior (matriculaciones)
                fig_yoy.add_trace(go.Bar(
                    x=df_grafico_top['Marca'],
                    y=df_grafico_top[f'Mat_{año_seleccionado_yoy-1}'],
                    name=f'Matriculaciones {año_seleccionado_yoy-1}',
                    marker_color='#A23B72',
                    opacity=0.7,
                    text=df_grafico_top[f'Mat_{año_seleccionado_yoy-1}'].apply(lambda x: f'{x:,.0f}' if x > 0 else ''),
                    textposition='outside',
                    textfont=dict(color='#FFFFFF', size=15),
                    hovertemplate='<b>%{x}</b><br>Matriculaciones %{fullData.name}<br>Valor: %{y:,.0f}<extra></extra>'
                ), row=2, col=1)
                
                # Barras para año actual (matriculaciones)
                fig_yoy.add_trace(go.Bar(
                    x=df_grafico_top['Marca'],
                    y=df_grafico_top[f'Mat_{año_seleccionado_yoy}'],
                    name=f'Matriculaciones {año_seleccionado_yoy}',
                    marker_color='#A23B72',
                    opacity=1.0,
                    text=df_grafico_top[f'Mat_{año_seleccionado_yoy}'].apply(lambda x: f'{x:,.0f}' if x > 0 else ''),
                    textposition='outside',
                    textfont=dict(color='#FFFFFF', size=15),
                    hovertemplate='<b>%{x}</b><br>Matriculaciones %{fullData.name}<br>Valor: %{y:,.0f}<extra></extra>'
                ), row=2, col=1)
                
                # === LÍNEAS DE CONEXIÓN PARA IMPORTACIONES ===
                for i, (_, row) in enumerate(df_grafico_top.iterrows()):
                    # Línea que conecta las barras de importaciones
                    fig_yoy.add_trace(go.Scatter(
                        x=[row['Marca'], row['Marca']],
                        y=[row[f'Imp_{año_seleccionado_yoy-1}'], row[f'Imp_{año_seleccionado_yoy}']],
                        mode='lines',
                        line=dict(color='#2E86AB', width=3, dash='solid'),
                        showlegend=False,
                        hoverinfo='skip'
                    ), row=1, col=1)
                    
                    # Agregar flecha o marcador en el punto final
                    variacion_imp = ((row[f'Imp_{año_seleccionado_yoy}'] - row[f'Imp_{año_seleccionado_yoy-1}']) / row[f'Imp_{año_seleccionado_yoy-1}'] * 100) if row[f'Imp_{año_seleccionado_yoy-1}'] > 0 else 0
                    color_flecha = 'green' if variacion_imp > 0 else 'red' if variacion_imp < 0 else 'gray'
                    
                    fig_yoy.add_trace(go.Scatter(
                        x=[row['Marca']],
                        y=[row[f'Imp_{año_seleccionado_yoy}']],
                        mode='markers',
                        marker=dict(
                            symbol='arrow-up' if variacion_imp > 0 else 'arrow-down' if variacion_imp < 0 else 'circle',
                            size=12,
                            color=color_flecha
                        ),
                        showlegend=False,
                        hovertemplate=f'<b>{row["Marca"]}</b><br>Variación: {variacion_imp:.1f}%<extra></extra>'
                    ), row=1, col=1)
                
                # === LÍNEAS DE CONEXIÓN PARA MATRICULACIONES ===
                for i, (_, row) in enumerate(df_grafico_top.iterrows()):
                    # Línea que conecta las barras de matriculaciones
                    fig_yoy.add_trace(go.Scatter(
                        x=[row['Marca'], row['Marca']],
                        y=[row[f'Mat_{año_seleccionado_yoy-1}'], row[f'Mat_{año_seleccionado_yoy}']],
                        mode='lines',
                        line=dict(color='#A23B72', width=3, dash='solid'),
                        showlegend=False,
                        hoverinfo='skip'
                    ), row=2, col=1)
                    
                    # Agregar flecha o marcador en el punto final
                    variacion_mat = ((row[f'Mat_{año_seleccionado_yoy}'] - row[f'Mat_{año_seleccionado_yoy-1}']) / row[f'Mat_{año_seleccionado_yoy-1}'] * 100) if row[f'Mat_{año_seleccionado_yoy-1}'] > 0 else 0
                    color_flecha = 'green' if variacion_mat > 0 else 'red' if variacion_mat < 0 else 'gray'
                    
                    fig_yoy.add_trace(go.Scatter(
                        x=[row['Marca']],
                        y=[row[f'Mat_{año_seleccionado_yoy}']],
                        mode='markers',
                        marker=dict(
                            symbol='arrow-up' if variacion_mat > 0 else 'arrow-down' if variacion_mat < 0 else 'circle',
                            size=12,
                            color=color_flecha
                        ),
                        showlegend=False,
                        hovertemplate=f'<b>{row["Marca"]}</b><br>Variación: {variacion_mat:.1f}%<extra></extra>'
                    ), row=2, col=1)
                
                fig_yoy.update_layout(
                    title=f' Comparación YoY: {mes_seleccionado_yoy:02d}-{año_seleccionado_yoy} vs {mes_seleccionado_yoy:02d}-{año_seleccionado_yoy-1}',
                    height=700,
                    template='plotly_white',
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    barmode='group'  # Agrupa las barras por marca
                )
                
                # Configurar ejes X
                fig_yoy.update_xaxes(title_text="Marcas (Top 10)", row=2, col=1, tickangle=45)
                fig_yoy.update_xaxes(title_text="", row=1, col=1, tickangle=45)
                
                # Configurar ejes Y
                fig_yoy.update_yaxes(title_text="Valor ($)", row=1, col=1)
                fig_yoy.update_yaxes(title_text="Valor ($)", row=2, col=1)
                
                st.plotly_chart(fig_yoy, use_container_width=True)
                
                # Mostrar tabla de variaciones
                st.subheader(" Tabla de Variaciones YoY")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if not imp_comparacion.empty:
                        st.write("**Importaciones:**")
                        imp_display = imp_comparacion[['Marca', f'Valor_{año_seleccionado_yoy-1}', f'Valor_{año_seleccionado_yoy}', 'Variacion_YoY']].copy()
                        imp_display.columns = ['Marca', f'{año_seleccionado_yoy-1}', f'{año_seleccionado_yoy}', 'YoY (%)']
                        imp_display['YoY (%)'] = imp_display['YoY (%)'].round(1)
                        st.dataframe(imp_display, use_container_width=True)
                
                with col2:
                    if not mat_comparacion.empty:
                        st.write("**Matriculaciones:**")
                        mat_display = mat_comparacion[['Marca', f'Valor_{año_seleccionado_yoy-1}', f'Valor_{año_seleccionado_yoy}', 'Variacion_YoY']].copy()
                        mat_display.columns = ['Marca', f'{año_seleccionado_yoy-1}', f'{año_seleccionado_yoy}', 'YoY (%)']
                        mat_display['YoY (%)'] = mat_display['YoY (%)'].round(1)
                        st.dataframe(mat_display, use_container_width=True)
            
            else:
                st.warning(f"⚠️ No hay datos disponibles para {mes_seleccionado_yoy:02d}-{año_seleccionado_yoy} o {mes_seleccionado_yoy:02d}-{año_seleccionado_yoy-1}")

        except Exception as e:
            st.error(f"❌ Error en comparación YoY: {e}")
            st.info("💡 Verifica que los datos tengan el formato correcto")

    except Exception as e:
        st.error(f"❌ Error general en análisis temporal: {e}")
        st.info("💡 Verifica que los datos tengan el formato correcto")

# === PÁGINA: ANÁLISIS POR MARCA ===
elif pagina == " Análisis por Marca":
    st.title(" Análisis Detallado por Marca")
    
    # Control deslizante para rango de fechas
    if marcas_seleccionadas:
        # Obtener rango de fechas disponible
        fechas_imp = importaciones[importaciones["Marca"].isin(marcas_seleccionadas)]["Fecha"].dropna()
        fechas_mat = matriculaciones[matriculaciones["Marca"].isin(marcas_seleccionadas)]["fecha"].dropna()
        fechas_todas = pd.concat([fechas_imp, fechas_mat])
        
        if not fechas_todas.empty:
            fecha_min = fechas_todas.min().date()
            fecha_max = fechas_todas.max().date()
            
            rango_fechas_marca = st.slider(
                " Rango de fechas para análisis:",
                min_value=fecha_min,
                max_value=fecha_max,
                value=(fecha_min, fecha_max),
                format="YYYY-MM-DD",
                help="Selecciona el período de tiempo para analizar las marcas"
            )
            
            # Filtrar datos por fecha
            imp_filtrado_marca = importaciones[
                (importaciones["Marca"].isin(marcas_seleccionadas)) &
                (importaciones["Fecha"].dt.date >= rango_fechas_marca[0]) &
                (importaciones["Fecha"].dt.date <= rango_fechas_marca[1])
            ]
            
            mat_filtrado_marca = matriculaciones[
                (matriculaciones["Marca"].isin(marcas_seleccionadas)) &
                (matriculaciones["fecha"].dt.date >= rango_fechas_marca[0]) &
                (matriculaciones["fecha"].dt.date <= rango_fechas_marca[1])
            ]
        else:
            imp_filtrado_marca = importaciones[importaciones["Marca"].isin(marcas_seleccionadas)]
            mat_filtrado_marca = matriculaciones[matriculaciones["Marca"].isin(marcas_seleccionadas)]
        
        for marca in marcas_seleccionadas[:5]:  # Limitar a 5 marcas
            st.subheader(f" {marca}")
            
            # Filtrar datos por marca usando datos filtrados por fecha
            imp_marca = imp_filtrado_marca[imp_filtrado_marca["Marca"] == marca]
            mat_marca = mat_filtrado_marca[mat_filtrado_marca["Marca"] == marca]
            
            if not imp_marca.empty or not mat_marca.empty:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    total_imp_marca = imp_marca["Valor"].sum() if not imp_marca.empty else 0
                    st.metric(f"Importaciones", f"{total_imp_marca:,.0f}")
                    
                with col2:
                    total_mat_marca = mat_marca["VALOR"].sum() if not mat_marca.empty else 0
                    st.metric(f"Matriculaciones", f"{total_mat_marca:,.0f}")
                
                with col3:
                    ratio_marca = (total_mat_marca / total_imp_marca * 100) if total_imp_marca > 0 else 0
                    porcentaje_falta = 100 - ratio_marca
                    st.metric(f"Falta Matricular", f"{porcentaje_falta:.1f}%")
                    
                # Gráfico temporal por marca
                try:
                    imp_marca_mes = imp_marca.groupby(imp_marca["Fecha"].dt.to_period("M"))["Valor"].sum()
                    mat_marca_mes = mat_marca.groupby(mat_marca["fecha"].dt.to_period("M"))["VALOR"].sum()
                    
                    fig_marca = go.Figure()
                    
                    if not imp_marca_mes.empty:
                        fig_marca.add_trace(go.Scatter(
                            x=imp_marca_mes.index.astype(str),
                            y=imp_marca_mes.values,
                            mode='lines+markers+text',
                            name=f'Importaciones',
                            line=dict(width=3, color='#2E86AB'),
                            marker=dict(size=8),
                            text=imp_marca_mes.values,
                            textposition='top center',
                            textfont=dict(color='#2E86AB', size=12),
                            hovertemplate='<b>Importaciones</b><br>Mes: %{x}<br>Valor: %{y:,.0f}<extra></extra>'
                        ))
                    
                    if not mat_marca_mes.empty:
                        fig_marca.add_trace(go.Scatter(
                            x=mat_marca_mes.index.astype(str),
                            y=mat_marca_mes.values,
                            mode='lines+markers+text',
                            name=f'Matriculaciones',
                            line=dict(width=3, color='#A23B72'),
                            marker=dict(size=8),
                            text=mat_marca_mes.values,
                            textposition='bottom center',
                            textfont=dict(color='#A23B72', size=12),
                            hovertemplate='<b>Matriculaciones</b><br>Mes: %{x}<br>Valor: %{y:,.0f}<extra></extra>'
                        ))
                    
                    fig_marca.update_layout(
                        title={
                            'text': f' Evolución Temporal - {marca}',
                            'x': 0.5,
                            'xanchor': 'center'
                        },
                        xaxis_title='Mes',
                        yaxis_title='Unidades',
                        height=400,
                        template='plotly_white',
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1
                        )
                    )
                    
                    st.plotly_chart(fig_marca, use_container_width=True)
                    
                except Exception as e:
                    st.error(f"Error en gráfico para {marca}: {e}")
            else:
                st.info(f"No hay datos disponibles para {marca} en el período seleccionado")
                
            st.markdown("---")
    else:
        st.info("👆 Selecciona una o más marcas en el filtro del sidebar para ver el análisis detallado")

# === PÁGINA: PRONÓSTICO MENSUAL ===
elif pagina == " Proyección de Matriculaciones":
    st.title(" Proyección de Matriculaciones")
    st.info("🚧 Esta funcionalidad estará disponible próximamente")

# === PÁGINA: HIGHLIGHTS ===
elif pagina == " Highlights":
    st.title(" Destacados del Mes")

    # Campo de texto para la consulta
    user_query = st.text_input(
        "Consulta a la IA:",
        placeholder="Ejemplo: ¿Cómo está el desempeño de Jetour vs competidores chinos?"
    )

    # Verifica que los datos existan
    if importaciones.empty or matriculaciones.empty:
        st.error("No hay datos disponibles para consultar. Por favor, carga los datos primero.")
    else:
        # Filtros simplificados
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

        # Filtrar datos base
        if años_seleccionados and meses_seleccionados:
            datos_imp = importaciones[
                (importaciones['Año'].isin(años_seleccionados)) & 
                (importaciones['Mes'].isin(meses_seleccionados))
            ]
            datos_mat = matriculaciones[
                (matriculaciones['Año'].isin(años_seleccionados)) & 
                (matriculaciones['Mes'].isin(meses_seleccionados))
            ]

            if datos_imp.empty or datos_mat.empty:
                st.warning("No hay datos para el período seleccionado.")
            else:
                # GENERAR DATOS AGREGADOS
                
                # 1. Importaciones por marca (Top 10)
                imp_por_marca = datos_imp.groupby('Marca')['Valor'].sum().sort_values(ascending=False).head(10)
                
                # 2. Matriculaciones por marca (Top 10)
                mat_por_marca = datos_mat.groupby('Marca')['VALOR'].sum().sort_values(ascending=False).head(10)
                
                # 3. Tendencia mensual de importaciones
                tendencia_imp = datos_imp.groupby(['Año', 'Mes'])['Valor'].sum()
                tendencia_imp_dict = {f"{año}-{mes:02d}": valor for (año, mes), valor in tendencia_imp.items()}
                
                # 4. Tendencia mensual de matriculaciones
                tendencia_mat = datos_mat.groupby(['Año', 'Mes'])['VALOR'].sum()
                tendencia_mat_dict = {f"{año}-{mes:02d}": valor for (año, mes), valor in tendencia_mat.items()}
                
                # 5. Comparación importaciones vs matriculaciones por marca
                comparacion_marcas = pd.DataFrame({
                    'Importaciones': imp_por_marca,
                    'Matriculaciones': mat_por_marca
                }).fillna(0)
                
                # 6. Análisis específico de Jetour
                jetour_imp = datos_imp[datos_imp['Marca'].str.contains('jetour', case=False, na=False)]
                jetour_mat = datos_mat[datos_mat['Marca'].str.contains('jetour', case=False, na=False)]
                
                jetour_stats = {
                    "importaciones_total": int(jetour_imp['Valor'].sum()) if not jetour_imp.empty else 0,
                    "matriculaciones_total": int(jetour_mat['VALOR'].sum()) if not jetour_mat.empty else 0,
                    "importaciones_mensual": {f"{año}-{mes:02d}": valor for (año, mes), valor in jetour_imp.groupby(['Año', 'Mes'])['Valor'].sum().items()} if not jetour_imp.empty else {},
                    "matriculaciones_mensual": {f"{año}-{mes:02d}": valor for (año, mes), valor in jetour_mat.groupby(['Año', 'Mes'])['VALOR'].sum().items()} if not jetour_mat.empty else {},
                }
                
                # Calcular rankings solo si Jetour tiene datos
                if not jetour_imp.empty and len(jetour_imp['Marca'].unique()) > 0:
                    jetour_marca_imp = jetour_imp['Marca'].iloc[0]
                    jetour_stats["ranking_importaciones"] = int(list(imp_por_marca.index).index(jetour_marca_imp) + 1) if jetour_marca_imp in imp_por_marca.index else None
                else:
                    jetour_stats["ranking_importaciones"] = None
                    
                if not jetour_mat.empty and len(jetour_mat['Marca'].unique()) > 0:
                    jetour_marca_mat = jetour_mat['Marca'].iloc[0]
                    jetour_stats["ranking_matriculaciones"] = int(list(mat_por_marca.index).index(jetour_marca_mat) + 1) if jetour_marca_mat in mat_por_marca.index else None
                else:
                    jetour_stats["ranking_matriculaciones"] = None
                
                # 7. Análisis de competidores chinos
                marcas_chinas = ['Chery', 'Geely', 'BYD', 'Great Wall', 'JAC', 'Jetour', 'Haval', 'MG', 'Dongfeng']
                comp_chinos_imp = datos_imp[datos_imp['Marca'].isin(marcas_chinas)].groupby('Marca')['Valor'].sum()
                comp_chinos_mat = datos_mat[datos_mat['Marca'].isin(marcas_chinas)].groupby('Marca')['VALOR'].sum()
                
                # 8. Métricas de mercado
                total_imp = int(datos_imp['Valor'].sum())
                total_mat = int(datos_mat['VALOR'].sum())
                
                market_metrics = {
                    "total_importaciones": total_imp,
                    "total_matriculaciones": total_mat,
                    "conversion_rate": round((total_mat / total_imp * 100), 2) if total_imp > 0 else 0,
                    "participacion_chinos_imp": round((comp_chinos_imp.sum() / total_imp * 100), 2) if total_imp > 0 else 0,
                    "participacion_chinos_mat": round((comp_chinos_mat.sum() / total_mat * 100), 2) if total_mat > 0 else 0,
                    "jetour_market_share_imp": round((jetour_stats["importaciones_total"] / total_imp * 100), 2) if total_imp > 0 else 0,
                    "jetour_market_share_mat": round((jetour_stats["matriculaciones_total"] / total_mat * 100), 2) if total_mat > 0 else 0
                }
                
                # 8.1. Análisis por Modelo (NUEVO)
                # Verificar si las columnas de modelo existen
                if 'Modelo' in datos_imp.columns and 'Modelo' in datos_mat.columns:
                    # Top modelos por importaciones
                    imp_por_modelo = datos_imp.groupby('Modelo')['Valor'].sum().sort_values(ascending=False).head(15)
                    
                    # Top modelos por matriculaciones
                    mat_por_modelo = datos_mat.groupby('Modelo')['VALOR'].sum().sort_values(ascending=False).head(15)
                    
                    # Análisis por marca y modelo (importaciones)
                    imp_marca_modelo = datos_imp.groupby(['Marca', 'Modelo'])['Valor'].sum().sort_values(ascending=False).head(20)
                    
                    # Análisis por marca y modelo (matriculaciones)
                    mat_marca_modelo = datos_mat.groupby(['Marca', 'Modelo'])['VALOR'].sum().sort_values(ascending=False).head(20)
                    
                    # Si existe columna Tipo en importaciones
                    if 'Tipo' in datos_imp.columns:
                        imp_por_tipo = datos_imp.groupby('Tipo')['Valor'].sum().sort_values(ascending=False)
                        tipo_modelo_imp = datos_imp.groupby(['Tipo', 'Modelo'])['Valor'].sum().sort_values(ascending=False).head(15)
                    else:
                        imp_por_tipo = pd.Series()
                        tipo_modelo_imp = pd.Series()
                    
                    analisis_modelos = {
                        "top_modelos_importaciones": imp_por_modelo.to_dict(),
                        "top_modelos_matriculaciones": mat_por_modelo.to_dict(),
                        "top_marca_modelo_importaciones": {f"{marca} - {modelo}": valor for (marca, modelo), valor in imp_marca_modelo.items()},
                        "top_marca_modelo_matriculaciones": {f"{marca} - {modelo}": valor for (marca, modelo), valor in mat_marca_modelo.items()},
                        "importaciones_por_tipo": imp_por_tipo.to_dict() if not imp_por_tipo.empty else {},
                        "tipo_modelo_importaciones": {f"{tipo} - {modelo}": valor for (tipo, modelo), valor in tipo_modelo_imp.items()} if not tipo_modelo_imp.empty else {}
                    }
                else:
                    analisis_modelos = {
                        "top_modelos_importaciones": {},
                        "top_modelos_matriculaciones": {},
                        "top_marca_modelo_importaciones": {},
                        "top_marca_modelo_matriculaciones": {},
                        "importaciones_por_tipo": {},
                        "tipo_modelo_importaciones": {}
                    }
                
                # 9. Comparación año anterior (si existe)
                comparacion_anual = {}
                if min(años_seleccionados) > min(años_disponibles):
                    año_anterior = min(años_seleccionados) - 1
                    datos_imp_ant = importaciones[importaciones['Año'] == año_anterior]
                    datos_mat_ant = matriculaciones[matriculaciones['Año'] == año_anterior]
                    
                    if not datos_imp_ant.empty and not datos_mat_ant.empty:
                        jetour_imp_ant = datos_imp_ant[datos_imp_ant['Marca'].str.contains('jetour', case=False, na=False)]
                        jetour_mat_ant = datos_mat_ant[datos_mat_ant['Marca'].str.contains('jetour', case=False, na=False)]
                        
                        jetour_imp_ant_total = jetour_imp_ant['Valor'].sum() if not jetour_imp_ant.empty else 0
                        jetour_mat_ant_total = jetour_mat_ant['VALOR'].sum() if not jetour_mat_ant.empty else 0
                        total_imp_ant = datos_imp_ant['Valor'].sum()
                        total_mat_ant = datos_mat_ant['VALOR'].sum()
                        
                        comparacion_anual = {
                            "crecimiento_jetour_imp": round(((jetour_stats["importaciones_total"] - jetour_imp_ant_total) / jetour_imp_ant_total * 100), 2) if jetour_imp_ant_total > 0 else 0,
                            "crecimiento_jetour_mat": round(((jetour_stats["matriculaciones_total"] - jetour_mat_ant_total) / jetour_mat_ant_total * 100), 2) if jetour_mat_ant_total > 0 else 0,
                            "crecimiento_mercado_imp": round(((total_imp - total_imp_ant) / total_imp_ant * 100), 2) if total_imp_ant > 0 else 0,
                            "crecimiento_mercado_mat": round(((total_mat - total_mat_ant) / total_mat_ant * 100), 2) if total_mat_ant > 0 else 0
                        }

                # PREPARAR DATOS OPTIMIZADOS PARA MAGIC LOOPS
                datos_agregados = {
                    "contexto": {
                        "empresa": "Importadora de vehículos - Paraguay",
                        "marca_principal": "Mercado General",  # Cambiado de "Jetour" a "Mercado General"
                        "periodo_analisis": f"Años: {años_seleccionados}, Meses: {meses_seleccionados}",
                        "mercado": "Automotriz Paraguay",
                        "moneda": "Unidades"
                    },
                    
                    "metricas_mercado": market_metrics,
                    "jetour_performance": jetour_stats,
                    
                    "top_marcas": {
                        "importaciones": imp_por_marca.to_dict(),
                        "matriculaciones": mat_por_marca.to_dict()
                    },
                    
                    "competencia_china": {
                        "importaciones": comp_chinos_imp.to_dict(),
                        "matriculaciones": comp_chinos_mat.to_dict(),
                        "marcas_analizadas": marcas_chinas
                    },
                    
                    "tendencias_mensuales": {
                        "importaciones": tendencia_imp_dict,
                        "matriculaciones": tendencia_mat_dict
                    },
                    
                    "analisis_modelos": analisis_modelos,
                    
                    "comparacion_anual": comparacion_anual,
                    
                    "insights_automaticos": {
                        "jetour_presente": jetour_stats["importaciones_total"] > 0 or jetour_stats["matriculaciones_total"] > 0,
                        "jetour_ranking_imp": jetour_stats["ranking_importaciones"],
                        "jetour_ranking_mat": jetour_stats["ranking_matriculaciones"],
                        "conversion_jetour": round((jetour_stats["matriculaciones_total"] / jetour_stats["importaciones_total"] * 100), 2) if jetour_stats["importaciones_total"] > 0 else 0
                    },
                    
                    "instrucciones_ai": {
                        "rol": "Analista senior de mercado automotriz paraguayo",
                        "objetivo": "Proporcionar insights estratégicos sobre cualquier aspecto del mercado automotriz paraguayo basado en la consulta del usuario",
                        "formato": "Análisis ejecutivo con datos específicos, comparaciones y recomendaciones accionables",
                        "prioridades": ["Análisis de mercado general", "Desempeño de marcas específicas", "Análisis de modelos particulares", "Tendencias y variaciones", "Competencia y oportunidades", "Insights estratégicos"],
                        "lenguaje": "Español profesional del sector automotriz",
                        "enfoque": "Adaptar el análisis según la consulta específica del usuario, incluyendo datos de modelos cuando sea relevante"
                    }
                }

                # Mostrar preview de datos
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Importaciones", f"{total_imp:,}")
                with col2:
                    st.metric("Total Matriculaciones", f"{total_mat:,}")
                with col3:
                    st.metric("Tasa Conversión", f"{market_metrics['conversion_rate']:.1f}%")
                with col4:
                    diferencia_total = total_imp - total_mat
                    st.metric("Pendiente Matricular", f"{diferencia_total:,}")

                if st.button("🔮 Consultar IA"):
                    with st.spinner("Analizando datos agregados..."):
                        resultado = consultar_magic_loops(datos_agregados, pregunta=user_query)
                        
                        if "error" in resultado:
                            st.error(f"❌ Error: {resultado['error']}")
                        else:
                            # Muestra los resultados de forma estructurada
                            if resultado.get('insight'):
                                st.success(f"**💡 Análisis Principal:**\n{resultado['insight']}")
                            
                            if resultado.get("urgencia"):
                                st.warning(f"**⚠️ Atención Requerida:**\n{resultado['urgencia']}")
                            
                            if resultado.get("accion_sugerida"):
                                st.info(f"**🎯 Recomendación Estratégica:**\n{resultado['accion_sugerida']}")
                            
                            if resultado.get("impacto_estimado"):
                                st.info(f"** Impacto Proyectado:**\n{resultado['impacto_estimado']}")
                            
                            # Mostrar insights adicionales solo si son relevantes
                            campos_adicionales = ['tendencias', 'comparaciones', 'recomendaciones', 'alertas', 'oportunidades']
                            for campo in campos_adicionales:
                                if resultado.get(campo):
                                    st.info(f"**{campo.replace('_', ' ').title()}:**\n{resultado[campo]}")

                # Opción para ver los datos que se enviarán
                if st.checkbox(" Ver resumen de datos agregados"):
                    st.json(datos_agregados)

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