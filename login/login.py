import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth")


class Database:
    pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def connect(cls):
        if cls.pool is not None:
            return

        cls.pool = await asyncpg.create_pool(
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            min_size=5,
            max_size=20,
        )
        logger.info("Pool de conexiones creado")

    @classmethod
    async def close(cls):
        if cls.pool is not None:
            await cls.pool.close()
            cls.pool = None
            logger.info("Pool de conexiones cerrado")

    @classmethod
    async def fetch_user(cls, username: str):
        if cls.pool is None:
            raise HTTPException(503, "DB pool no disponible")

        async with cls.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, usuario, password, unidad, nivel_per_uni, unida_per
                FROM usuarios
                WHERE usuario=$1
                """,
                username,
            )
            return dict(row) if row else None


class Cache:
    users: Dict[str, dict] = {}
    ttl = 60

    @classmethod
    def get(cls, key):
        data = cls.users.get(key)
        if data and time.time() - data["time"] < cls.ttl:
            return data["value"]
        return None

    @classmethod
    def set(cls, key, value):
        cls.users[key] = {"value": value, "time": time.time()}


class RateLimiter:
    attempts: Dict[str, list] = {}

    @classmethod
    def check(cls, ip):
        now = time.time()
        window = 60
        limit = 10

        if ip not in cls.attempts:
            cls.attempts[ip] = []

        cls.attempts[ip] = [t for t in cls.attempts[ip] if now - t < window]

        if len(cls.attempts[ip]) >= limit:
            logger.warning(f"Rate limit superado: {ip}")
            raise HTTPException(429, "Demasiados intentos")

        cls.attempts[ip].append(now)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    @staticmethod
    def verify_password(plain, hashed):
        return pwd_context.verify(plain, hashed)

    @staticmethod
    def hash_password(password: str):
        return pwd_context.hash(password[:72])

    @staticmethod
    def create_token(data: dict):
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(
            minutes=Config.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, Config.SECRET_KEY, algorithm=Config.ALGORITHM)

    @staticmethod
    def verify_token(token: str):
        try:
            return jwt.decode(token, Config.SECRET_KEY, algorithms=[Config.ALGORITHM])
        except JWTError:
            raise HTTPException(401, "Token invalido")


class LoginRequest(BaseModel):
    username: str
    password: str


router = APIRouter()


async def get_current_user(request: Request):
    auth = request.headers.get("Authorization")

    if not auth or " " not in auth:
        raise HTTPException(401, "Token invalido")

    token = auth.split(" ")[1]
    return AuthService.verify_token(token)


@router.post("/login")
async def login(data: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    RateLimiter.check(ip)

    user = Cache.get(data.username)

    if not user:
        user = await Database.fetch_user(data.username)
        if user:
            Cache.set(data.username, user)

    if not user:
        logger.warning(f"Usuario no encontrado: {data.username}")
        raise HTTPException(401, "Usuario no encontrado")

    if not AuthService.verify_password(data.password, user["password"]):
        logger.warning(f"Password incorrecto: {data.username}")
        raise HTTPException(401, "Credenciales incorrectas")

    token_payload = {
        "sub": user["usuario"],
        "user_id": user["id"],
        "unidad": user.get("unidad"),
        "nivel_per_uni": user.get("nivel_per_uni"),
        "unida_per": user.get("unida_per"),
    }

    token = AuthService.create_token(token_payload)

    logger.info(f"Login exitoso: {data.username}")

    return {"access_token": token}


@router.get("/perfil")
async def perfil(user=Depends(get_current_user)):
    return {"usuario": user}
