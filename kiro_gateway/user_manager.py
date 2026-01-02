# -*- coding: utf-8 -*-

"""
KiroGate 用户管理模块。

处理用户会话、OAuth2 认证和用户相关操作。
"""

import base64
import binascii
import hashlib
import hmac
import os
import secrets
from typing import Optional, Tuple

import httpx
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from loguru import logger

from kiro_gateway.config import (
    settings,
    OAUTH_AUTHORIZATION_URL,
    OAUTH_TOKEN_URL,
    OAUTH_USER_URL,
    GITHUB_AUTHORIZATION_URL,
    GITHUB_TOKEN_URL,
    GITHUB_USER_URL,
)
from kiro_gateway.database import user_db, User


class UserSessionManager:
    """用户会话管理器。"""

    def __init__(self):
        self._serializer = URLSafeTimedSerializer(settings.user_session_secret)
        self._oauth_states: dict[str, int] = {}  # state -> timestamp

    def create_session(self, user_id: int, session_version: int = 1) -> str:
        """
        Create a signed session token for user.

        Args:
            user_id: User ID
            session_version: Current session version from database

        Returns:
            Signed session token containing user_id and session_version
        """
        return self._serializer.dumps({
            "user_id": user_id,
            "session_version": session_version
        })

    def verify_session(self, token: str) -> Optional[int]:
        """
        Verify session token and return user_id if valid.

        Checks both token signature/expiry AND session_version against database.

        Returns:
            user_id if valid, None otherwise
        """
        if not token:
            return None
        try:
            data = self._serializer.loads(token, max_age=settings.user_session_max_age)
            user_id = data.get("user_id")
            token_version = data.get("session_version", 1)

            if not user_id:
                return None

            # Verify session version against database
            current_version = user_db.get_session_version(user_id)
            if token_version != current_version:
                logger.debug(f"Session version mismatch for user {user_id}: token={token_version}, db={current_version}")
                return None

            return user_id
        except (BadSignature, SignatureExpired):
            return None

    def create_oauth_state(self) -> str:
        """Create a random state for OAuth2 CSRF protection."""
        import time
        state = secrets.token_urlsafe(32)
        self._oauth_states[state] = int(time.time())
        # Clean old states (> 10 minutes)
        cutoff = int(time.time()) - 600
        self._oauth_states = {k: v for k, v in self._oauth_states.items() if v > cutoff}
        return state

    def verify_oauth_state(self, state: str) -> bool:
        """Verify OAuth2 state parameter."""
        if state in self._oauth_states:
            del self._oauth_states[state]
            return True
        return False


class OAuth2Client:
    """LinuxDo OAuth2 客户端。"""

    def __init__(self):
        self.client_id = settings.oauth_client_id
        self.client_secret = settings.oauth_client_secret
        self.redirect_uri = settings.oauth_redirect_uri

    @property
    def is_configured(self) -> bool:
        """Check if OAuth2 is properly configured."""
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, state: str) -> str:
        """Get OAuth2 authorization URL."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{OAUTH_AUTHORIZATION_URL}?{query}"

    async def exchange_code(self, code: str) -> Optional[dict]:
        """
        Exchange authorization code for access token.

        Returns:
            Token response dict or None on failure
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    OAUTH_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self.redirect_uri,
                    },
                    auth=(self.client_id, self.client_secret),
                    headers={"Accept": "application/json"},
                    timeout=30.0,
                )
                if response.status_code == 200:
                    return response.json()
                logger.error(f"OAuth2 token exchange failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"OAuth2 token exchange error: {e}")
        return None

    async def get_user_info(self, access_token: str) -> Optional[dict]:
        """
        Get user info from LinuxDo API.

        Returns:
            User info dict or None on failure
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    OAUTH_USER_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                    timeout=30.0,
                )
                if response.status_code == 200:
                    return response.json()
                logger.error(f"OAuth2 user info failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"OAuth2 user info error: {e}")
        return None


class GitHubOAuth2Client:
    """GitHub OAuth2 客户端。"""

    def __init__(self):
        self.client_id = settings.github_client_id
        self.client_secret = settings.github_client_secret
        self.redirect_uri = settings.github_redirect_uri

    @property
    def is_configured(self) -> bool:
        """Check if GitHub OAuth2 is properly configured."""
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, state: str) -> str:
        """Get GitHub OAuth2 authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{GITHUB_AUTHORIZATION_URL}?{query}"

    async def exchange_code(self, code: str) -> Optional[dict]:
        """
        Exchange authorization code for access token.

        Returns:
            Token response dict or None on failure
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    GITHUB_TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                        "redirect_uri": self.redirect_uri,
                    },
                    headers={"Accept": "application/json"},
                    timeout=30.0,
                )
                if response.status_code == 200:
                    return response.json()
                logger.error(f"GitHub OAuth2 token exchange failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"GitHub OAuth2 token exchange error: {e}")
        return None

    async def get_user_info(self, access_token: str) -> Optional[dict]:
        """
        Get user info from GitHub API.

        Returns:
            User info dict or None on failure
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    GITHUB_USER_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "KiroGate",
                    },
                    timeout=30.0,
                )
                if response.status_code == 200:
                    return response.json()
                logger.error(f"GitHub user info failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"GitHub user info error: {e}")
        return None


class UserManager:
    """用户管理器，整合会话、OAuth2 和数据库操作。"""

    def __init__(self):
        self.session = UserSessionManager()
        self.oauth = OAuth2Client()
        self.github = GitHubOAuth2Client()

    def _hash_password(self, password: str) -> str:
        """Hash password with PBKDF2."""
        salt = os.urandom(16)
        iterations = 120000
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
        hash_b64 = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return f"pbkdf2_sha256${iterations}${salt_b64}${hash_b64}"

    def _verify_password(self, password: str, stored: str) -> bool:
        """Verify password hash."""
        try:
            algo, iterations_str, salt_b64, hash_b64 = stored.split("$", 3)
            if algo != "pbkdf2_sha256":
                return False
            iterations = int(iterations_str)
            salt = base64.urlsafe_b64decode(salt_b64 + "==")
            expected = base64.urlsafe_b64decode(hash_b64 + "==")
        except (ValueError, binascii.Error):
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(digest, expected)

    async def oauth_login(self, code: str) -> Tuple[Optional[User], Optional[str]]:
        """
        Complete OAuth2 login flow.

        Args:
            code: Authorization code from OAuth2 callback

        Returns:
            (User, session_token) on success, (None, error_message) on failure
        """
        # Exchange code for token
        token_data = await self.oauth.exchange_code(code)
        if not token_data:
            return None, "授权码交换失败"

        access_token = token_data.get("access_token")
        if not access_token:
            return None, "响应中缺少访问令牌"

        # Get user info
        user_info = await self.oauth.get_user_info(access_token)
        if not user_info:
            return None, "获取用户信息失败"

        # Extract user data
        linuxdo_id = str(user_info.get("id", ""))
        username = user_info.get("username", "") or user_info.get("name", "")
        avatar_url = user_info.get("avatar_url") or user_info.get("avatar_template", "")
        trust_level = user_info.get("trust_level", 0)

        if not linuxdo_id:
            return None, "用户信息无效：缺少 ID"

        # Check if user exists
        user = user_db.get_user_by_linuxdo(linuxdo_id)
        if user:
            # Update last login
            user_db.update_last_login(user.id)
            # Check if banned
            if user.is_banned:
                return None, "用户已被封禁"
            if user.approval_status != "approved":
                return None, "账号审核中" if user.approval_status == "pending" else "账号已被拒绝"
        else:
            from kiro_gateway.metrics import metrics
            if metrics.is_self_use_enabled():
                return None, "自用模式下暂不开放注册"
            # Create new user
            user = user_db.create_user(
                linuxdo_id=linuxdo_id,
                username=username,
                avatar_url=avatar_url,
                trust_level=trust_level,
                approval_status="approved"
            )
            logger.info(f"New user registered: {username} (LinuxDo ID: {linuxdo_id})")

        # Create session
        session_token = self.session.create_session(user.id, user.session_version)
        return user, session_token

    async def github_login(self, code: str) -> Tuple[Optional[User], Optional[str]]:
        """
        Complete GitHub OAuth2 login flow.

        Args:
            code: Authorization code from GitHub OAuth2 callback

        Returns:
            (User, session_token) on success, (None, error_message) on failure
        """
        # Exchange code for token
        token_data = await self.github.exchange_code(code)
        if not token_data:
            return None, "授权码交换失败"

        access_token = token_data.get("access_token")
        if not access_token:
            return None, "响应中缺少访问令牌"

        # Get user info
        user_info = await self.github.get_user_info(access_token)
        if not user_info:
            return None, "获取用户信息失败"

        # Extract user data
        github_id = str(user_info.get("id", ""))
        username = user_info.get("login", "") or user_info.get("name", "")
        avatar_url = user_info.get("avatar_url", "")

        if not github_id:
            return None, "用户信息无效：缺少 ID"

        # Check if user exists by GitHub ID
        user = user_db.get_user_by_github(github_id)
        if user:
            # Update last login
            user_db.update_last_login(user.id)
            # Check if banned
            if user.is_banned:
                return None, "用户已被封禁"
            if user.approval_status != "approved":
                return None, "账号审核中" if user.approval_status == "pending" else "账号已被拒绝"
        else:
            from kiro_gateway.metrics import metrics
            if metrics.is_self_use_enabled():
                return None, "自用模式下暂不开放注册"
            # Create new user with GitHub ID
            user = user_db.create_user(
                github_id=github_id,
                username=username,
                avatar_url=avatar_url,
                trust_level=0,
                approval_status="approved"
            )
            logger.info(f"New user registered via GitHub: {username} (GitHub ID: {github_id})")

        # Create session
        session_token = self.session.create_session(user.id, user.session_version)
        return user, session_token

    def get_current_user(self, session_token: str) -> Optional[User]:
        """Get current user from session token."""
        user_id = self.session.verify_session(session_token)
        if not user_id:
            return None
        user = user_db.get_user(user_id)
        if user and (user.is_banned or user.approval_status != "approved"):
            return None
        return user

    def register_with_email(
        self,
        email: str,
        password: str,
        username: Optional[str] = None
    ) -> Tuple[Optional[User], Optional[str]]:
        """Register a new user with email/password."""
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            return None, "邮箱格式不正确"
        if not password or len(password) < 8:
            return None, "密码至少 8 位"
        from kiro_gateway.metrics import metrics
        if metrics.is_self_use_enabled():
            return None, "自用模式下暂不开放注册"
        existing = user_db.get_user_by_email(email)
        if existing:
            return None, "邮箱已注册"
        display_name = (username or "").strip() or email.split("@", 1)[0]
        approval_status = "pending" if metrics.is_require_approval() else "approved"
        password_hash = self._hash_password(password)
        user = user_db.create_user(
            username=display_name,
            email=email,
            password_hash=password_hash,
            approval_status=approval_status
        )
        if approval_status != "approved":
            return None, "注册成功，等待审核"
        session_token = self.session.create_session(user.id, user.session_version)
        return user, session_token

    def login_with_email(self, email: str, password: str) -> Tuple[Optional[User], Optional[str]]:
        """Login with email/password."""
        email = (email or "").strip().lower()
        if not email or not password:
            return None, "邮箱或密码不能为空"
        user = user_db.get_user_by_email(email)
        if not user or not user.password_hash:
            return None, "邮箱或密码错误"
        if not self._verify_password(password, user.password_hash):
            return None, "邮箱或密码错误"
        if user.is_banned:
            return None, "用户已被封禁"
        if user.approval_status != "approved":
            return None, "账号审核中" if user.approval_status == "pending" else "账号已被拒绝"
        user_db.update_last_login(user.id)
        session_token = self.session.create_session(user.id, user.session_version)
        return user, session_token

    def logout(self, user_id: int) -> bool:
        """
        Logout user by incrementing session version.

        This invalidates all existing session tokens for the user.

        Args:
            user_id: User ID to logout

        Returns:
            True on success
        """
        user_db.increment_session_version(user_id)
        logger.info(f"User {user_id} logged out, session version incremented")
        return True


# Global user manager instance
user_manager = UserManager()
