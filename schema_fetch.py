import os
from appwrite.client import Client
from appwrite.services.tables_db import TablesDB
from dotenv import load_dotenv

load_dotenv()

client = Client()
client.set_endpoint(os.getenv('APPWRITE_ENDPOINT'))
client.set_project(os.getenv('APPWRITE_PROJECT_ID'))
client.set_key(os.getenv('APPWRITE_API_KEY'))

tables_db = TablesDB(client)
db_id = os.getenv('APPWRITE_DATABASE_ID')
col_id = os.getenv('APPWRITE_PROFILE_COLLECTION_ID')

try:
    table = tables_db.get_table(db_id, col_id)
    print("ATTRIBUTES:")
    for attr in table.columns:
        print(f"- {attr.key} ({attr.type})")
except Exception as e:
    print("ERROR:", e)
