from peewee import *
from . import config
import datetime

database = SqliteDatabase(config.DATABASE_PATH)


class Task(Model):
    username = CharField(max_length=254, index=True)
    token = TextField()
    secret = TextField()
    changesets = TextField()
    comment = CharField(max_length=254)
    timestamp = DateTimeField(default=datetime.datetime.now)
    status = FixedCharField(max_length=10, default='queued')
    error = TextField(null=True)
    pending = BooleanField(default=True, index=True)

    class Meta:
        database = database

    def changeset_ids(self):
        return self.changesets.split()
