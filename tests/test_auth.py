"""
Tests for authentication: registration, login, JWT validation, and protected routes.
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from auth import hash_password, verify_password, create_token, decode_token, validate_registration


# ── Password hashing tests ───────────────────────────────────────────

class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_returns_hash_and_salt(self):
        pw_hash, salt = hash_password('mypassword')
        assert isinstance(pw_hash, str)
        assert isinstance(salt, str)
        assert len(pw_hash) == 64  # SHA-256 hex
        assert len(salt) == 32     # 16 bytes hex

    def test_verify_correct_password(self):
        pw_hash, salt = hash_password('correct_password')
        assert verify_password('correct_password', pw_hash, salt) is True

    def test_verify_wrong_password(self):
        pw_hash, salt = hash_password('correct_password')
        assert verify_password('wrong_password', pw_hash, salt) is False

    def test_different_passwords_different_hashes(self):
        h1, s1 = hash_password('password1')
        h2, s2 = hash_password('password2')
        assert h1 != h2


# ── JWT token tests ──────────────────────────────────────────────────

class TestJWT:
    """Tests for JWT creation and decoding."""

    def test_create_and_decode_token(self):
        token = create_token(42, 'user@example.com')
        payload = decode_token(token)
        assert payload is not None
        assert payload['user_id'] == 42
        assert payload['email'] == 'user@example.com'

    def test_decode_invalid_token_returns_none(self):
        assert decode_token('not.a.valid.token') is None

    def test_decode_tampered_token_returns_none(self):
        token = create_token(1, 'a@b.com')
        tampered = token[:-5] + 'XXXXX'
        assert decode_token(tampered) is None


# ── Registration validation tests ────────────────────────────────────

class TestValidateRegistration:
    """Tests for input validation on registration data."""

    def test_valid_registration(self):
        ok, err = validate_registration({
            'email': 'user@example.com',
            'password': 'longpassword',
            'name': 'Alice',
        })
        assert ok is True
        assert err == ''

    def test_missing_email(self):
        ok, err = validate_registration({'email': '', 'password': '12345678', 'name': 'Bob'})
        assert ok is False
        assert 'email' in err.lower()

    def test_short_password(self):
        ok, err = validate_registration({'email': 'a@b.com', 'password': '123', 'name': 'Bob'})
        assert ok is False
        assert 'password' in err.lower()

    def test_short_name(self):
        ok, err = validate_registration({'email': 'a@b.com', 'password': '12345678', 'name': 'A'})
        assert ok is False
        assert 'name' in err.lower()


# ── Route-level auth tests ───────────────────────────────────────────

class TestAuthRoutes:
    """Integration tests for /api/auth/* endpoints."""

    def test_register_success(self, client):
        resp = client.post('/api/auth/register', json={
            'email': 'new@example.com',
            'name': 'New User',
            'password': 'securepassword123',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'token' in data
        assert data['user']['email'] == 'new@example.com'

    def test_register_duplicate_email(self, client):
        payload = {'email': 'dup@example.com', 'name': 'Dup', 'password': 'securepassword123'}
        client.post('/api/auth/register', json=payload)
        resp = client.post('/api/auth/register', json=payload)
        assert resp.status_code == 409

    def test_login_success(self, client):
        client.post('/api/auth/register', json={
            'email': 'login@example.com', 'name': 'Login', 'password': 'password1234',
        })
        resp = client.post('/api/auth/login', json={
            'email': 'login@example.com', 'password': 'password1234',
        })
        assert resp.status_code == 200
        assert 'token' in resp.get_json()

    def test_login_wrong_password(self, client):
        client.post('/api/auth/register', json={
            'email': 'wrong@example.com', 'name': 'Wrong', 'password': 'password1234',
        })
        resp = client.post('/api/auth/login', json={
            'email': 'wrong@example.com', 'password': 'badpassword',
        })
        assert resp.status_code == 401

    def test_protected_route_without_token(self, client):
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401

    def test_protected_route_with_valid_token(self, client, auth_header):
        resp = client.get('/api/auth/me', headers=auth_header)
        assert resp.status_code == 200
        assert resp.get_json()['email'] == 'test@example.com'
