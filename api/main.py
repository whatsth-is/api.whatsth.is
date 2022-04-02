import urllib3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import router
from api.cache import Cache
from api.config import Config

def_url  = 'https://gist.githubusercontent.com/soup-bowl/ca302eb775278a581cd4e7e2ea4122a1/raw/definitions.yml'
def_file = urllib3.PoolManager().request('GET', def_url)

config = Config()
cache  = Cache()

if def_file.status == 200:
    print("Loaded latest definition file from GitHub.")
    config.load_yml( def_file.data.decode('utf-8') )
else:
    print("Unable to download definitions file.")
    exit(1)

app = FastAPI(
    title="What's This? API",
    description="Inspection application that detects web technologies and informs the user of them.",
    contact={
        "name": "Soupbowl",
        "email": "code@soupbowl.io",
        "url": "https://www.soupbowl.io",
    },
    license_info={
        "name": "MIT",
        "url": "https://github.com/soup-bowl/api.whatsth.is/blob/main/LICENSE",
    },
    version="0.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router.router)
