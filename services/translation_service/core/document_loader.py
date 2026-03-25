from services.translation_service.core.rag_engine import add_documents


def load_sample_docs():
    
    docs = [
        "Use p300 pipette for volumes between 50-300 uL",
        "Always avoid cross contamination by changing tips",
        "96 well plate is commonly used for assays",
        "Do not exceed pipette maximum capacity",
        "Ensure proper labware placement before execution"
    ]

    add_documents(docs)