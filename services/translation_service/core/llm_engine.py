from services.translation_service.core.rag_engine import retrieve_context
from shared.logger import get_logger
from core.rag_engine import client
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from config.settings import settings

SYSTEM_PROMPT = "You are an expert protocol code generator. Generate clean, well-documented Python code based on the user's requirements."

def generate_protocol_code(user_input: str):
    
    logger = get_logger()

    logger.info("Generating protocol using LLM")

    context = retrieve_context(user_input)

    prompt = f"""
    Context:
    {context}

    Task:
    {user_input}
    """

    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    code = response.choices[0].message.content

    return code