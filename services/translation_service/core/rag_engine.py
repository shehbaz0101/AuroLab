import chromadb
from shared.logger import get_logger

logger = get_logger()

client = chromadb.Client()

collection = client.get_or_create_collection(name="lab_docs")


def add_documents(chunks):
    logger.info("Adding documents to vector DB")

    for i, chunk in enumerate(chunks):
        collection.add(
            documents=[chunk],
            ids=[str(i)]
        )


def retrieve_context(query: str):
    logger.info("Retrieving context from vector DB")

    results = collection.query(
        query_texts=[query],
        n_results=3
    )

    return results["documents"]