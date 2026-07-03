"""
backend/demo1/routers/webauthn_router.py
========================================
Handles Passwordless WebAuthn (YubiKey) Authentication.
Prevents Keystroke Injection / BadUSB attacks.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from fido2.server import Fido2Server
from fido2.webauthn import PublicKeyCredentialRpEntity, UserVerificationRequirement
from backend.demo1.pg import get_conn
import json
import base64
import os

router = APIRouter(prefix="/api/webauthn", tags=["webauthn"])

# Configure the Relying Party (Your App)
# Replace 'localhost' with your actual domain (e.g., 'paraiq.yourdomain.com') in production
rp_id = os.getenv("WEBAUTHN_RP_ID", "localhost")
rp = PublicKeyCredentialRpEntity(name="ParaIQ", id=rp_id)
server = Fido2Server(rp)

# In-memory state (For production, store these in Redis or Postgres temporarily)
pending_registrations = {}
pending_logins = {}

class WebAuthnLoginRequest(BaseModel):
    credential_id: str
    authenticator_data: str
    client_data_json: str
    signature: str

@router.get("/register/begin/{username}")
def begin_registration(username: str, request: Request):
    """Step 1: Client asks to register a security key."""
    user_id = username.encode('utf-8')
    
    # Fetch existing credentials from DB to prevent re-registration
    with get_conn("default") as conn:
        rows = conn.execute(
            "SELECT credential_id FROM user_security_keys WHERE username = %s",
            (username,)
        ).fetchall()
    
    existing_credentials = [bytes.fromhex(row["credential_id"]) for row in rows] if rows else []

    options, state = server.register_begin(
        {
            "id": user_id,
            "name": username,
            "displayName": username,
        },
        user_verification=UserVerificationRequirement.REQUIRED,
        existing_credentials=existing_credentials
    )
    
    pending_registrations[username] = state
    
    return json.loads(options.to_json())

@router.post("/register/complete/{username}")
def complete_registration(username: str, response: WebAuthnLoginRequest, request: Request):
    """Step 2: Client sends the YubiKey signature. We verify and save it."""
    if username not in pending_registrations:
        raise HTTPException(400, "Registration session expired")
        
    state = pending_registrations[username]
    
    try:
        # Verify the cryptographic signature (Decoding Base64 from Vue browser)
        auth_credential = server.register_complete(
            state,
            base64.b64decode(response.client_data_json),
            base64.b64decode(response.authenticator_data),
            base64.b64decode(response.signature),
        )
    except Exception as e:
        raise HTTPException(400, f"Key verification failed: {str(e)}")

    # Save the credential ID and public key to the database
    cred_id = auth_credential.credential_id.hex()
    pub_key = auth_credential.credential_public_key.hex()
    
    # Get firm_id from current session context for RLS
    try:
        firm_id = request.state.current_firm_id
    except AttributeError:
        firm_id = None

    with get_conn("default") as conn:
        conn.execute(
            "INSERT INTO user_security_keys (firm_id, username, credential_id, public_key) VALUES (%s, %s, %s, %s)",
            (firm_id, username, cred_id, pub_key)
        )
        
    del pending_registrations[username]
    return {"status": "success", "message": "Security key registered successfully."}

@router.get("/login/begin/{username}")
def begin_login(username: str, request: Request):
    """Step 1: Client asks to login with security key."""
    with get_conn("default") as conn:
        rows = conn.execute(
            "SELECT credential_id, public_key FROM user_security_keys WHERE username = %s",
            (username,)
        ).fetchall()
        
    if not rows:
        raise HTTPException(404, "No security key registered for this user")
        
    credentials = [
        {
            "id": bytes.fromhex(row["credential_id"]),
            "public_key": bytes.fromhex(row["public_key"]),
            "type": "public-key",
        }
        for row in rows
    ]

    options, state = server.authenticate_begin(
        credentials=credentials,
        user_verification=UserVerificationRequirement.REQUIRED
    )
    
    pending_logins[username] = state
    return json.loads(options.to_json())

@router.post("/login/complete/{username}")
def complete_login(username: str, response: WebAuthnLoginRequest, request: Request):
    """Step 2: Client signs the challenge. We verify it and issue JWT."""
    if username not in pending_logins:
        raise HTTPException(400, "Login session expired")
        
    state = pending_logins[username]
    
    with get_conn("default") as conn:
        rows = conn.execute(
            "SELECT credential_id, public_key FROM user_security_keys WHERE username = %s",
            (username,)
        ).fetchall()
        
    credentials = [
        {
            "id": bytes.fromhex(row["credential_id"]),
            "public_key": bytes.fromhex(row["public_key"]),
        }
        for row in rows
    ]

    try:
        # Verify the YubiKey touch (Decoding Base64 from Vue browser)
        server.authenticate_complete(
            state,
            credentials,
            base64.b64decode(response.credential_id),
            base64.b64decode(response.client_data_json),
            base64.b64decode(response.authenticator_data),
            base64.b64decode(response.signature),
        )
    except Exception as e:
        raise HTTPException(401, "YubiKey verification failed. Possible tampering detected.")

    del pending_logins[username]
    
    # In a real app, you would generate and return your JWT token here
    # from backend.demo1.auth import create_jwt_token
    # token = create_jwt_token(username)
    # return {"access_token": token}
    
    return {"status": "success", "message": "YubiKey verified. Login successful."}
