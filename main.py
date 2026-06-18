import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", module="appwrite")

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from pydantic import BaseModel
import os
import cloudinary
import cloudinary.uploader
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

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
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()
    if hasattr(obj, '__dict__'):
        return vars(obj)
    return {}

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
        # 1. Fetch all reservations to find approved emails
        approved_emails = set()
        req_queries = [Query.limit(100)]
        while True:
            res_response = databases.list_documents(
                database_id, RESERVATIONS_COLLECTION, req_queries
            )
            docs = get_docs(res_response)
            if not docs:
                break
            for d in docs:
                data = as_dict(d).get('data', as_dict(d))
                tid = data.get('ticket_id', '')
                if tid and tid not in ('PENDING', 'REJECTED'):
                    approved_emails.add(data.get('user_email'))
            if len(docs) < 100:
                break
            req_queries = [Query.limit(100), Query.cursorAfter(docs[-1]['$id'])]

        # 2. Fetch all members and filter
        members = []
        mem_queries = [Query.limit(100)]
        while True:
            response = databases.list_documents(database_id, collection_id, mem_queries)
            docs = get_docs(response)
            if not docs:
                break
            for doc in docs:
                m = doc_to_member(doc)
                if m.get('email') in approved_emails:
                    m['avatar'] = optimize_cloudinary_url(m['avatar'])
                    members.append(m)
            if len(docs) < 100:
                break
            mem_queries = [Query.limit(100), Query.cursorAfter(docs[-1]['$id'])]
            
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


@app.put("/api/members/{email}")
def update_member_by_email(email: str, payload: dict):
    try:
        # Find the user by email
        # Find the user by email
        response = databases.list_documents(
            database_id,
            collection_id,
            [Query.equal('email', email)]
        )
        docs = get_docs(response)
        if not docs:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        doc_dict = as_dict(docs[0])
        doc_id = doc_dict.get('$id')
        if not doc_id:
            raise HTTPException(status_code=500, detail="Missing document ID")
            
        # Prepare the update data mapping
        update_data = {}
        if 'full_name' in payload:
            update_data['name'] = payload['full_name']
            update_data['full_name'] = payload['full_name']
        if 'profession' in payload:
            update_data['role'] = payload['profession']
            update_data['profession'] = payload['profession']
        # Company attribute doesn't exist in the database schema yet
        # if 'company' in payload:
        #     update_data['company'] = payload['company']
        if 'location' in payload:
            update_data['area'] = payload['location']
        if 'bio' in payload:
            update_data['bio'] = payload['bio']
        if 'linkedin' in payload:
            update_data['linkedIn'] = payload['linkedin']
        if 'instagram' in payload:
            update_data['instagram'] = payload['instagram']
            
        # Update the document
        updated_doc = databases.update_document(
            database_id,
            collection_id,
            doc_id,
            update_data
        )
        
        m = doc_to_member(updated_doc)
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
    price: int = 422


class ReservationCreate(BaseModel):
    meetup_id: str
    user_email: str
    user_name: str
    quantity: int = 1
    answers: str = "{}"
    status: str = "confirmed"        # "confirmed" or "pending_payment"
    expires_at: str = ""             # ISO string, only used for pending_payment


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
        'price': data.get('Price', data.get('price', 422)),
        'created_at': d.get('$createdAt', ''),
    }


def doc_to_reservation(doc) -> dict:
    d = as_dict(doc)
    data = d.get('data', d)
    
    # Calculate status based on ticket_id without needing a DB column
    ticket = data.get('ticket_id', '')
    if ticket == 'PENDING':
        status = 'pending_payment'
    elif ticket == 'REJECTED':
        status = 'rejected'
    else:
        status = 'confirmed'

    return {
        'id': d.get('$id', ''),
        'meetup_id': data.get('meetup_id', ''),
        'user_email': data.get('user_email', ''),
        'user_name': data.get('user_name', ''),
        'quantity': data.get('quantity', 1),
        'ticket_id': ticket,
        'answers': data.get('answers', '{}'),
        'status': status,
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
            valid_docs = [doc for doc in get_docs(res) if (as_dict(doc).get('data', as_dict(doc))).get('ticket_id') != 'REJECTED']
            total_seats = sum(
                (as_dict(doc).get('data', as_dict(doc))).get('quantity', 1)
                for doc in valid_docs
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
        data = meetup.model_dump()
        data['Price'] = data.pop('price', 422)
        doc = databases.create_document(
            database_id, MEETUPS_COLLECTION, 'unique()',
            data
        )
        return doc_to_meetup(doc)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/meetups/{meetup_id}")
def update_meetup(meetup_id: str, meetup: MeetupCreate):
    try:
        data = meetup.model_dump()
        data['Price'] = data.pop('price', 422)
        doc = databases.update_document(
            database_id, MEETUPS_COLLECTION, meetup_id,
            data
        )
        return doc_to_meetup(doc)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reservations/pending")
def get_pending_reservations(request_admin_email: str = ""):
    """Return all pending_payment, expired, and rejected reservations for admin review."""
    try:
        all_docs = []
        queries = [Query.limit(100)]
        while True:
            response = databases.list_documents(
                database_id, RESERVATIONS_COLLECTION,
                queries
            )
            docs = get_docs(response)
            if not docs:
                break
            all_docs.extend(docs)
            if len(docs) < 100:
                break
            # Use the last document ID as the cursor for the next page
            last_id = docs[-1]['$id']
            queries = [Query.limit(100), Query.cursorAfter(last_id)]

        results = []
        for doc in all_docs:
            r = doc_to_reservation(doc)
            if r['status'] in ('pending_payment', 'expired', 'rejected'):
                try:
                    meetup_doc = databases.get_document(database_id, MEETUPS_COLLECTION, r['meetup_id'])
                    r['meetup'] = doc_to_meetup(meetup_doc)
                except Exception:
                    r['meetup'] = None
                results.append(r)
        
        # Sort in Python to avoid Appwrite missing index errors on $createdAt
        results.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reservations/{meetup_id}")
def get_reservations(meetup_id: str):
    try:
        results = []
        queries = [Query.equal('meetup_id', meetup_id), Query.limit(100)]
        while True:
            response = databases.list_documents(
                database_id, RESERVATIONS_COLLECTION, queries
            )
            docs = get_docs(response)
            if not docs:
                break
            
            # Filter out pending and rejected reservations
            for doc in docs:
                r = doc_to_reservation(doc)
                if r['status'] not in ('pending_payment', 'rejected'):
                    results.append(r)
                    
            if len(docs) < 100:
                break
            queries = [Query.equal('meetup_id', meetup_id), Query.limit(100), Query.cursorAfter(docs[-1]['$id'])]
                
        return results
    except Exception as e:
        return []


@app.get("/api/users/{email}/reservations")
def get_user_reservations(email: str):
    try:
        response = databases.list_documents(
            database_id,
            RESERVATIONS_COLLECTION,
            [Query.equal('user_email', email)]
        )
        reservations = []
        for doc in get_docs(response):
            res_dict = doc_to_reservation(doc)
            try:
                meetup_doc = databases.get_document(database_id, MEETUPS_COLLECTION, res_dict['meetup_id'])
                res_dict['meetup'] = doc_to_meetup(meetup_doc)
            except Exception as e:
                res_dict['meetup'] = None
            reservations.append(res_dict)
        return reservations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TicketScanRequest(BaseModel):
    ticket_id: str
    action: str = "check_in"  # "check_in" | "check_out"

class ReservationStatusUpdate(BaseModel):
    status: str

@app.put("/api/reservations/{reservation_id}/status")
def update_reservation_status(reservation_id: str, payload: ReservationStatusUpdate):
    try:
        is_checked_in = payload.status == 'checked_in'
        updated_doc = databases.update_document(
            database_id,
            RESERVATIONS_COLLECTION,
            reservation_id,
            {'checked_in': is_checked_in}
        )
        return doc_to_reservation(updated_doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tickets/scan")
def scan_ticket(req: TicketScanRequest):
    ticket_id = req.ticket_id
    action = req.action
    if not ticket_id:
        raise HTTPException(status_code=400, detail="Ticket ID is required")
    
    try:
        response = databases.list_documents(
            database_id, RESERVATIONS_COLLECTION,
            [Query.equal('ticket_id', ticket_id)]
        )
        docs = get_docs(response)
        if not docs:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        res_doc = docs[0]
        res_dict = doc_to_reservation(res_doc)
        
        new_status = 'checked_in' if action == 'check_in' else 'confirmed'
        
        updated_doc = databases.update_document(
            database_id,
            RESERVATIONS_COLLECTION,
            res_dict['id'],
            {
                'status': new_status
            }
        )
        
        meetup_doc = databases.get_document(database_id, MEETUPS_COLLECTION, res_dict['meetup_id'])
        meetup_dict = doc_to_meetup(meetup_doc)
        
        return {
            "status": "success",
            "message": f"Successfully {'checked in' if action == 'check_in' else 'checked out'} {res_dict['user_name']}",
            "reservation": doc_to_reservation(updated_doc),
            "meetup": meetup_dict
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def send_ticket_email(email_to: str, user_name: str, meetup_title: str, ticket_id: str, qr_url: str):
    import os
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = os.getenv('SMTP_PORT', '587')
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')

    print(f"\n=======================================================")
    print(f"📧 [PREVIEW] Ticket Confirmation Email Generated:")
    print(f"   To: {email_to}")
    print(f"   Attendee Name: {user_name}")
    print(f"   Event: {meetup_title}")
    print(f"   Ticket ID: {ticket_id}")
    print(f"   QR Code URL: {qr_url}")
    print(f"=======================================================\n")

    if not smtp_host or not smtp_user or not smtp_password:
        print("⚠️ SMTP credentials missing in environment. Email transmission skipped (logged to stdout).")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Your Ticket for {meetup_title} - Perenti Pass"
        msg['From'] = f"Perenti Community <{smtp_user}>"
        msg['To'] = email_to

        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #0d0f12; color: #ffffff; padding: 20px;">
            <div style="max-width: 500px; margin: 0 auto; background-color: #15191f; border: 1px solid #232a35; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
              <div style="background-color: #03d47c; padding: 15px; text-align: center; color: #061B0F; font-weight: bold; font-size: 18px; letter-spacing: 0.05em; text-transform: uppercase;">
                perenti pass
              </div>
              <div style="padding: 25px;">
                <h2 style="color: #ffffff; margin-top: 0;">Hey {user_name}!</h2>
                <p style="color: #a0aec0; line-height: 1.5;">Your registration for <strong>{meetup_title}</strong> is confirmed. Below is your entry pass.</p>
                
                <div style="border: 1px dashed #2d3748; padding: 20px; border-radius: 8px; background-color: #0d0f12; margin: 20px 0; text-align: center;">
                  <h3 style="margin: 0 0 15px 0; color: #ffffff;">{meetup_title}</h3>
                  <p style="color: #a0aec0; font-size: 14px; margin: 5px 0;">Show this QR code at the venue entrance:</p>
                  
                  <img src="{qr_url}" alt="Ticket QR Code" style="border: 8px solid #ffffff; border-radius: 6px; margin: 15px auto; display: block;" width="150" height="150" />
                  
                  <div style="font-family: monospace; background-color: #1a202c; color: #e2e8f0; padding: 8px; border-radius: 4px; display: inline-block; font-size: 12px; margin-top: 10px;">
                    {ticket_id}
                  </div>
                </div>
                
                <p style="color: #a0aec0; font-size: 12px; text-align: center; margin-top: 30px;">
                  Perenti Community &bull; Hyderabad, India
                </p>
              </div>
            </div>
          </body>
        </html>
        """

        part = MIMEText(html, 'html')
        msg.attach(part)

        server = smtplib.SMTP(smtp_host, int(smtp_port))
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, email_to, msg.as_string())
        server.quit()
        print(f"📧 Ticket email successfully sent to {email_to}")
        return True
    except Exception as e:
        print(f"❌ Failed to dispatch ticket email: {e}")
        return False


class StatusUpdateRequest(BaseModel):
    status: str


@app.put("/api/reservations/{reservation_id}/status")
def update_reservation_status(reservation_id: str, req: StatusUpdateRequest):
    try:
        if req.status == 'confirmed':
            import random, string
            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            new_ticket_id = f"PRNT-EBC-{suffix}"
            
            doc = databases.update_document(
                database_id,
                RESERVATIONS_COLLECTION,
                reservation_id,
                {'ticket_id': new_ticket_id}
            )
            
            # Send email
            try:
                res_dict = doc_to_reservation(doc)
                meetup_doc = databases.get_document(database_id, MEETUPS_COLLECTION, res_dict['meetup_id'])
                meetup_data = as_dict(meetup_doc).get('data', as_dict(meetup_doc))
                meetup_title = meetup_data.get('title', 'Perenti Meetup')
                
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={new_ticket_id}"
                send_ticket_email(res_dict['user_email'], res_dict['user_name'], meetup_title, new_ticket_id, qr_url)
            except Exception as mail_err:
                print(f"⚠️ Non-blocking email dispatch error: {mail_err}")
                
        elif req.status == 'rejected':
            doc = databases.update_document(
                database_id,
                RESERVATIONS_COLLECTION,
                reservation_id,
                {'ticket_id': 'REJECTED'}
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid status")
            
        return doc_to_reservation(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reservations")
def create_reservation(res: ReservationCreate):
    try:
        import random, string
        from datetime import datetime, timezone

        # Check capacity
        meetup_doc = databases.get_document(database_id, MEETUPS_COLLECTION, res.meetup_id)
        meetup_data = as_dict(meetup_doc).get('data', as_dict(meetup_doc))
        capacity = meetup_data.get('capacity', 60)
        meetup_title = meetup_data.get('title', 'Perenti Meetup')

        existing = databases.list_documents(
            database_id, RESERVATIONS_COLLECTION,
            [Query.equal('meetup_id', res.meetup_id)]
        )
        valid_existing = [d for d in get_docs(existing) if (as_dict(d).get('data', as_dict(d))).get('ticket_id') != 'REJECTED']
        
        # Prevent duplicate registrations
        user_already_registered = any(
            (as_dict(d).get('data', as_dict(d))).get('user_email') == res.user_email
            for d in valid_existing
        )
        if user_already_registered:
            raise HTTPException(status_code=400, detail="You have already registered for this meetup.")

        total_booked = sum(
            (as_dict(d).get('data', as_dict(d))).get('quantity', 1)
            for d in valid_existing
        )
        if total_booked + res.quantity > capacity:
            raise HTTPException(status_code=400, detail="Not enough seats remaining.")

        is_pending = res.status == 'pending_payment'

        # Instead of adding a new 'status' column to the database schema, 
        # we just save 'PENDING' in the existing 'ticket_id' column to mark it.
        ticket_id = 'PENDING'
        if not is_pending:
            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            ticket_id = f"PRNT-EBC-{suffix}"

        doc_data = {
            'meetup_id': res.meetup_id,
            'user_email': res.user_email,
            'user_name': res.user_name,
            'quantity': res.quantity,
            'ticket_id': ticket_id,
            'answers': res.answers,
        }

        doc = databases.create_document(
            database_id, RESERVATIONS_COLLECTION, 'unique()', doc_data
        )

        # Send confirmation email only for immediately confirmed reservations
        if not is_pending and ticket_id != 'PENDING':
            try:
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={ticket_id}"
                send_ticket_email(res.user_email, res.user_name, meetup_title, ticket_id, qr_url)
            except Exception as mail_err:
                print(f"⚠️ Non-blocking email dispatch error: {mail_err}")

        return doc_to_reservation(doc)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── Admin Approval Endpoints ─────────────────────────────────────────────────

ADMIN_EMAILS = [
    'admin@perenti.com', 'sreemadhav@gmail.com',
    'madhav@ebc.com', 'shiva24.santosh@gmail.com'
]




@app.put("/api/reservations/{reservation_id}/approve")
def approve_reservation(reservation_id: str):
    """Admin approves a pending_payment reservation — generates ticket_id and confirms."""
    try:
        import random, string

        doc = databases.get_document(database_id, RESERVATIONS_COLLECTION, reservation_id)
        res_dict = doc_to_reservation(doc)

        if res_dict['status'] not in ('pending_payment',):
            raise HTTPException(status_code=400, detail=f"Reservation is not pending (status={res_dict['status']})")

        # Generate ticket ID now
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        ticket_id = f"PRNT-EBC-{suffix}"

        updated_doc = databases.update_document(
            database_id, RESERVATIONS_COLLECTION, reservation_id,
            {'ticket_id': ticket_id}
        )

        # Send confirmation email
        try:
            meetup_doc = databases.get_document(database_id, MEETUPS_COLLECTION, res_dict['meetup_id'])
            meetup_title = as_dict(meetup_doc).get('data', as_dict(meetup_doc)).get('title', 'EBC Meetup')
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={ticket_id}"
            send_ticket_email(res_dict['user_email'], res_dict['user_name'], meetup_title, ticket_id, qr_url)
        except Exception as mail_err:
            print(f"⚠️ Non-blocking email dispatch error: {mail_err}")

        return doc_to_reservation(updated_doc)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/reservations/{reservation_id}/reject")
def reject_reservation(reservation_id: str):
    """Admin rejects a pending_payment reservation."""
    try:
        updated_doc = databases.update_document(
            database_id, RESERVATIONS_COLLECTION, reservation_id,
            {'ticket_id': 'REJECTED'}
        )
        return doc_to_reservation(updated_doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "EBC Community API — Perenti"}
