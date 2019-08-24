import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chalicelib.settings import DB_STRING


class DatabaseConnection:
    def __init__(self):
        self.connection_string = DB_STRING.format(
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            host=os.getenv("MYSQL_HOST", "db"),
            database=os.getenv("MYSQL_DATABASE"),
        )
        self.engine_obj = None
        self.session_obj = None

    def engine(self, new=False):
        if new is False and self.engine_obj is None:
            self.engine_obj = create_engine(self.connection_string)
        return self.engine_obj

    def session(self, new=False):
        if new is False and self.session_obj is None:
            engine = self.engine(new)
            self.session_obj = sessionmaker(bind=engine)
        return self.session_obj()
