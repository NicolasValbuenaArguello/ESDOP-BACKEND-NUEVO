import os
from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(title="estadistica_mapa_test")


def build_service_info():
    return {
        "service": "estadistica_mapa",
        "hostname": os.getenv("HOSTNAME", "unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    return {
        "message": "Servicio de prueba estadistica_mapa",
        **build_service_info(),
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        **build_service_info(),
    }


@app.get("/test")
async def test():
    return {
        "message": "Respuesta de prueba para validar replicas y balanceo",
        **build_service_info(),
    }
