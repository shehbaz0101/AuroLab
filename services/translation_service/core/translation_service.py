from shared.logger import get_logger

logger = get_logger()


class TranslationService:

    def process_request(self, experiment: str):
        
        logger.info(f"Processing experiment: {experiment}")

        # Placeholder (LLM will come later)
        result = f"Processed: {experiment}"

        return result