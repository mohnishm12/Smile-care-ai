import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.config import get_settings
from src.database import engine
from src.routers import auth, messages, staff, whatsapp

settings = get_settings()

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("healflow")


def _setup_otel(app: FastAPI) -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: settings.otel_service_name})
        )
        exporter = OTLPSpanExporter(
            endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces"
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except Exception:  # pragma: no cover - tracing must never break the app
        logger.warning("OpenTelemetry setup failed; continuing without tracing", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_otel(app)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(messages.router)
app.include_router(staff.router)
app.include_router(whatsapp.router)


@app.get("/health")
async def health() -> dict:
    db_status = "healthy"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    overall = "healthy" if db_status == "healthy" else "unhealthy"
    return {
        "status": overall,
        "service": settings.app_name,
        "version": settings.app_version,
        "database": db_status,
    }
