from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from login.login import AuthService, Database, get_current_user


class PermisoPaginaInput(BaseModel):
    tiene_permiso: bool = False
    puede_ver: bool = False
    puede_crear: bool = False
    puede_editar: bool = False
    puede_eliminar: bool = False


class UsuarioCreate(BaseModel):
    nombre: str
    usuario: str
    password: str
    email: str
    unidad: Optional[str] = None
    nivel_per_uni: Optional[str] = None
    unida_per: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    permisos: Dict[str, PermisoPaginaInput] = Field(default_factory=dict)


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None
    unidad: Optional[str] = None
    nivel_per_uni: Optional[str] = None
    unida_per: Optional[str] = None
    roles: Optional[List[str]] = None
    permisos: Optional[Dict[str, PermisoPaginaInput]] = None


router = APIRouter()


def require_pool():
    if Database.pool is None:
        raise HTTPException(503, "DB pool no disponible")
    return Database.pool


async def check_permiso(usuario: str, ruta: str, accion: str):
    pool = require_pool()

    try:
        async with pool.acquire() as conn:
            permiso = await conn.fetchrow(
                """
                SELECT * FROM obtener_permisos_usuario_pagina($1, $2)
                """,
                usuario,
                ruta,
            )

        if not permiso:
            return False

        return permiso[f"out_puede_{accion}"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"DB error: {str(e)}")


def format_permiso(permiso):
    if not permiso:
        return {
            "tiene_permiso": False,
            "puede_ver": False,
            "puede_crear": False,
            "puede_editar": False,
            "puede_eliminar": False,
        }

    return {
        "tiene_permiso": permiso.get("out_tiene_permiso", False),
        "puede_ver": permiso.get("out_puede_ver", False),
        "puede_crear": permiso.get("out_puede_crear", False),
        "puede_editar": permiso.get("out_puede_editar", False),
        "puede_eliminar": permiso.get("out_puede_eliminar", False),
    }


async def guardar_permisos_usuario(
    conn, usuario_id: int, permisos: Dict[str, PermisoPaginaInput]
):
    await conn.execute("DELETE FROM usuario_pagina WHERE usuario_id=$1", usuario_id)

    if not permisos:
        return

    rutas = list(permisos.keys())
    paginas = await conn.fetch(
        "SELECT id, ruta FROM paginas WHERE ruta = ANY($1::text[])",
        rutas,
    )
    paginas_por_ruta = {pagina["ruta"]: pagina["id"] for pagina in paginas}

    rutas_no_encontradas = [ruta for ruta in rutas if ruta not in paginas_por_ruta]
    if rutas_no_encontradas:
        raise HTTPException(
            400,
            f"Paginas no encontradas para permisos: {', '.join(rutas_no_encontradas)}",
        )

    registros = []
    for ruta, permiso in permisos.items():
        registros.append(
            (
                usuario_id,
                paginas_por_ruta[ruta],
                permiso.tiene_permiso,
                permiso.puede_ver,
                permiso.puede_crear,
                permiso.puede_editar,
                permiso.puede_eliminar,
            )
        )

    await conn.executemany(
        """
        INSERT INTO usuario_pagina (
            usuario_id,
            pagina_id,
            tiene_permiso,
            puede_ver,
            puede_crear,
            puede_editar,
            puede_eliminar
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        registros,
    )


async def guardar_roles_usuario(conn, usuario_id: int, roles: List[str]):
    await conn.execute("DELETE FROM usuario_rol WHERE usuario_id=$1", usuario_id)

    if not roles:
        return

    await conn.executemany(
        """
        INSERT INTO usuario_rol (usuario_id, rol_id)
        SELECT $1, id FROM roles WHERE nombre=$2
        """,
        [(usuario_id, rol) for rol in roles],
    )


@router.post("/usuarios")
async def crear_usuario(data: UsuarioCreate, user=Depends(get_current_user)):
    if not await check_permiso(user["sub"], "/usuarios/nuevos", "crear"):
        raise HTTPException(403, "Sin permisos")

    pool = require_pool()

    try:
        async with pool.acquire() as conn:
            hashed = AuthService.hash_password(data.password)

            row = await conn.fetchrow(
                """
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
                data.unida_per,
            )

            await guardar_roles_usuario(conn, row["id"], data.roles)
            await guardar_permisos_usuario(conn, row["id"], data.permisos)

        return {
            "msg": "Usuario creado correctamente",
            "usuario": dict(row),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"DB error: {str(e)}")


@router.get("/usuarios")
async def listar_usuarios(user=Depends(get_current_user)):
    pool = require_pool()

    try:
        async with pool.acquire() as conn:
            usuarios = await conn.fetch(
                """
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
                """
            )

            paginas = await conn.fetch("SELECT ruta FROM paginas")

            resultado = []
            for u in usuarios:
                permisos = {}

                for p in paginas:
                    perm = await conn.fetchrow(
                        """
                        SELECT * FROM obtener_permisos_usuario_pagina($1, $2)
                        """,
                        u["usuario"],
                        p["ruta"],
                    )

                    permisos[p["ruta"]] = format_permiso(dict(perm) if perm else None)

                resultado.append(
                    {
                        **dict(u),
                        "roles": u["roles"],
                        "permisos": permisos,
                    }
                )

        return resultado
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"DB error: {str(e)}")


@router.put("/usuarios/{id}")
async def actualizar_usuario(id: int, data: UsuarioUpdate, user=Depends(get_current_user)):
    pool = require_pool()

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE usuarios
                SET nombre = COALESCE($1, nombre),
                    email = COALESCE($2, email),
                    unidad = COALESCE($3, unidad),
                    nivel_per_uni = COALESCE($4, nivel_per_uni),
                    unida_per = COALESCE($5, unida_per)
                WHERE id=$6
                """,
                data.nombre,
                data.email,
                data.unidad,
                data.nivel_per_uni,
                data.unida_per,
                id,
            )

            if data.roles is not None:
                await guardar_roles_usuario(conn, id, data.roles)

            if data.permisos is not None:
                await guardar_permisos_usuario(conn, id, data.permisos)

        return {
            "msg": "Usuario actualizado correctamente",
            "id": id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"DB error: {str(e)}")


@router.delete("/usuarios/{id}")
async def eliminar_usuario(id: int, user=Depends(get_current_user)):
    pool = require_pool()

    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM usuarios WHERE id=$1", id)

        return {
            "msg": "Usuario eliminado correctamente",
            "id": id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"DB error: {str(e)}")


@router.get("/grados")
async def listar_grados(user=Depends(get_current_user)):
    pool = require_pool()

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, nombre, abreviatura, nivel
                FROM grados
                ORDER BY nivel ASC
                """
            )
        return [dict(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"DB error: {str(e)}")


@router.get("/paginas")
async def listar_paginas(user=Depends(get_current_user)):
    pool = require_pool()

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, menu, nombre, ruta
                FROM paginas
                """
            )
        return [dict(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"DB error: {str(e)}")


@router.get("/roles")
async def listar_roles(user=Depends(get_current_user)):
    pool = require_pool()

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, nombre, descripcion
                FROM roles
                """
            )
        return [dict(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"DB error: {str(e)}")
