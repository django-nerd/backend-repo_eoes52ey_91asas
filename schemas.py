"""
Database Schemas for the Song Distribution Platform

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercased class name. Example: class Song -> "song" collection.
"""

from pydantic import BaseModel, Field
from typing import Optional, List

class Song(BaseModel):
    """
    Songs collection schema
    Collection name: "song"
    """
    title: str = Field(..., description="Song title")
    artist: str = Field(..., description="Artist name")
    description: Optional[str] = Field(None, description="Short description")
    slug: str = Field(..., description="Public share identifier")
    filename: str = Field(..., description="Original filename")
    storage_path: str = Field(..., description="Server storage path for the file")
    content_type: str = Field(..., description="MIME type of the uploaded file")
    size: int = Field(..., ge=0, description="File size in bytes")
    downloads: int = Field(0, ge=0, description="Total download count")
    views: int = Field(0, ge=0, description="Total view count")

class Event(BaseModel):
    """
    Analytics events collection schema
    Collection name: "event"
    """
    song_slug: str = Field(..., description="Slug of the song involved in the event")
    event_type: str = Field(..., description="Type of event: view|download")
    user_agent: Optional[str] = Field(None, description="User agent string")
    ip: Optional[str] = Field(None, description="Client IP address")
