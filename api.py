import requests
import json
import time
from typing import Dict, Any, Optional
import streamlit as st

# Configuración
API_URL = st.secrets["MAGICLOOPS_API_KEY"]
MAX_PAYLOAD_SIZE = 500_000  # 500KB
DEFAULT_TIMEOUT = (30, 120)  # conexión, lectura
MAX_RETRIES = 3

def consultar_magic_loops(datos: Dict[str, Any], pregunta: Optional[str] = None) -> Dict[str, Any]:
    """
    Consulta la API de Magic Loops con datos y pregunta opcional.
    
    Args:
        datos: Diccionario con los datos a analizar
        pregunta: Consulta opcional del usuario
        
    Returns:
        Diccionario con la respuesta de la API o error
    """
    # Preparar payload
    payload: Dict[str, Any] = datos.copy() if isinstance(datos, dict) else {"data": datos}
    if pregunta and pregunta.strip():
        payload["pregunta"] = pregunta.strip()
    
    # Validar tamaño
    if len(json.dumps(payload, default=str)) > MAX_PAYLOAD_SIZE:
        return {"error": "Datos demasiado grandes. Reduce el período de consulta."}
    
    # Configurar sesión
    session = requests.Session()
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=3))
    
    # Realizar petición con reintentos
    for intento in range(MAX_RETRIES):
        try:
            response = session.post(
                API_URL,
                json=payload,
                timeout=DEFAULT_TIMEOUT,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                return response.json()
            
            # Si no es el último intento, esperar antes de reintentar
            if intento < MAX_RETRIES - 1:
                time.sleep(2 ** intento)  # backoff exponencial
                continue
                
            return {"error": f"Error HTTP {response.status_code}"}
            
        except requests.exceptions.Timeout:
            if intento < MAX_RETRIES - 1:
                time.sleep(2 ** intento)
                continue
            return {"error": "Timeout: La API no respondió a tiempo"}
            
        except requests.exceptions.RequestException as e:
            if intento < MAX_RETRIES - 1:
                time.sleep(2 ** intento)
                continue
            return {"error": f"Error de conexión: {str(e)}"}
            
        except Exception as e:
            return {"error": f"Error inesperado: {str(e)}"}
    
    return {"error": f"Falló después de {MAX_RETRIES} intentos"}