import pandas as pd
import sqlite3
import os
from datetime import datetime

def cargar_datos():
    """
    Función para cargar y procesar los datos de Excel hacia SQLite
    """
    try:
        # Verificar que los archivos existen
        archivos_requeridos = ["IMPORT GRAL.xlsx", "MATRICULACIONES_2022 A HOY.xlsx"]
        for archivo in archivos_requeridos:
            if not os.path.exists(archivo):
                raise FileNotFoundError(f"No se encontró el archivo: {archivo}")
        
        print("Cargando archivos Excel...")
        
        # Cargar archivos Excel con manejo de errores
        try:
            df_import = pd.read_excel("IMPORT GRAL.xlsx", sheet_name="IMPORT_GENERAL")
            print(f"✓ Importaciones cargadas: {len(df_import)} registros")
        except Exception as e:
            print(f"Error al cargar importaciones: {e}")
            raise
            
        try:
            df_matric = pd.read_excel("MATRICULACIONES_2022 A HOY.xlsx", sheet_name="New Report")
            print(f"✓ Matriculaciones cargadas: {len(df_matric)} registros")
        except Exception as e:
            print(f"Error al cargar matriculaciones: {e}")
            raise

        # Procesar IMPORTACIONES
        print("Procesando datos de importaciones...")
        
        # Limpiar y convertir fechas
        df_import["Fecha"] = pd.to_datetime(df_import["Fecha"], errors="coerce")
        fechas_invalidas_imp = df_import["Fecha"].isna().sum()
        if fechas_invalidas_imp > 0:
            print(f"⚠️  {fechas_invalidas_imp} fechas inválidas en importaciones")
        
        # Eliminar registros con fechas nulas
        df_import = df_import.dropna(subset=["Fecha"])
        
        # Crear columnas de tiempo
        df_import["Año"] = df_import["Fecha"].dt.year
        df_import["Mes"] = df_import["Fecha"].dt.month
        df_import["Trimestre"] = df_import["Fecha"].dt.quarter
        
        # Limpiar datos de texto
        df_import["Marca"] = df_import["Marca"].astype(str).str.strip().str.upper()
        
        # Verificar y limpiar valores numéricos
        if "Valor" in df_import.columns:
            df_import["Valor"] = pd.to_numeric(df_import["Valor"], errors="coerce").fillna(0)
        else:
            print("⚠️  Columna 'Valor' no encontrada en importaciones")
            
        # Crear columna combinada
        df_import["Combinada"] = (df_import["Marca"] + "-" + 
                                 df_import["Mes"].astype(str) + "/" + 
                                 df_import["Año"].astype(str))

        # Procesar MATRICULACIONES
        print("Procesando datos de matriculaciones...")
        
        # Limpiar y convertir fechas
        df_matric["fecha"] = pd.to_datetime(df_matric["fecha"], errors="coerce")
        fechas_invalidas_mat = df_matric["fecha"].isna().sum()
        if fechas_invalidas_mat > 0:
            print(f"⚠️  {fechas_invalidas_mat} fechas inválidas en matriculaciones")
        
        # Eliminar registros con fechas nulas
        df_matric = df_matric.dropna(subset=["fecha"])
        
        # Estandarizar nombres de columnas
        if "valor" in df_matric.columns:
            df_matric = df_matric.rename(columns={"valor": "VALOR"})
        elif "Valor" in df_matric.columns:
            df_matric = df_matric.rename(columns={"Valor": "VALOR"})
            
        # Crear columnas de tiempo
        df_matric["Año"] = df_matric["fecha"].dt.year
        df_matric["Mes"] = df_matric["fecha"].dt.month
        df_matric["Trimestre"] = df_matric["fecha"].dt.quarter
        
        # Limpiar datos de texto
        df_matric["Marca"] = df_matric["Marca"].astype(str).str.strip().str.upper()
        
        # Verificar y limpiar valores numéricos
        if "VALOR" in df_matric.columns:
            df_matric["VALOR"] = pd.to_numeric(df_matric["VALOR"], errors="coerce").fillna(0)
        else:
            print("⚠️  Columna 'VALOR' no encontrada en matriculaciones")
            
        # Crear columna combinada
        df_matric["Combinada"] = (df_matric["Marca"] + "-" + 
                                 df_matric["Mes"].astype(str) + "/" + 
                                 df_matric["Año"].astype(str))

        # Mostrar estadísticas básicas
        print(f"\n📊 Resumen de datos procesados:")
        print(f"Importaciones: {len(df_import)} registros")
        print(f"  - Rango fechas: {df_import['Fecha'].min()} a {df_import['Fecha'].max()}")
        print(f"  - Marcas únicas: {df_import['Marca'].nunique()}")
        
        print(f"Matriculaciones: {len(df_matric)} registros")
        print(f"  - Rango fechas: {df_matric['fecha'].min()} a {df_matric['fecha'].max()}")
        print(f"  - Marcas únicas: {df_matric['Marca'].nunique()}")

        # Guardar en SQLite
        print("\nGuardando en base de datos...")
        conn = sqlite3.connect("automotor.db")
        
        # Guardar con manejo de errores
        df_import.to_sql("IMPORT_2019_2024", conn, if_exists="replace", index=False)
        df_matric.to_sql("MATRICULACION_ANUAL_", conn, if_exists="replace", index=False)
        
        # Crear índices para mejorar rendimiento
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE INDEX IF NOT EXISTS idx_import_fecha ON IMPORT_2019_2024(Fecha);
            CREATE INDEX IF NOT EXISTS idx_import_marca ON IMPORT_2019_2024(Marca);
            CREATE INDEX IF NOT EXISTS idx_import_año_mes ON IMPORT_2019_2024(Año, Mes);
            
            CREATE INDEX IF NOT EXISTS idx_matric_fecha ON MATRICULACION_ANUAL_(fecha);
            CREATE INDEX IF NOT EXISTS idx_matric_marca ON MATRICULACION_ANUAL_(Marca);
            CREATE INDEX IF NOT EXISTS idx_matric_año_mes ON MATRICULACION_ANUAL_(Año, Mes);
        """)
        
        conn.close()
        
        print("✅ Base de datos 'automotor.db' actualizada exitosamente!")
        return True
        
    except Exception as e:
        print(f"❌ Error durante el procesamiento: {e}")
        return False

if __name__ == "__main__":
    print("🚗 Iniciando carga de datos automotor...")
    print("=" * 50)
    
    success = cargar_datos()
    
    if success:
        print("=" * 50)
        print("✅ Proceso completado exitosamente!")
    else:
        print("=" * 50)
        print("❌ El proceso falló. Revisa los errores arriba.")