import os
import base64
import hashlib
from cryptography.fernet import Fernet

def vault():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(os.environ['APP_SECRET'].encode()).digest()))

def seal(value):return vault().encrypt(value.encode()).decode()
def unseal(value):return vault().decrypt(value.encode()).decode()