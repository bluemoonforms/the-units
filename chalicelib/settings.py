import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_STRING = "mysql+mysqldb://{user}:{password}@{host}/{database}"
DEBUG = True
