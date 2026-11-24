import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------- Config ----------
LLM_MODEL = "openai/gpt-oss-20b"
EMBED_MODEL = "all-MiniLM-L6-v2"      # MUST match the ingestion script
COLLECTION_NAME = "resume_rag"           # MUST match the ingestion script
TOP_K = 4
SCORE_THRESHOLD = 0.25                # drop weak matches; tune after testing

FRONTEND_URL = os.getenv("FRONTEND_URL")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# Shared resources, created once at startup
resources: dict = {}


def get_groq_client() -> Groq:
    api_key = os.getenv("API") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("API key missing. Set API or GROQ_API_KEY in your environment.")
    return Groq(api_key=api_key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading embedding model and connecting to Qdrant...")
    resources["embedder"] = SentenceTransformer(EMBED_MODEL)
    resources["qdrant"] = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    resources["groq"] = get_groq_client()
    try:
        info = resources["qdrant"].get_collection(COLLECTION_NAME)
        logger.info("Collection '%s' ready (%s points)", COLLECTION_NAME, info.points_count)
    except Exception as e:
        logger.warning("Qdrant collection check failed: %s", e)
    yield
    resources.clear()


app = FastAPI(title="Samir Jadhav Portfolio Chatbot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


# ---------- RAG steps ----------
def retrieve_context(question: str, top_k: int = TOP_K) -> list[dict]:
    """Embed the question the same way as ingestion, then search Qdrant."""
    vector = resources["embedder"].encode(question, normalize_embeddings=True).tolist()

    result = resources["qdrant"].query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=top_k,
        score_threshold=SCORE_THRESHOLD,
        with_payload=True,
    )

    return [
        {
            "text": p.payload.get("text", ""),
            "source": p.payload.get("source"),
            "score": p.score,
        }
        for p in result.points
    ]


# def build_system_prompt(chunks: list[dict]) -> str:
#     context = "\n\n".join(f"[{i + 1}] {c['text']}" for i, c in enumerate(chunks))
#     return f"""
# You are an AI assistant representing a job candidate named Samir Jadhav.

# Below is the retrieved context about the candidate:
# {context}

# Rules:
# 1. Answer only using this context.
# 2. Never hallucinate.
# 3. If the context does not contain the answer, say:
#    "I don't have enough information to answer that."
# 4. Be professional, friendly, and concise.
# 5. Answer as if HR or an interviewer is asking.
# 6. Structure your output in proper format.
# """


def build_system_prompt(chunks: list[dict]) -> str:
    context = "\n\n".join(f"[{i + 1}] {c['text']}" for i, c in enumerate(chunks))
    return f"""


You are the AI assistant on Samir Jadhav's portfolio. You speak to recruiters, HR and interviewers
about Samir, in third person ("Samir has...", "He built..."). Be warm, professional and concise.

CONTEXT (retrieved facts about Samir):
{context}

STEP 1 - Decide the type of message:
- Greeting or small talk (hi, hello, thanks, bye): reply in 1-2 friendly sentences,
  introduce yourself briefly, and invite a question (e.g. skills, projects, education).
  Do NOT use the context for this.
- Question about Samir: answer using ONLY the context.
- Unrelated to Samir or not in the context: reply exactly
  "I don't have enough information to answer that."

STEP 2 - Answer rules:
- Answer ONLY what was asked. Do not add extra background, past internships, or unrelated
  details unless the question asks for them.
- Never invent facts, dates, companies or numbers. Use only what is in the context.
- Do not mention "context", "chunks" or the [1], [2] markers.
- Keep it short: simple question = 1-3 sentences; broad question = at most 5 short points.

STEP 3 - Formatting rules (strict):
- Plain text only. Do NOT use markdown: no **, no *, no #, no backticks, no tables.
- For lists, put each item on a new line starting with "- ".
- For a project, use this shape:
  Project name: one-line description
  - Tech: ...
  - Key feature: ...
- Short paragraphs, blank line between them.

EXAMPLES:
User: hi
Assistant: Hello! I'm Samir Jadhav's AI assistant. I can tell you about his skills, projects, education or experience. What would you like to know?

User: What is his tech stack?
Assistant: Samir mainly works with the MERN stack and TypeScript. He also knows:
- C++, SQL and PostgreSQL
- Docker and AWS (currently learning)

Rules:
1. Answer only using this context.
2. Never hallucinate.
3. If the context does not contain the answer, say:
   "I don't have enough information to answer that."
4. Be professional, friendly, and concise.
5. Answer as if HR or an interviewer is asking.
6. Structure your output in proper format.
"""


def ask_candidate(question: str, chunks: list[dict]) -> str:
    response = resources["groq"].chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": build_system_prompt(chunks)},
            {"role": "user", "content": question},
        ],
        temperature=0.2,
        max_completion_tokens=1500,
    )
    return response.choices[0].message.content


# ---------- Routes ----------
@app.get("/")
def home():
    return {
        "message": "Welcome to Samir Jadhav's Personal & Professional RAG Chatbot API",
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    try:
        info = resources["qdrant"].get_collection(COLLECTION_NAME)
        return {"status": "ok", "qdrant_points": info.points_count}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        chunks = retrieve_context(request.question)
    except Exception as e:
        logger.exception("Retrieval failed")
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")

    # Nothing relevant found: skip the LLM call entirely
    if not chunks:
        return {"answer": "I don't have enough information to answer that.", "sources": []}

    try:
        answer = ask_candidate(request.question, chunks)
        return {
            "answer": answer,
            "sources": [{"source": c["source"], "score": round(c["score"], 3)} for c in chunks],
        }
    except Exception as e:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=f"Error generating answer: {e}")