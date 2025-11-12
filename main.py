import os
import secrets
from typing import Optional, List, Any
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from database import db, create_document, get_documents

app = FastAPI(title="SongShare API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def read_root():
    return {"message": "SongShare backend running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
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
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ---------------------- Song Upload & Sharing ----------------------

@app.post("/api/songs/upload")
async def upload_song(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str = Form(...),
    description: Optional[str] = Form(None),
):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    # Validate file type (basic check)
    allowed = {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/flac", "audio/aac", "audio/ogg", "audio/mp4", "audio/x-m4a"}
    if file.content_type not in allowed:
        # Allow unknown audio as fallback if extension looks like audio
        allowed_exts = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".mp4"}
        _, ext = os.path.splitext(file.filename)
        if ext.lower() not in allowed_exts:
            raise HTTPException(status_code=400, detail="Unsupported audio format")

    token = secrets.token_urlsafe(10)
    _, ext = os.path.splitext(file.filename)
    safe_ext = ext if ext else ""
    stored_filename = f"{token}{safe_ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)

    size = 0
    with open(file_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)

    doc = {
        "title": title,
        "artist": artist,
        "description": description,
        "token": token,
        "file_path": file_path,
        "original_filename": file.filename,
        "mime_type": file.content_type,
        "size_bytes": size,
        "download_count": 0,
    }

    song_id = create_document("song", doc)

    backend_url = os.getenv("BACKEND_URL") or ""
    download_url = f"{backend_url}/api/songs/{token}/download" if backend_url else f"/api/songs/{token}/download"
    meta_url = f"{backend_url}/api/songs/{token}" if backend_url else f"/api/songs/{token}"

    return {
        "id": song_id,
        "token": token,
        "download_url": download_url,
        "meta_url": meta_url,
    }


@app.get("/api/songs/{token}")
async def get_song(token: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    doc = db["song"].find_one({"token": token}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Song not found")

    # Build a safe response without exposing file_path
    backend_url = os.getenv("BACKEND_URL") or ""
    download_url = f"{backend_url}/api/songs/{token}/download" if backend_url else f"/api/songs/{token}/download"

    return {
        "title": doc.get("title"),
        "artist": doc.get("artist"),
        "description": doc.get("description"),
        "token": doc.get("token"),
        "size_bytes": doc.get("size_bytes"),
        "mime_type": doc.get("mime_type"),
        "download_count": doc.get("download_count", 0),
        "download_url": download_url,
        "original_filename": doc.get("original_filename"),
    }


@app.get("/api/songs/{token}/download")
async def download_song(token: str, request: Request):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    doc = db["song"].find_one({"token": token})
    if not doc:
        raise HTTPException(status_code=404, detail="Song not found")

    file_path = doc.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File missing on server")

    # Increment download count and log analytics
    db["song"].update_one({"_id": doc["_id"]}, {"$inc": {"download_count": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}})

    # Record analytics event
    try:
        analytics_doc = {
            "token": token,
            "song_title": doc.get("title"),
            "event": "download",
            "ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "referer": request.headers.get("referer"),
            "timestamp": datetime.now(timezone.utc),
        }
        db["analytics"].insert_one(analytics_doc)
    except Exception:
        pass

    filename = doc.get("original_filename") or os.path.basename(file_path)
    return FileResponse(path=file_path, media_type=doc.get("mime_type") or "application/octet-stream", filename=filename)


# ---------------------- Analytics ----------------------

@app.get("/api/analytics/overview")
async def analytics_overview(limit: int = 10):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    total_songs = db["song"].count_documents({})
    total_downloads = db["song"].aggregate([
        {"$group": {"_id": None, "count": {"$sum": "$download_count"}}}
    ])
    total_downloads_val = 0
    for row in total_downloads:
        total_downloads_val = row.get("count", 0)

    top_songs_cursor = db["song"].find({}, {"_id": 0, "title": 1, "artist": 1, "download_count": 1}).sort("download_count", -1).limit(limit)
    top_songs = list(top_songs_cursor)

    recent_downloads_cursor = db["analytics"].find({"event": "download"}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    recent_downloads = list(recent_downloads_cursor)

    return {
        "total_songs": total_songs,
        "total_downloads": total_downloads_val,
        "top_songs": top_songs,
        "recent_downloads": recent_downloads,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
