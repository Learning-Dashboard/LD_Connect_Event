from pymongo import MongoClient
from config.settings import MONGO_URI, MONGO_DB

# Create the global MongoClient instance.
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]


def get_collection(collection_name: str):
    """
    Returns a reference to a collection by name.
    E.g. get_collection("TeamA_commits") -> the 'TeamA_commits' collection
    """
    return db[collection_name]
