# Copy these to config_local.py
DEBUG = True
# Get these at osm.org -> account -> oauth settings -> register
OAUTH_KEY = ''
OAUTH_SECRET = ''
# Change this for the production
SECRET_KEY = 'sakdfjhasldfhasldfsdfas21421432134'

BASE_URL = 'http://127.0.0.1/'

# The rest you can leave as is or override if needed

CREATED_BY = 'RevertUI 1.0'
MAX_CHANGESETS = 20
MAX_DIFFS = 200
MAX_HISTORY = 100

import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'revertui.db')

try:
    from .config_local import *
except ImportError:
    pass
