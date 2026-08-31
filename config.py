import os

class Config:
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "")

    # MongoDB Connection URL
    MONGO_URL = os.environ.get("MONGO_URL", "")

    DOWNLOAD_LOCATION = "./downloads"
  
