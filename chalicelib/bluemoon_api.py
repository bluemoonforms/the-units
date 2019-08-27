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
        """Shortcut."""
        response = self.post_raw(path=path, data=data)
        return response.json()

    def get_json(self, path, params=None):
        """Shortcut."""
        response = self.get_raw(path=path, params=params)
        return response.json()

    def post_raw(self, path, data):
        """Used directly for PDFs, via shortcuts for JSON"""
        headers = self.headers
        headers["Content-Type"] = "application/json"
        response = requests.post(
            self.generate_url(path), headers=self.headers, json=data
        )
        return response

    def get_raw(self, path, params=None):
        """Used directly for PDFs, via shortcuts for JSON"""
        response = requests.get(
            self.generate_url(path), headers=self.headers, params=params
        )
        return response

    def user_details(self):
        """Currently logged in Bluemoon user."""
        path = "user"
        return self.get_json(path=path)

    def execute_lease(self, bm_id, data):
        """Execute lease for the provided Bluemoon Lease Esignature ID."""
        path = "esignature/lease/execute/{}".format(bm_id)
        return self.post_json(path=path, data=data)

    def esignature_details(self, bm_id):
        """Fetch details for the provided Bluemoon Lease Esignature ID."""
        path = "esignature/lease/{}".format(bm_id)
        return self.get_json(path=path)

    def request_esignature(self, data):
        """Create a lease esignature and request an esignature for each resident given a lease id."""
        path = "esignature/lease"
        return self.post_json(path=path, data=data)

    def lease_forms(self):
        """Fetch all the lease forms for the selected property."""
        property_number = self.property_number()
        # Filtering by the section, lease as that is all that you can currently
        # access via the Bluemoon Rest API.
        params = {"section": "lease"}
        path = "forms/list/{}".format(property_number)
        data = self.get_json(path=path, params=params)
        return data.get("lease", [])

    def property_number(self):
        """Fetch a property number associated with an account."""
        path = "property"
        data = self.get_json(path=path)
        # Accounts can have multiple properties so you need to know
        # the actual property id, this is just for demonstration purposes
        # Try to get the aptdb property number
        for prop in data["data"]:
            if prop["unit_type"] == "aptdb":
                return prop["id"]
        # No apt db then just return the first one
        return data["data"][0]["id"]

    def logout(self):
        path = "logout"
        return self.post_json(path=path, data={})


class BluemoonAuthorization(object):
    def __init__(self):
        self.url = "{}{}".format(os.getenv("API_URL"), "/oauth/token")
        self.client_id = os.getenv("OAUTH_CLIENT_ID")
        self.client_secret = os.getenv("OAUTH_CLIENT_SECRET")
        self.db = DatabaseConnection()
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
        """Create oauthed user."""
        # I am basically creating my user based on the Bluemoon data
        # typically you would have your application user and a single bluemoon api user
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
        # It is important to always pass the accept and content-type json headers for a post
        response = requests.post(
            self.url,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=payload,
        )
        data = response.json()
        if response.status_code == 200 and "access_token" in data:
            self.manage_user(data=data, username=username)
            return {"success": True}

        return data

    def check_authorization(self, token):
        # Verifying the token has not expired.
        user = self.user_by_token(token=token)
        if not user:
            return False
        now = datetime.datetime.now()
        if now < user.expires:
            return user
        return False

    def logout(self, token):
        bm_api = BluemoonApi(token)
        # Revoke the token in the API.
        results = bm_api.logout()
        if results["success"]:
            user = self.user_by_token(token)
            # This basicall revokes the token locally
            data = {"access_token": "", "refresh_token": "", "expires_in": 0}
            self.manage_user(data=data, username=user.username)
            return True
