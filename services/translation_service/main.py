from fastapi import FastAPI
from services.translation_service.api.routes import router
from shared.middleware import LoggingMiddleware
from shared.exceptions import global_exception_handler
from services.translation_service.core.document_loader import load_sample_docs

app = FastAPI(title = "AuroLab API", version = "1.0")

load_sample_docs()

# Middleware
app.add_middleware(LoggingMiddleware)

# Routes
app.include_router(router)

# Exception handler
app.add_exception_handler(Exception, global_exception_handler)

@app.get("/health")
def health_check():
    return {"status" : "ok"}