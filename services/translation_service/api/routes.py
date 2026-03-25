from fastapi import APIRouter, Depends
from shared.response import success_response
from services.translation_service.models.schema import ProtocolRequest
from services.translation_service.core.translation_service import TranslationService

router = APIRouter(prefix="/v1")


def get_translation_service():
    return TranslationService()


@router.post("/generate")
def generate_protocol(
    request: ProtocolRequest,
    service: TranslationService = Depends(get_translation_service)
):
    code = service.process_request(request.experiment)

    return success_response(data={"protocol": code})