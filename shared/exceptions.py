from fastapi.responses import JSONResponse
from fastapi.requests import Request

async def global_exception_handler(request : Request, exc : Exception):
    return JSONResponse(
        status_code = 500,
        content = {
            "status" : "error",
            "message" : str(exc),
            "errors" : []
        }
    )
    