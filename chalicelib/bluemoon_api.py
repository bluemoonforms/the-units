import datetime
import requests
import os

from chalicelib.models import User
from chalicelib.database import DatabaseConnection


class BluemoonApi(object):
    def __init__(self, token):
        self.token = token
        self.url = os.getenv("API_URL")
        self.headers = {
            "Accept": "application/json",
            "Authorization": "Bearer {}".format(token),
        }

    def generate_url(self, path):
        return "{}/api/{}".format(self.url, path)

    def post_json(self, path, data):
        response = requests.post(
            self.generate_url(path), headers=self.headers, json=data
        )
        data = response.json()
        return data

    def get_json(self, path, params=None):
        url = self.generate_url(path)
        response = requests.get(url, headers=self.headers, params=params)
        data = response.json()
        return data

    def post_raw(self, path, data):
        response = requests.post(
            self.generate_url(path), headers=self.headers, json=data
        )
        return response

    def user_details(self):
        path = "user"
        return self.get_json(path=path)

    def execute_lease(self, bm_id, data):
        path = "lease/execute/{}".format(bm_id)
        return self.post_json(path=path, data=data)

    def esignature_details(self, bm_id):
        path = "esignature/lease/{}".format(bm_id)
        return self.get_json(path=path)

    def request_esignature(self, data):
        path = "esignature/lease"
        data["data"]["owner"] = {
            "name": "Test Name",
            "email": "test@name.com",
            "phone": "15129005000",
        }
        return self.post_json(path=path, data=data)

    def lease_forms(self):
        property_number = self.property_number()
        params = {"section": "lease"}
        path = "forms/list/{}".format(property_number)
        data = self.get_json(path=path, params=params)
        return data.get("lease", [])

    def property_number(self):
        path = "property"
        data = self.get_json(path=path)

        # Try to get the aptdb property number
        for prop in data["data"]:
            if prop["unit_type"] == "aptdb":
                return prop["id"]
        # No apt db then just return the first one
        return data["data"][0]["id"]

    def logout(self):
        path = "logout"
        return self.post_json(path=path)


class BluemoonAuthorization(object):
    def __init__(self, db=None):
        self.url = "{}{}".format(os.getenv("API_URL"), "/oauth/token")
        self.client_id = os.getenv("OAUTH_CLIENT_ID")
        self.client_secret = os.getenv("OAUTH_CLIENT_SECRET")
        if db is None:
            db = DatabaseConnection()
        self.db = db
        self.user = None

    def user_by_id(self, user_id):
        session = self.db.session()
        query = session.query(User)
        user = query.filter(User.id == user_id).first()
        return user

    def user_by_token(self, token):
        session = self.db.session()
        query = session.query(User)
        user = query.filter(User.access_token == token).first()
        return user

    def manage_user(self, data, username):
        session = self.db.session()
        query = session.query(User)
        user = query.filter(User.username == username).first()
        now = datetime.datetime.now()
        expires = now + datetime.timedelta(seconds=data["expires_in"])
        if not user:
            user = User(
                username=username,
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires=expires,
            )
            session.add(user)
        else:
            user.access_token = data["access_token"]
            user.refresh_token = data["refresh_token"]
            user.expires = expires
        session.commit()
        self.user = user

    def authenticate(self, username, password):
        payload = {
            "username": username,
            "password": password,
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = requests.post(
            self.url, headers={"Accept": "application/json"}, json=payload
        )
        data = response.json()
        if response.status_code == 200 and "access_token" in data:
            self.manage_user(data=data, username=username)
            return {"success": True}

        return data

    def check_authorization(self, token):
        user = self.user_by_token(token=token)
        if not user:
            return False
        now = datetime.datetime.now()
        if now < user.expires:
            return user
        return False

    def logout(self, token):
        bm_api = BluemoonApi(token)
        results = bm_api.logout()
        if results["success"]:
            user = self.user_by_token(token)
            data = {"access_token": "", "refresh_token": "", "expires_in": 0}
            self.manage_user(data=data, username=user.username)
            return True
