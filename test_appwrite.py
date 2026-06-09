import os
from appwrite.client import Client
from appwrite.services.databases import Databases
from dotenv import load_dotenv

load_dotenv()
client = Client()
client.set_endpoint(os.getenv('APPWRITE_ENDPOINT'))
client.set_project(os.getenv('APPWRITE_PROJECT_ID'))
client.set_key(os.getenv('APPWRITE_API_KEY'))

db = Databases(client)
db_id = os.getenv('APPWRITE_DATABASE_ID')
col_id = 'messages'

try:
    db.create_string_attribute(db_id, col_id, 'sender_id', 255, True)
    db.create_string_attribute(db_id, col_id, 'receiver_id', 255, True)
    db.create_string_attribute(db_id, col_id, 'content', 10000, True)
    db.create_datetime_attribute(db_id, col_id, 'timestamp', True)
    print("Attributes created!")
except Exception as e:
    print(f"Error: {e}")
