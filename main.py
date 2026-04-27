import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from login.login import Database, router as login_router
from usuarios.usuarios import router as usuarios_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(login_router)
app.include_router(usuarios_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api_backend"}


@app.on_event("startup")
async def startup():
    await Database.connect()
    logger.info("Backend unificado iniciado correctamente")


@app.on_event("shutdown")
async def shutdown():
    await Database.close()
