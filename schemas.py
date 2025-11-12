"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Add your own schemas here:
# --------------------------------------------------

class Song(BaseModel):
    """
    Songs collection schema
    Collection name: "song"
    """
    title: str = Field(..., description="Song title")
    artist: str = Field(..., description="Artist name or uploader")
    description: Optional[str] = Field(None, description="Song description")
    token: str = Field(..., description="Public token used for sharing and download")
    file_path: str = Field(..., description="Server path where the file is stored")
    original_filename: str = Field(..., description="Original uploaded filename")
    mime_type: Optional[str] = Field(None, description="MIME type of the uploaded file")
    size_bytes: Optional[int] = Field(None, ge=0, description="File size in bytes")
    download_count: int = Field(0, ge=0, description="Number of downloads")
