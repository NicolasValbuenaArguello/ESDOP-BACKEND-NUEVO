import asyncpg
import asyncio

async def test():
    conn = await asyncpg.connect(
        user="postgres",
        password="NICval10**",
        database="esdop",
        host="172.22.2.36",
        port=5432,
        timeout=5
    )
    
    print("OK")
    await conn.close()

asyncio.run(test())