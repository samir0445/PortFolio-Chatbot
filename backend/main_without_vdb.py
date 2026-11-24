import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel, Field
from pypdf import PdfReader

load_dotenv()

# Production logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

model = "openai/gpt-oss-20b"
app = FastAPI(title="Samir Jadhav Portfolio Chatbot API")


FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# CORS — allow React frontend (Vercel, localhost, etc.) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_groq_client() -> Groq:
    """Retrieve Groq client safely using API or GROQ_API_KEY env variables."""
    api_key = os.getenv("API") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("API key missing. Set API or GROQ_API_KEY in your environment.")
    return Groq(api_key=api_key)

# Models for structured resume extraction
class Experience(BaseModel):
    company: str | None = None
    role: str | None = None
    duration: str | None = None
    description: str | None = None
    skills_used: list[str] = []

class ProjectDes(BaseModel):
    name: str | None = None
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)
    link: str | None = None

class Resume(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    github: str | None = None
    linkedIn: str | None = None
    location: str | None = None
    total_experience_years: float | None = None
    skills: list[str] = []
    experiences: list[Experience] = []
    education: list[str] = []
    projects: list[ProjectDes] = Field(default_factory=list)
    certifications: list[str] = []

resume_schema = Resume.model_json_schema()

# In-memory cache for parsed resume
cached_resume: Resume | None = None

class ChatRequest(BaseModel):
    question: str

def ask_candidate(question: str, resume: Resume) -> str:
    client = get_groq_client()
    system_prompt = f"""
You are an AI assistant representing a job candidate named Samir Jadhav.

Below is everything you know about the candidate:
{resume.model_dump_json(indent=2)}

Rules:
1. Answer only using this information.
2. Never hallucinate.
3. If information is unavailable, say:
   "I don't have enough information to answer that."
4. Be professional, friendly, and concise.
5. Answer as if HR or an interviewer is asking.
6. Structure your output in proper format.
"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        max_completion_tokens=1500
    )
    return response.choices[0].message.content

def parse_projects(resume_text: str) -> list[ProjectDes]:
    client = get_groq_client()
    system_prompt = f"""
    You are an expert resume parser
    Extract all projects from the resume.

    You MUST return a valid JSON object with a root key "projects" containing a list of objects.
    Each project object must follow this schema:
    {ProjectDes.model_json_schema()}

    Rules:
    - Extract every project.
    - Preserve complete descriptions.
    - Associate GitHub links with their projects.
    - Do not invent missing information.
    - For missing details use null or [].
    """

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": resume_text}
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_completion_tokens=2500
    )

    data = json.loads(response.choices[0].message.content)

    if isinstance(data, dict):
        projects_data = data.get("projects", [])
    elif isinstance(data, list):
        projects_data = data
    else:
        projects_data = []

    return [
        ProjectDes.model_validate(project)
        for project in projects_data
    ]

def parse_resume(resume_text: str) -> Resume:
    client = get_groq_client()
    system_prompt = f"""
You are an expert resume parser.

Extract information from the resume based on its meaning,
not only based on exact section headings.

Return ONLY valid JSON matching this schema:
{resume_schema}

Important rules:
1. Do not invent information.
2. If a value is not available, return null.
3. If a list has no information, return an empty list.
4. Include internships inside experiences.
5. Extract skills mentioned across the entire resume.
6. Do not extract projects.
"""
    user_prompt = f"Parse the following resume:\n{resume_text}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        max_completion_tokens=3000
    )
    raw_output = response.choices[0].message.content
    data = json.loads(raw_output)

    projects = parse_projects(resume_text)
    data["projects"] = [
        project.model_dump() for project in projects
    ]
    return Resume.model_validate(data)

def read_pdf(file_path: Path) -> str:
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

def load_and_cache_resume() -> Resume | None:
    """Helper to locate, read and parse the resume PDF."""
    global cached_resume
    resume_path = Path(__file__).resolve().parent / "my_resume.pdf"
    if not resume_path.exists():
        logger.warning("Resume file not found at %s", resume_path)
        return None
    
    text = read_pdf(resume_path)
    cached_resume = parse_resume(text)
    
    return cached_resume

@app.on_event("startup")
def startup_event():
    """Parse resume once at startup and cache it."""
    try:
        load_and_cache_resume()
    except Exception as e:
        logger.warning("Resume could not be cached at startup: %s", e)

@app.get("/")
def home():
    return {
        "message": "Welcome to Samir Jadhav's Personal & Professional RAG Chatbot API",
        "status": "online",
        "docs": "/docs"
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "resume_loaded": cached_resume is not None
    }

@app.post("/chat")
def chat(request: ChatRequest):
    global cached_resume
    # Lazy attempt to load resume if startup failed (e.g. cold start / env timing)
    if cached_resume is None:
        try:
            cached_resume = load_and_cache_resume()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load resume context: {str(e)}"
            )

    if cached_resume is None:
        raise HTTPException(
            status_code=503,
            detail="Resume data is not loaded. Please ensure my_resume.pdf exists on the server."
        )

    try:
        answer = ask_candidate(request.question, cached_resume)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating answer: {str(e)}"
        )
