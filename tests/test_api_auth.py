"""
API tests for auth router.
"""
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


class TestAuthConfig:
    """Tests for GET /api/auth/config"""
    
    async def test_get_auth_config(self, client: AsyncClient):
        """Test getting auth configuration."""
        response = await client.get("/api/auth/config")
        assert response.status_code == 200
        
        data = response.json()
        assert "supabase_enabled" in data
        assert isinstance(data["supabase_enabled"], bool)
    
    async def test_get_auth_config_local_mode(self, client: AsyncClient):
        """Test auth config in local mode (no Supabase)."""
        with patch("api.routers.auth_router.USE_SUPABASE", False):
            response = await client.get("/api/auth/config")
            assert response.status_code == 200
            
            data = response.json()
            assert data["supabase_enabled"] == False


class TestSignUp:
    """Tests for POST /api/auth/signup"""
    
    async def test_signup_local_mode(self, client: AsyncClient):
        """Test signup in local mode (should fail)."""
        with patch("api.routers.auth_router.USE_SUPABASE", False):
            response = await client.post(
                "/api/auth/signup",
                json={"email": "test@example.com", "password": "password123"}
            )
            # In local mode, signup should fail or be disabled
            assert response.status_code in [400, 501]
    
    async def test_signup_missing_email(self, client: AsyncClient):
        """Test signup without email."""
        response = await client.post(
            "/api/auth/signup",
            json={"password": "password123"}
        )
        assert response.status_code == 422  # Validation error
    
    async def test_signup_missing_password(self, client: AsyncClient):
        """Test signup without password."""
        response = await client.post(
            "/api/auth/signup",
            json={"email": "test@example.com"}
        )
        assert response.status_code == 422  # Validation error
    
    async def test_signup_invalid_email(self, client: AsyncClient):
        """Test signup with invalid email format."""
        response = await client.post(
            "/api/auth/signup",
            json={"email": "invalid-email", "password": "password123"}
        )
        # Should fail validation or during signup
        assert response.status_code in [400, 422]


class TestSignIn:
    """Tests for POST /api/auth/signin"""
    
    async def test_signin_local_mode(self, client: AsyncClient):
        """Test signin in local mode (should fail)."""
        with patch("api.routers.auth_router.USE_SUPABASE", False):
            response = await client.post(
                "/api/auth/signin",
                json={"email": "test@example.com", "password": "password123"}
            )
            # In local mode, signin should fail or be disabled
            assert response.status_code in [400, 501]
    
    async def test_signin_missing_credentials(self, client: AsyncClient):
        """Test signin without credentials."""
        response = await client.post("/api/auth/signin", json={})
        assert response.status_code == 422  # Validation error


class TestSignOut:
    """Tests for POST /api/auth/signout"""
    
    async def test_signout_no_auth(self, client: AsyncClient):
        """Test signout without authentication."""
        response = await client.post("/api/auth/signout")
        # Should handle gracefully even without auth
        assert response.status_code in [200, 401]
    
    async def test_signout_with_auth(self, client: AsyncClient, auth_headers):
        """Test signout with authentication."""
        # In local mode, auth headers might not be validated
        response = await client.post("/api/auth/signout", headers=auth_headers)
        assert response.status_code in [200, 401]


class TestRefreshToken:
    """Tests for POST /api/auth/refresh"""
    
    async def test_refresh_local_mode(self, client: AsyncClient):
        """Test token refresh in local mode."""
        with patch("api.routers.auth_router.USE_SUPABASE", False):
            response = await client.post(
                "/api/auth/refresh",
                json={"refresh_token": "test-refresh-token"}
            )
            # In local mode, refresh should fail or be disabled
            assert response.status_code in [400, 401, 501]
    
    async def test_refresh_missing_token(self, client: AsyncClient):
        """Test refresh without token."""
        response = await client.post("/api/auth/refresh", json={})
        # Should fail without refresh token
        assert response.status_code in [400, 422]


class TestCurrentUser:
    """Tests for GET /api/auth/me"""
    
    async def test_get_current_user_no_auth(self, client: AsyncClient):
        """Test getting current user without authentication."""
        response = await client.get("/api/auth/me")
        assert response.status_code == 200
        
        data = response.json()
        # In local mode, should return local user or unauthenticated state
        assert "authenticated" in data or "id" in data
    
    async def test_get_current_user_local_mode(self, client: AsyncClient):
        """Test current user in local mode."""
        with patch("api.routers.auth_router.USE_SUPABASE", False):
            response = await client.get("/api/auth/me")
            assert response.status_code == 200
            
            data = response.json()
            # Local mode should return a local user
            assert data.get("id") == "local" or data.get("authenticated") == False
    
    async def test_get_current_user_with_auth(self, client: AsyncClient, auth_headers):
        """Test getting current user with authentication."""
        response = await client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200


class TestAuthFlow:
    """Integration tests for complete auth flows."""
    
    async def test_auth_disabled_flow(self, client: AsyncClient):
        """Test that API works when auth is disabled."""
        with patch("api.routers.auth_router.USE_SUPABASE", False):
            # Should be able to access protected endpoints
            response = await client.get("/api/podcasts")
            assert response.status_code == 200
            
            response = await client.get("/api/summaries")
            assert response.status_code == 200
