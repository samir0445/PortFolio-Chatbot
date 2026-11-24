import os
import uuid

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")  # None for local
COLLECTION_NAME = "resume_rag"
DATA_DIR = "."  # folder containing your .txt files
MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim

client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
model = SentenceTransformer(MODEL_NAME)
VECTOR_SIZE = model.get_sentence_embedding_dimension()


def create_collection():
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def chunk_by_paragraph(text: str) -> list[str]:
    """Split on blank lines; drop empty chunks."""
    text = text.replace("\r\n", "\n")
    return [p.strip() for p in text.split("\n\n") if p.strip()]


# def load_chunks(data_dir: str):
#     """Yield (filename, chunk_index, chunk_text) for every paragraph."""
#     for filename in sorted(os.listdir(data_dir)):
#         if not filename.endswith(".txt"):
#             continue
#         with open(os.path.join(data_dir, filename), "r", encoding="utf-8") as f:
#             text = f.read()
#         for idx, chunk in enumerate(chunk_by_paragraph(text)):
#             yield filename, idx, chunk

def load_chunks(data_dir: str):
    """Yield (filename, chunk_index, chunk_text) for info.txt only."""
    filename = "info.txt"
    filepath = os.path.join(data_dir, filename)

    if not os.path.exists(filepath):
        return

    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    for idx, chunk in enumerate(chunk_by_paragraph(text)):
        yield filename, idx, chunk


def ingest():
    create_collection()

    records = list(load_chunks(DATA_DIR))
    if not records:
        print("No chunks found.")
        return

    texts = [r[2] for r in records]
    vectors = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

    points = []
    for (filename, idx, chunk), vector in zip(records, vectors):
        # deterministic ID: re-running won't create duplicates
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{filename}:{idx}"))
        points.append(
            PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={
                    "text": chunk,
                    "source": filename,
                    "chunk_index": idx,
                },
            )
        )

    # upsert in batches
    BATCH = 64
    for i in range(0, len(points), BATCH):
        client.upsert(collection_name=COLLECTION_NAME, points=points[i : i + BATCH])

    print(f"Inserted {len(points)} points into '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    ingest()