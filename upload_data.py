import os
import pandas as pd
from dotenv import load_dotenv
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.exception import AppwriteException
import time
import math

load_dotenv()

client = Client()
client.set_endpoint(os.getenv('APPWRITE_ENDPOINT'))
client.set_project(os.getenv('APPWRITE_PROJECT_ID'))
client.set_key(os.getenv('APPWRITE_API_KEY'))

databases = Databases(client)

database_id = os.getenv('APPWRITE_DATABASE_ID')
collection_id = os.getenv('APPWRITE_PROFILE_COLLECTION_ID')

def create_attribute_if_not_exists(key, type='string', size=255, array=False):
    try:
        databases.create_string_attribute(database_id, collection_id, key, size, not array, None, array)
        print(f"Created attribute: {key}")
        time.sleep(1)  # wait for attribute to be created
    except AppwriteException as e:
        if e.code == 409: # Already exists
            pass
        else:
            print(f"Error creating attribute {key}: {e}")

def setup_collection():
    try:
        databases.get_collection(database_id, collection_id)
        print(f"Collection {collection_id} exists.")
    except AppwriteException as e:
        if e.code == 404:
            print(f"Creating collection {collection_id}...")
            databases.create_collection(database_id, collection_id, "Profiles")
            time.sleep(2)
        else:
            raise e

    # Create attributes
    create_attribute_if_not_exists('name', size=255)
    create_attribute_if_not_exists('profession', size=255)
    create_attribute_if_not_exists('area', size=255)
    create_attribute_if_not_exists('bio', size=2000)
    create_attribute_if_not_exists('whyJoined', size=2000)
    create_attribute_if_not_exists('whatTheyExpect', size=2000)
    create_attribute_if_not_exists('howTheyCanHelp', size=2000)
    create_attribute_if_not_exists('linkedIn', size=1000)
    create_attribute_if_not_exists('instagram', size=1000)
    create_attribute_if_not_exists('portfolio', size=1000)
    create_attribute_if_not_exists('tags', array=True, size=100)
    create_attribute_if_not_exists('email', size=255)
    create_attribute_if_not_exists('phone', size=255)
    create_attribute_if_not_exists('avatar', size=1000)
    
    print("Waiting for attributes to be fully available...")
    time.sleep(5)

def clean_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()

def process_csv():
    # Load CSV
    csv_file = 'Ekthaa Community Collaboration Matching Form (Responses) - Form Responses 1.csv'
    df = pd.read_csv(csv_file)
    
    print(f"Found {len(df)} records to process.")
    
    # We will randomly assign avatars from the mock set to make the UI look good
    mock_avatars = [
        '/avatars/avatar-girl-svgrepo-com.svg',
        '/avatars/avatar-boy-svgrepo-com.svg',
        '/avatars/avatar-girl-svgrepo-com-2.svg',
        '/avatars/avatar-boy-svgrepo-com-2.svg',
        '/avatars/avatar-girl-svgrepo-com-3.svg',
        '/avatars/avatar-boy-svgrepo-com-3.svg'
    ]
    
    for idx, row in df.iterrows():
        name = clean_str(row['Full Name'])
        if not name:
            continue
            
        area = clean_str(row['Current Location'])
        email = clean_str(row['Primary Contact Email ID'])
        phone = clean_str(row['Phone Number (Optional - For direct calls/SMS, not mandatory for community access)'])
        
        # Profession
        roles = clean_str(row['2. Who Are You? (Select all that apply for best matching)'])
        other_role = clean_str(row["If you selected 'Other', please specify your primary role:"])
        
        profession = "Member"
        if other_role:
            profession = other_role
        elif roles:
            profession = [r.strip() for r in roles.split(',')][0]
            
        # Bio
        focus = clean_str(row['3. Current Focus / Stage: What best describes you right now?'])
        skills = clean_str(row['4. Skills & Strengths: What core skills can you offer to others?'])
        other_skills = clean_str(row["If you selected 'Other Specialized Skill', please briefly list your key strengths:"])
        bio = f"{focus}. Skills: {skills}"
        if other_skills:
            bio += f". {other_skills}"
            
        # Why joined
        intent = clean_str(row['5. Collaboration Intent: What are you primarily looking for from the Ekthaa Community? (Select all that apply)'])
        other_intent = clean_str(row["If you have a specific goal not listed above, please describe it briefly:"])
        whyJoined = intent
        if other_intent:
            whyJoined += f" - {other_intent}"
            
        # What they expect
        expect = clean_str(row['7. Collaboration Preference: You are open to collaborate with (Select all relevant categories):'])
        
        # How they can help
        help_com = clean_str(row['6. How Can You Help the Community?'])
        
        # Tags
        tags = []
        if roles:
            tags.extend([r.strip() for r in roles.split(',') if r.strip() != 'Other'])
        # keep tags short
        tags = tags[:3]
        if not tags:
            tags = ["Member"]
            
        # Links
        linkedin = clean_str(row.get('LinkedIn Profile URL', ''))
        instagram = clean_str(row.get('Instagram Profile URL ', ''))
        portfolio = clean_str(row.get('Portfolio / Website / GitHub Link (Optional)', ''))
        
        avatar = mock_avatars[idx % len(mock_avatars)]
        
        doc = {
            'user_id': ID.unique(),
            'full_name': name,
            'role': profession,
            'name': name,
            'profession': profession,
            'area': area,
            'bio': bio[:2000],
            'whyJoined': whyJoined[:2000],
            'whatTheyExpect': expect[:2000],
            'howTheyCanHelp': help_com[:2000],
            'linkedIn': linkedin,
            'instagram': instagram,
            'portfolio': portfolio,
            'tags': tags,
            'email': email,
            'phone': phone,
            'avatar': avatar
        }
        
        try:
            databases.create_document(database_id, collection_id, ID.unique(), doc)
            print(f"Inserted: {name}")
        except Exception as e:
            print(f"Failed to insert {name}: {e}")

if __name__ == '__main__':
    print("Setting up Appwrite schema...")
    setup_collection()
    print("Uploading data...")
    process_csv()
    print("Done!")
