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

def as_dict(obj):
    return obj if isinstance(obj, dict) else getattr(obj, 'to_dict', lambda: obj)()

def get_docs(response):
    if isinstance(response, dict):
        return response.get('documents', [])
    return getattr(response, 'documents', [])

def doc_to_member(doc) -> dict:
    """Convert an Appwrite Document object to a plain member dict."""
    if not doc:
        return {}
    d = as_dict(doc)
    data = d.get('data', d)
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

class MemberCreate(BaseModel):
    full_name: str
    email: str
    profession: str = ""
    company: str = ""
    location: str = ""
    bio: str = ""
    tags: list = []
    avatar_url: str = ""


@app.post("/api/auth/login")
def login(request: LoginRequest):
    try:
        response = databases.list_documents(
            database_id,
            collection_id,
            [Query.equal('email', request.email)]
        )
        docs = get_docs(response)
        if not docs:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user_dict = as_dict(docs[0])
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

@app.post("/api/members")
def create_member(member: MemberCreate):
    import uuid
    try:
        data = member.dict()
        doc = databases.create_document(
            database_id, collection_id, 'unique()',
            {
                'user_id': uuid.uuid4().hex,
                'full_name': data['full_name'],
                'role': data['profession'],
                'name': data['full_name'],
                'email': data['email'],
                'profession': data['profession'],
                'area': data['location'],
                'bio': data['bio'],
                'tags': data['tags'],
                'avatar': data['avatar_url'],
                'whyJoined': '',
                'whatTheyExpect': '',
                'howTheyCanHelp': '',
                'linkedIn': '',
                'instagram': '',
                'portfolio': '',
                'phone': ''
            }
        )
        m = doc_to_member(doc)
        m['avatar'] = optimize_cloudinary_url(m['avatar'])
        return m
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/members")
def get_members():
    try:
        response = databases.list_documents(database_id, collection_id)
        members = []
        for doc in get_docs(response):
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
        
        docs = get_docs(response)
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


# ─── Chat ───────────────────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    sender_id: str
    receiver_id: str
    content: str

@app.get("/api/chat/messages")
def get_messages(user1: str, user2: str):
    """
    Get messages between two users.
    """
    try:
        # Appwrite limitation: We cannot do complex OR queries easily without multiple queries or index requirements.
        # We will fetch messages where sender=user1 and receiver=user2, and vice versa, then merge and sort.
        res1 = databases.list_documents(
            database_id,
            'messages',
            [Query.equal('sender_id', user1), Query.equal('receiver_id', user2), Query.limit(100)]
        )
        res2 = databases.list_documents(
            database_id,
            'messages',
            [Query.equal('sender_id', user2), Query.equal('receiver_id', user1), Query.limit(100)]
        )
        
        all_docs = get_docs(res1) + get_docs(res2)
        all_docs.sort(key=lambda x: x.get('timestamp', ''), reverse=False)
        
        return [as_dict(doc) for doc in all_docs]
    except Exception as e:
        print(f"Error fetching messages: {e}")
        return []

@app.post("/api/chat/send")
def send_message(req: SendMessageRequest):
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        
        doc = databases.create_document(
            database_id,
            'messages',
            'unique()',
            {
                'sender_id': req.sender_id,
                'receiver_id': req.receiver_id,
                'content': req.content,
                'timestamp': now
            }
        )
        return as_dict(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Meetups ──────────────────────────────────────────────────────────────────

MEETUPS_COLLECTION = os.getenv('APPWRITE_MEETUPS_COLLECTION_ID', 'meetups')
RESERVATIONS_COLLECTION = os.getenv('APPWRITE_RESERVATIONS_COLLECTION_ID', 'reservations')


class MeetupCreate(BaseModel):
    title: str
    description: str
    date: str
    time: str
    venue: str
    banner_url: str = ""
    capacity: int = 60
    is_active: bool = True


class ReservationCreate(BaseModel):
    meetup_id: str
    user_email: str
    user_name: str
    quantity: int = 1
    answers: str = "{}"


def doc_to_meetup(doc) -> dict:
    d = as_dict(doc)
    data = d.get('data', d)
    return {
        'id': d.get('$id', ''),
        'title': data.get('title', ''),
        'description': data.get('description', ''),
        'date': data.get('date', ''),
        'time': data.get('time', ''),
        'venue': data.get('venue', ''),
        'banner_url': data.get('banner_url', ''),
        'capacity': data.get('capacity', 60),
        'is_active': data.get('is_active', True),
        'created_at': d.get('$createdAt', ''),
    }


def doc_to_reservation(doc) -> dict:
    d = as_dict(doc)
    data = d.get('data', d)
    return {
        'id': d.get('$id', ''),
        'meetup_id': data.get('meetup_id', ''),
        'user_email': data.get('user_email', ''),
        'user_name': data.get('user_name', ''),
        'quantity': data.get('quantity', 1),
        'ticket_id': data.get('ticket_id', ''),
        'answers': data.get('answers', '{}'),
        'status': data.get('status', 'confirmed'),
        'created_at': d.get('$createdAt', ''),
    }


@app.get("/api/meetups")
def get_meetups():
    try:
        response = databases.list_documents(database_id, MEETUPS_COLLECTION)
        return [doc_to_meetup(doc) for doc in get_docs(response)]
    except Exception as e:
        return {"error": str(e), "meetups": []}


@app.get("/api/meetups/{meetup_id}")
def get_meetup(meetup_id: str):
    try:
        doc = databases.get_document(database_id, MEETUPS_COLLECTION, meetup_id)
        meetup = doc_to_meetup(doc)
        # Count reservations
        try:
            res = databases.list_documents(
                database_id, RESERVATIONS_COLLECTION,
                [Query.equal('meetup_id', meetup_id)]
            )
            total_seats = sum(
                (as_dict(doc).get('data', as_dict(doc))).get('quantity', 1)
                for doc in get_docs(res)
            )
            meetup['registered_count'] = total_seats
            meetup['remaining'] = max(0, meetup['capacity'] - total_seats)
        except:
            meetup['registered_count'] = 0
            meetup['remaining'] = meetup['capacity']
        return meetup
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/meetups")
def create_meetup(meetup: MeetupCreate):
    try:
        doc = databases.create_document(
            database_id, MEETUPS_COLLECTION, 'unique()',
            meetup.dict()
        )
        return doc_to_meetup(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reservations/{meetup_id}")
def get_reservations(meetup_id: str):
    try:
        response = databases.list_documents(
            database_id, RESERVATIONS_COLLECTION,
            [Query.equal('meetup_id', meetup_id)]
        )
        return [doc_to_reservation(doc) for doc in get_docs(response)]
    except Exception as e:
        return []


@app.post("/api/reservations")
def create_reservation(res: ReservationCreate):
    try:
        import random, string
        from datetime import datetime, timezone

        # Check capacity
        meetup_doc = databases.get_document(database_id, MEETUPS_COLLECTION, res.meetup_id)
        meetup_data = as_dict(meetup_doc).get('data', as_dict(meetup_doc))
        capacity = meetup_data.get('capacity', 60)

        existing = databases.list_documents(
            database_id, RESERVATIONS_COLLECTION,
            [Query.equal('meetup_id', res.meetup_id)]
        )
        total_booked = sum(
            (as_dict(d).get('data', as_dict(d))).get('quantity', 1)
            for d in get_docs(existing)
        )
        if total_booked + res.quantity > capacity:
            raise HTTPException(status_code=400, detail="Not enough seats remaining.")

        # Generate ticket ID
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        ticket_id = f"PRNT-EBC-{suffix}"

        doc = databases.create_document(
            database_id, RESERVATIONS_COLLECTION, 'unique()',
            {
                'meetup_id': res.meetup_id,
                'user_email': res.user_email,
                'user_name': res.user_name,
                'quantity': res.quantity,
                'ticket_id': ticket_id,
                'answers': res.answers,
                'status': 'confirmed',
            }
        )
        return doc_to_reservation(doc)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "EBC Community API — Perenti"}
