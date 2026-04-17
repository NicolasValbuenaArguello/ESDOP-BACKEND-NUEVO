-- ============================================================
-- BASE DE DATOS: MANDO CONTROL COATE (CORREGIDO)
-- ============================================================

SET client_min_messages TO WARNING;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- ROLES
-- ============================================================
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    descripcion TEXT
);

INSERT INTO roles (nombre, descripcion) VALUES
('SUPER', 'Super administrador con control total'),
('ADMIN', 'Administrador con acceso ampliado'),
('USUARIO', 'Operador con acceso restringido')
ON CONFLICT DO NOTHING;

-- ============================================================
-- GRADOS
-- ============================================================
CREATE TABLE IF NOT EXISTS grados (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    abreviatura VARCHAR(20),
    nivel INTEGER NOT NULL
);

-- ============================================================
-- PAGINAS
-- ============================================================
CREATE TABLE IF NOT EXISTS paginas (
    id SERIAL PRIMARY KEY,
    menu VARCHAR(150) NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    ruta VARCHAR(200) UNIQUE NOT NULL,
    descripcion TEXT,
    activa BOOLEAN DEFAULT TRUE,
    creada_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO paginas (menu, nombre, ruta, descripcion) VALUES
('HOME','Home', '/home', 'Panel principal'),
('Usuarios','Usuarios Ingreso', '/usuarios/nuevos', 'Creacion de usuarios'),
('Usuarios','Usuarios Listados', '/usuarios/listado', 'Listado y gestion de usuarios'),
('Estadistica','Estadisticas', '/estadisticas', 'Visualización de estadísticas'),
('Configuración','Configuración', '/configuracion', 'Ajustes del sistema')
ON CONFLICT DO NOTHING;

-- ============================================================
-- USUARIOS
-- ============================================================
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    usuario VARCHAR(255) UNIQUE NOT NULL,
    password TEXT NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    unidad TEXT,
    nivel_per_uni VARCHAR(50),
    unida_per VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- RELACIONES
-- ============================================================
CREATE TABLE IF NOT EXISTS usuario_rol (
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    rol_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (usuario_id, rol_id)
);

CREATE TABLE IF NOT EXISTS rol_pagina (
    rol_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    pagina_id INTEGER REFERENCES paginas(id) ON DELETE CASCADE,
    tiene_permiso BOOLEAN DEFAULT TRUE,
    puede_ver BOOLEAN DEFAULT TRUE,
    puede_crear BOOLEAN DEFAULT FALSE,
    puede_editar BOOLEAN DEFAULT FALSE,
    puede_eliminar BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (rol_id, pagina_id)
);

CREATE TABLE IF NOT EXISTS usuario_pagina (
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    pagina_id INTEGER REFERENCES paginas(id) ON DELETE CASCADE,
    tiene_permiso BOOLEAN DEFAULT TRUE,
    puede_ver BOOLEAN DEFAULT TRUE,
    puede_crear BOOLEAN DEFAULT FALSE,
    puede_editar BOOLEAN DEFAULT FALSE,
    puede_eliminar BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (usuario_id, pagina_id)
);

-- ============================================================
-- USUARIO ADMIN
-- ============================================================
INSERT INTO usuarios (nombre, usuario, password, email, unidad)
VALUES (
    'Administrador',
    'admin',
    '$2b$12$FE15whjzDoCcoroKuhSi6.gyayl6sXAjEr8rxTmqNckuijIk1N4vi',
    'admin@example.com',
    'Ejército Nacional'
)
ON CONFLICT DO NOTHING;

INSERT INTO usuario_rol (usuario_id, rol_id)
SELECT u.id, r.id
FROM usuarios u, roles r
WHERE u.usuario = 'admin' AND r.nombre = 'SUPER'
ON CONFLICT DO NOTHING;

-- ============================================================
-- PERMISOS SUPER
-- ============================================================
INSERT INTO rol_pagina (
    rol_id, pagina_id,
    tiene_permiso, puede_ver, puede_crear, puede_editar, puede_eliminar
)
SELECT r.id, p.id, TRUE, TRUE, TRUE, TRUE, TRUE
FROM roles r, paginas p
WHERE r.nombre = 'SUPER'
ON CONFLICT DO NOTHING;

-- ============================================================
-- 🔥 FUNCION CORREGIDA (SIN ERROR)
-- ============================================================
CREATE OR REPLACE FUNCTION obtener_permisos_usuario_pagina(
    p_usuario TEXT,
    p_ruta_o_nombre TEXT
) RETURNS TABLE(
    out_tiene_permiso BOOLEAN,
    out_puede_ver BOOLEAN,
    out_puede_crear BOOLEAN,
    out_puede_editar BOOLEAN,
    out_puede_eliminar BOOLEAN
) LANGUAGE plpgsql AS $$

DECLARE
    v_usuario_id INTEGER;
    v_pagina_id INTEGER;

    r_tiene_permiso BOOLEAN;
    r_puede_ver BOOLEAN;
    r_puede_crear BOOLEAN;
    r_puede_editar BOOLEAN;
    r_puede_eliminar BOOLEAN;

    u_tiene_permiso BOOLEAN;
    u_puede_ver BOOLEAN;
    u_puede_crear BOOLEAN;
    u_puede_editar BOOLEAN;
    u_puede_eliminar BOOLEAN;

BEGIN

    SELECT id INTO v_usuario_id FROM usuarios WHERE usuario = p_usuario LIMIT 1;
    SELECT id INTO v_pagina_id FROM paginas WHERE ruta = p_ruta_o_nombre OR nombre = p_ruta_o_nombre LIMIT 1;

    IF v_usuario_id IS NULL OR v_pagina_id IS NULL THEN
        RETURN QUERY SELECT FALSE, FALSE, FALSE, FALSE, FALSE;
        RETURN;
    END IF;

    SELECT
        bool_or(rp.tiene_permiso),
        bool_or(rp.puede_ver),
        bool_or(rp.puede_crear),
        bool_or(rp.puede_editar),
        bool_or(rp.puede_eliminar)
    INTO 
        r_tiene_permiso,
        r_puede_ver,
        r_puede_crear,
        r_puede_editar,
        r_puede_eliminar
    FROM usuario_rol ur
    JOIN rol_pagina rp ON rp.rol_id = ur.rol_id
    WHERE ur.usuario_id = v_usuario_id 
      AND rp.pagina_id = v_pagina_id;

    SELECT 
        up.tiene_permiso,
        up.puede_ver,
        up.puede_crear,
        up.puede_editar,
        up.puede_eliminar
    INTO 
        u_tiene_permiso,
        u_puede_ver,
        u_puede_crear,
        u_puede_editar,
        u_puede_eliminar
    FROM usuario_pagina up
    WHERE up.usuario_id = v_usuario_id 
      AND up.pagina_id = v_pagina_id
    LIMIT 1;

    RETURN QUERY SELECT
        COALESCE(u_tiene_permiso, r_tiene_permiso, FALSE),
        COALESCE(u_puede_ver, r_puede_ver, FALSE),
        COALESCE(u_puede_crear, r_puede_crear, FALSE),
        COALESCE(u_puede_editar, r_puede_editar, FALSE),
        COALESCE(u_puede_eliminar, r_puede_eliminar, FALSE);

END;
$$;