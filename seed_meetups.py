#!/usr/bin/env python3
"""
Seed script — creates the meetups + reservations collections in Appwrite
and adds the EBC 28th Meetup as the first event.
Run from EBC-APP-Backend directory:
  python seed_meetups.py
"""

import os, sys, json, requests
from dotenv import load_dotenv

load_dotenv()

ENDPOINT   = os.getenv('APPWRITE_ENDPOINT', 'https://fra.cloud.appwrite.io/v1')
PROJECT_ID = os.getenv('APPWRITE_PROJECT_ID')
API_KEY    = os.getenv('APPWRITE_API_KEY')
DATABASE_ID = os.getenv('APPWRITE_DATABASE_ID', 'community_app_db')

HEADERS = {
    'Content-Type': 'application/json',
    'X-Appwrite-Project': PROJECT_ID,
    'X-Appwrite-Key': API_KEY,
}

def api(method, path, body=None):
    url = f"{ENDPOINT}{path}"
    resp = requests.request(method, url, headers=HEADERS, json=body)
    if resp.status_code not in (200, 201):
        print(f"  ⚠️  {method} {path} → {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()

def create_collection(col_id, name, attrs):
    """Create collection if it doesn't exist."""
    existing = api('GET', f'/databases/{DATABASE_ID}/collections/{col_id}')
    if existing:
        print(f"  ✓ Collection '{col_id}' already exists.")
        return

    print(f"  Creating collection '{col_id}'…")
    result = api('POST', f'/databases/{DATABASE_ID}/collections', {
        'collectionId': col_id,
        'name': name,
        'documentSecurity': False,
        'permissions': ['read("any")', 'create("any")', 'update("users")']
    })
    if not result:
        print(f"  ✗ Failed to create collection '{col_id}'. Check permissions.")
        return

    for attr in attrs:
        atype = attr.pop('type')
        required = attr.pop('required', False)
        default = attr.pop('default', None)
        key = attr.get('key')
        print(f"    Adding attribute '{key}' ({atype})…")
        body = {**attr, 'required': required}
        if default is not None:
            body['default'] = default
        api('POST', f'/databases/{DATABASE_ID}/collections/{col_id}/attributes/{atype}', body)

    print(f"  ✓ Collection '{col_id}' created.")


def seed_meetup():
    """Create the EBC 28th Meetup document."""
    col = 'meetups'
    # Check if any meetup already exists
    docs = api('GET', f'/databases/{DATABASE_ID}/collections/{col}/documents?limit=5')
    if docs and docs.get('total', 0) > 0:
        print(f"\n  ✓ Meetup already seeded ({docs['total']} meetup(s) found). Skipping.")
        return

    print(f"\n  Seeding EBC 28th Meetup…")
    body = {
        'documentId': 'unique()',
        'data': {
            'title': 'EBC 28th Meetup',
            'description': "Join us at the EBC 28th meetup, where aspiring founders, business owners, professionals, and students can share their stories. You'll have one minute to introduce yourself and discuss what you're building.",
            'date': 'Sunday, June 29th 2026',
            'time': '9:00 AM – 11:00 AM (IST)',
            'venue': 'Birch Cafe Vanasthalipuram, Hyderabad',
            'banner_url': '/meetup_banner.jpg',
            'capacity': 60,
            'is_active': True,
        },
        'permissions': ['read("any")', 'write("users")']
    }
    result = api('POST', f'/databases/{DATABASE_ID}/collections/{col}/documents', body)
    if result:
        print(f"  ✓ Meetup created: {result.get('$id')}")
    else:
        print("  ✗ Failed to seed meetup.")


if __name__ == '__main__':
    print("\n🚀 Perenti — Appwrite Collection Setup\n")

    # ── meetups collection ────────────────────────────────────────────────────
    create_collection('meetups', 'Meetups', [
        {'type': 'string', 'key': 'title',       'size': 256, 'required': True},
        {'type': 'string', 'key': 'description', 'size': 4096, 'required': False, 'default': ''},
        {'type': 'string', 'key': 'date',        'size': 128, 'required': False, 'default': ''},
        {'type': 'string', 'key': 'time',        'size': 128, 'required': False, 'default': ''},
        {'type': 'string', 'key': 'venue',       'size': 256, 'required': False, 'default': ''},
        {'type': 'string', 'key': 'banner_url',  'size': 1024, 'required': False, 'default': ''},
        {'type': 'integer','key': 'capacity',    'required': False, 'default': 60},
        {'type': 'boolean','key': 'is_active',   'required': False, 'default': True},
    ])

    # ── reservations collection ───────────────────────────────────────────────
    create_collection('reservations', 'Reservations', [
        {'type': 'string',  'key': 'meetup_id',   'size': 256,  'required': True},
        {'type': 'string',  'key': 'user_email',  'size': 256,  'required': True},
        {'type': 'string',  'key': 'user_name',   'size': 256,  'required': False, 'default': ''},
        {'type': 'integer', 'key': 'quantity',    'required': False, 'default': 1},
        {'type': 'string',  'key': 'ticket_id',   'size': 64,   'required': False, 'default': ''},
        {'type': 'string',  'key': 'answers',     'size': 4096, 'required': False, 'default': '{}'},
        {'type': 'string',  'key': 'status',      'size': 32,   'required': False, 'default': 'confirmed'},
    ])

    # ── seed meetup ───────────────────────────────────────────────────────────
    seed_meetup()

    print("\n✅ Done! Collections ready. Deploy your backend to Render now.\n")
