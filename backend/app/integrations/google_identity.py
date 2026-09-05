"""Google OAuth SDK transport; identity owns admission and payload decisions."""
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


def verify_oauth2_token(credential: str, client_id: str) -> object:
    return id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
