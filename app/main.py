from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import get_pool, close_pool
from app.routers import predios, cbr


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()   # precalentar pool al arrancar
    yield
    await close_pool()


app = FastAPI(
    title="API Catastral Chile",
    description=(
        "API REST para consulta del catastro de bienes raíces SII Chile. "
        "9.4M predios — consulta por rol (comuna / manzana / predio)."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(predios.router, tags=["Predios"])
app.include_router(cbr.router)


@app.get("/health", tags=["Sistema"])
async def health():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"status": "ok"}
