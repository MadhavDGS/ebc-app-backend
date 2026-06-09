from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from pydantic import BaseModel
import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Appwrite configurationg
client = Client()
client.set_endpoint(os.getenv('APPWRITE_ENDPOINT'))
client.set_project(os.getenv('APPWRITE_PROJECT_ID'))
client.set_key(os.getenv('APPWRITE_API_KEY'))

databases = Databases(client)
database_id = os.getenv('APPWRITE_DATABASE_ID')
collection_id = os.getenv('APPWRITE_PROFILE_COLLECTION_ID')

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def doc_to_member(doc) -> dict:
    """Convert an Appwrite Document object to a plain member dict."""
    d = doc.to_dict()
    data = d.get('data', {})
    return {
        'id': d.get('$id', ''),
        'name': data.get('name') or data.get('full_name') or '',
        'profession': data.get('profession') or data.get('role') or '',
        'area': data.get('area') or '',
        'bio': data.get('bio') or '',
        'whyJoined': data.get('whyJoined') or '',
        'whatTheyExpect': data.get('whatTheyExpect') or '',
        'howTheyCanHelp': data.get('howTheyCanHelp') or '',
        'linkedIn': data.get('linkedIn') or data.get('linkedin_url') or '',
        'instagram': data.get('instagram') or data.get('instagram_url') or '',
        'portfolio': data.get('portfolio') or '',
        'tags': data.get('tags') or [],
        'email': data.get('email') or '',
        'phone': data.get('phone') or '',
        # Return Cloudinary URL or empty string (never None)
        'avatar': data.get('avatar') or '',
    }


def optimize_cloudinary_url(url: str, width: int = 200) -> str:
    """Inject Cloudinary transformation for optimized avatars."""
    if not url or 'cloudinary.com' not in url:
        return url
    return url.replace('/upload/', f'/upload/w_{width},h_{width},c_fill,q_auto,f_auto,r_max/')


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(request: LoginRequest):
    try:
        response = databases.list_documents(
            database_id,
            collection_id,
            [Query.equal('email', request.email)]
        )
        docs = response.documents
        if not docs:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user_dict = docs[0].to_dict()
        user_data = user_dict.get('data', {})
        avatar_raw = user_data.get('avatar') or ''
        return {
            "token": "mock-jwt-token-for-testing",
            "user": {
                "$id": user_dict.get('$id', ''),
                "name": user_data.get('name') or user_data.get('full_name') or '',
                "email": user_data.get('email', ''),
                "avatar": optimize_cloudinary_url(avatar_raw),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Members ──────────────────────────────────────────────────────────────────

@app.get("/api/members")
def get_members():
    try:
        response = databases.list_documents(database_id, collection_id)
        members = []
        for doc in response.documents:
            m = doc_to_member(doc)
            m['avatar'] = optimize_cloudinary_url(m['avatar'])
            members.append(m)
        return members
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/members/me")
def get_member_me(email: str = None):
    try:
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
            
        response = databases.list_documents(
            database_id, 
            collection_id,
            [Query.equal('email', email)]
        )
        
        docs = response.documents
        if not docs:
            raise HTTPException(status_code=404, detail="Profile not found")
            
        m = doc_to_member(docs[0])
        m['avatar'] = optimize_cloudinary_url(m['avatar'])
        return m
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/members/{member_id}")
def get_member(member_id: str):
    try:
        doc = databases.get_document(database_id, collection_id, member_id)
        m = doc_to_member(doc)
        m['avatar'] = optimize_cloudinary_url(m['avatar'])
        return m
    except Exception as e:
        return {"error": str(e)}


# ─── Avatar Upload ────────────────────────────────────────────────────────────

@app.post("/api/members/{member_id}/avatar")
async def upload_avatar(member_id: str, file: UploadFile = File(...)):
    """
    Upload an avatar image to Cloudinary and store the resulting URL
    back into the member's Appwrite document.
    """
    try:
        contents = await file.read()

        # Upload to Cloudinary
        result = cloudinary.uploader.upload(
            contents,
            folder="ebc_avatars",
            public_id=f"member_{member_id}",
            overwrite=True,
            resource_type="image",
            transformation=[
                {"width": 400, "height": 400, "crop": "fill", "gravity": "face"},
                {"quality": "auto", "fetch_format": "auto"},
            ]
        )
        avatar_url = result.get("secure_url", "")

        # Update the Appwrite document's data.avatar field
        # Appwrite stores custom fields inside 'data' map field
        databases.update_document(
            database_id,
            collection_id,
            member_id,
            {"data": {"avatar": avatar_url}}
        )

        return {"avatar_url": avatar_url, "message": "Avatar uploaded successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "EBC Community API"}
