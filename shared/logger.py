from loguru import logger
import os

os.makedirs("logs", exist_ok = True)
logger.add("logs/aurolab.log", rotation = "1 MB")

def get_logger():
    return logger