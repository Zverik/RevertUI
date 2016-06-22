DEBUG = True

CREATED_BY = 'RevertUI 1.0'

# Get these at osm.org -> account -> oauth settings -> register
OAUTH_KEY = ''
OAUTH_SECRET = ''

MAX_CHANGESETS = 20
MAX_DIFFS = 200

import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'revertui.db')

# Change this for the production
SECRET_KEY = 'sakdfjhasldfhasldfsdfas21421432134'
