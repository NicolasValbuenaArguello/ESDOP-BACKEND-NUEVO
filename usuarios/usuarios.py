import os
import asyncpg
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt, JWTError

# ==============================
# CONFIG
# ==============================
class Config:
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "NICval10**")
    DB_HOST = os.getenv("DB_HOST", "172.22.2.36")
    DB_PORT = int(os.getenv("DB_PORT", 5432))
    DB_NAME = os.getenv("DB_NAME", "esdop")

    SECRET_KEY = os.getenv("SECRET_KEY", "comando_ejercito_2026**esdop")
    ALGORITHM = "HS256"


# ==============================
# DATABASE
# ==============================
class Database:
    @staticmethod
    async def get_connection():
        try:
            return await asyncpg.connect(
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                database=Config.DB_NAME,
                host=Config.DB_HOST,
                port=Config.DB_PORT
            )
        except Exception as e:
            raise HTTPException(503, f"DB error: {str(e)}")


# ==============================
# SECURITY
# ==============================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:

    @staticmethod
    def hash_password(password: str):
        return pwd_context.hash(password[:72])

    @staticmethod
    def verify_token(token: str):
        try:
            return jwt.decode(token, Config.SECRET_KEY, algorithms=[Config.ALGORITHM])
        except JWTError:
            raise HTTPException(401, "Token inválido")


# ==============================
# MODELOS
# ==============================
class UsuarioCreate(BaseModel):
    nombre: str
    usuario: str
    password: str
    email: str
    unidad: Optional[str] = None
    nivel_per_uni: Optional[str] = None
    unida_per: Optional[str] = None
    roles: List[str] = []


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None


# ==============================
# APP
# ==============================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================
# AUTH
# ==============================
async def get_current_user(request: Request):
    auth = request.headers.get("Authorization")

    if not auth or " " not in auth:
        raise HTTPException(401, "Token inválido")

    token = auth.split(" ")[1]
    return AuthService.verify_token(token)


# ==============================
# 🔥 PERMISOS (CORREGIDO)
# ==============================
async def check_permiso(usuario: str, ruta: str, accion: str):

    conn = await Database.get_connection()

    try:
        permiso = await conn.fetchrow("""
            SELECT * FROM obtener_permisos_usuario_pagina($1, $2)
        """, usuario, ruta)

        if not permiso:
            return False

        # 🔥 IMPORTANTE (usa out_)
        return permiso[f"out_puede_{accion}"]

    finally:
        await conn.close()


# ==============================
# CREATE
# ==============================
@app.post("/usuarios")
async def crear_usuario(data: UsuarioCreate, user=Depends(get_current_user)):

    if not await check_permiso(user["sub"], "/usuarios/nuevos", "crear"):
        raise HTTPException(403, "Sin permisos")

    conn = await Database.get_connection()

    try:
        hashed = AuthService.hash_password(data.password)

        row = await conn.fetchrow("""
            INSERT INTO usuarios (nombre, usuario, password, email, unidad, nivel_per_uni, unida_per)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            RETURNING id, nombre, usuario, email
        """,
        data.nombre,
        data.usuario,
        hashed,
        data.email,
        data.unidad,
        data.nivel_per_uni,
        data.unida_per
        )

        if data.roles:
            await conn.executemany("""
                INSERT INTO usuario_rol (usuario_id, rol_id)
                SELECT $1, id FROM roles WHERE nombre=$2
            """, [(row["id"], r) for r in data.roles])

        return {
            "msg": "Usuario creado correctamente",
            "usuario": dict(row)
        }

    finally:
        await conn.close()


# ==============================
# READ
# ==============================
@app.get("/usuarios")
async def listar_usuarios(user=Depends(get_current_user)):

    if not await check_permiso(user["sub"], "/usuarios/listado", "ver"):
        raise HTTPException(403, "Sin permisos")

    conn = await Database.get_connection()

    try:
        usuarios = await conn.fetch("""
            SELECT 
                u.id,
                u.nombre,
                u.usuario,
                u.email,
                u.unidad,
                COALESCE(array_agg(DISTINCT r.nombre) FILTER (WHERE r.nombre IS NOT NULL), '{}') as roles
            FROM usuarios u
            LEFT JOIN usuario_rol ur ON ur.usuario_id = u.id
            LEFT JOIN roles r ON r.id = ur.rol_id
            GROUP BY u.id
            ORDER BY u.id DESC
        """)

        paginas = await conn.fetch("SELECT ruta FROM paginas")

        resultado = []

        for u in usuarios:
            permisos = {}

            for p in paginas:
                perm = await conn.fetchrow("""
                    SELECT * FROM obtener_permisos_usuario_pagina($1, $2)
                """, u["usuario"], p["ruta"])

                permisos[p["ruta"]] = dict(perm) if perm else {}

            resultado.append({
                **dict(u),
                "roles": u["roles"],
                "permisos": permisos
            })

        return resultado

    finally:
        await conn.close()


# ==============================
# UPDATE
# ==============================
@app.put("/usuarios/{id}")
async def actualizar_usuario(id: int, data: UsuarioUpdate, user=Depends(get_current_user)):

    if not await check_permiso(user["sub"], "/usuarios/listado", "editar"):
        raise HTTPException(403, "Sin permisos")

    conn = await Database.get_connection()

    try:
        await conn.execute("""
            UPDATE usuarios
            SET nombre = COALESCE($1, nombre),
                email = COALESCE($2, email)
            WHERE id=$3
        """, data.nombre, data.email, id)

        return {
            "msg": "Usuario actualizado correctamente",
            "id": id
        }

    finally:
        await conn.close()


# ==============================
# DELETE
# ==============================
@app.delete("/usuarios/{id}")
async def eliminar_usuario(id: int, user=Depends(get_current_user)):

    if not await check_permiso(user["sub"], "/usuarios/listado", "eliminar"):
        raise HTTPException(403, "Sin permisos")

    conn = await Database.get_connection()

    try:
        await conn.execute("DELETE FROM usuarios WHERE id=$1", id)

        return {
            "msg": "Usuario eliminado correctamente",
            "id": id
        }

    finally:
        await conn.close()


# ==============================
# OTROS
# ==============================
@app.get("/grados")
async def listar_grados(user=Depends(get_current_user)):
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch("""
            SELECT id, nombre, abreviatura, nivel
            FROM grados
            ORDER BY nivel ASC
        """)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@app.get("/paginas")
async def listar_paginas(user=Depends(get_current_user)):
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch("""
            SELECT id, menu, nombre, ruta
            FROM paginas
        """)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@app.get("/roles")
async def listar_roles(user=Depends(get_current_user)):
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch("""
            SELECT id, nombre, descripcion
            FROM roles
        """)
        return [dict(r) for r in rows]
    finally:
        await conn.close()