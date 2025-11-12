import os
import shutil
import uuid
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Song as SongSchema

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Song Distribution Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Song Distribution Platform API"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set"
            response["database_name"] = getattr(db, "name", "✅ Connected")
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


# Helpers

def make_slug(title: str, artist: str) -> str:
    base = f"{title}-{artist}".strip().lower()
    allowed = [c if c.isalnum() else '-' for c in base]
    base_slug = '-'.join('-'.join(''.join(allowed).split()).split('-'))
    base_slug = base_slug.strip('-') or 'song'
    unique = uuid.uuid4().hex[:6]
    slug = f"{base_slug}-{unique}"
    # ensure uniqueness
    while db["song"].find_one({"slug": slug}):
        unique = uuid.uuid4().hex[:6]
        slug = f"{base_slug}-{unique}"
    return slug


def record_event(slug: str, event_type: str, request: Request):
    try:
        # Increment counters on song document
        if event_type == "view":
            db["song"].update_one({"slug": slug}, {"$inc": {"views": 1}})
        elif event_type == "download":
            db["song"].update_one({"slug": slug}, {"$inc": {"downloads": 1}})
        # Optionally store a separate event document
        event_doc = {
            "song_slug": slug,
            "event_type": event_type,
            "user_agent": request.headers.get("user-agent"),
            "ip": request.client.host if request.client else None,
        }
        db["event"].insert_one(event_doc)
    except Exception:
        # Don't block primary action if analytics fails
        pass


class SongOut(BaseModel):
    title: str
    artist: str
    description: Optional[str]
    slug: str
    filename: str
    size: int
    downloads: int
    views: int
    download_url: str


@app.post("/api/songs", response_model=SongOut)
async def upload_song(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str = Form(...),
    description: Optional[str] = Form(None),
):
    if file.content_type is None or not file.content_type.startswith("audio"):
        raise HTTPException(status_code=400, detail="Please upload a valid audio file")

    # Persist file to disk
    original_name = file.filename or "audiofile"
    ext = os.path.splitext(original_name)[1]
    storage_name = f"{uuid.uuid4().hex}{ext}"
    storage_path = os.path.join(UPLOAD_DIR, storage_name)

    with open(storage_path, "wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    slug = make_slug(title, artist)

    song_doc = SongSchema(
        title=title,
        artist=artist,
        description=description,
        slug=slug,
        filename=original_name,
        storage_path=storage_path,
        content_type=file.content_type,
        size=os.path.getsize(storage_path),
        downloads=0,
        views=0,
    )

    create_document("song", song_doc)

    base_url = os.getenv("FRONTEND_URL") or os.getenv("BACKEND_URL") or ""
    download_url = f"/api/songs/{slug}/download"

    return SongOut(
        title=song_doc.title,
        artist=song_doc.artist,
        description=song_doc.description,
        slug=song_doc.slug,
        filename=song_doc.filename,
        size=song_doc.size,
        downloads=song_doc.downloads,
        views=song_doc.views,
        download_url=download_url,
    )


@app.get("/api/songs", response_model=List[SongOut])
def list_songs(request: Request, limit: int = 20):
    docs = db["song"].find().sort("created_at", -1).limit(limit)
    items: List[SongOut] = []
    for d in docs:
        items.append(
            SongOut(
                title=d.get("title"),
                artist=d.get("artist"),
                description=d.get("description"),
                slug=d.get("slug"),
                filename=d.get("filename"),
                size=d.get("size", 0),
                downloads=d.get("downloads", 0),
                views=d.get("views", 0),
                download_url=f"/api/songs/{d.get('slug')}/download",
            )
        )
    return items


@app.get("/api/songs/{slug}", response_model=SongOut)
def get_song(slug: str, request: Request):
    doc = db["song"].find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Song not found")
    # Count a view
    record_event(slug, "view", request)
    return SongOut(
        title=doc.get("title"),
        artist=doc.get("artist"),
        description=doc.get("description"),
        slug=doc.get("slug"),
        filename=doc.get("filename"),
        size=doc.get("size", 0),
        downloads=doc.get("downloads", 0),
        views=doc.get("views", 0),
        download_url=f"/api/songs/{doc.get('slug')}/download",
    )


@app.get("/api/songs/{slug}/download")
def download_song(slug: str, request: Request):
    doc = db["song"].find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Song not found")
    storage_path = doc.get("storage_path")
    if not storage_path or not os.path.exists(storage_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    # Record analytics
    record_event(slug, "download", request)

    return FileResponse(
        storage_path,
        media_type=doc.get("content_type", "application/octet-stream"),
        filename=doc.get("filename", f"{slug}.audio"),
    )


class AnalyticsOut(BaseModel):
    total_songs: int
    total_downloads: int
    total_views: int


@app.get("/api/analytics", response_model=AnalyticsOut)
def analytics():
    docs = get_documents("song")
    total_songs = len(docs)
    total_downloads = sum(int(d.get("downloads", 0)) for d in docs)
    total_views = sum(int(d.get("views", 0)) for d in docs)
    return AnalyticsOut(
        total_songs=total_songs,
        total_downloads=total_downloads,
        total_views=total_views,
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
