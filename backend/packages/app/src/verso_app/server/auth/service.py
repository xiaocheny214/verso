"""知乎登录、站内 session、调用 reputation 开户。不写画像。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from verso_app.server.auth.models import User
from verso_app.server.auth.session_store import SessionStore
from verso_app.server.reputation.service import ReputationService
from verso_common.enums import BizCode, UserStatus
from verso_common.exceptions import BizException
from verso_framework.config.app import AppSettings
from verso_framework.providers.zhihu import OAuthClient, ZhihuProfile

logger = logging.getLogger("verso.auth")


@dataclass(frozen=True, slots=True)
class LoginStart:
    authorize_url: str
    nonce: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    session_id: str


class AuthService:
    def __init__(
        self,
        session: Session,
        store: SessionStore,
        oauth: OAuthClient,
        reputation: ReputationService,
        settings: AppSettings,
    ) -> None:
        self._session = session
        self._store = store
        self._oauth = oauth
        self._reputation = reputation
        self._settings = settings

    def start_login(self) -> LoginStart:
        if not (
            self._settings.zhihu_client_id
            and self._settings.zhihu_client_secret
            and self._settings.zhihu_access_secret
            and self._settings.zhihu_redirect_uri
        ):
            raise BizException("未配置知乎登录", code=BizCode.INTERNAL_ERROR)
        nonce = self._store.put_intent(self._settings.oauth_intent_ttl_sec)
        return LoginStart(
            authorize_url=self._oauth.authorization_url(nonce),
            nonce=nonce,
        )

    def complete_login(self, *, code: str, nonce: str) -> LoginResult:
        if not code:
            raise BizException("缺少授权码", code=BizCode.BAD_REQUEST)
        if not nonce or not self._store.consume_intent(nonce):
            raise BizException("登录已过期，请重试", code=BizCode.BAD_REQUEST)
        try:
            token = self._oauth.exchange_code(code)
            profile = self._oauth.fetch_profile(token.access_token)
        except Exception:
            logger.exception("知乎换票或取名片失败")
            raise BizException("知乎授权失败", code=BizCode.BAD_REQUEST) from None
        user = self._upsert_user(profile)
        if user.status != UserStatus.ACTIVE:
            raise BizException("账号不可用", code=BizCode.FORBIDDEN)
        self._reputation.ensure_default(self._session, user.id)
        self._store.save_grant(str(user.id), token.access_token, token.expires_in)
        sid = self._store.issue_session(str(user.id), self._settings.session_ttl_sec)
        return LoginResult(user=user, session_id=sid)

    def logout(self, session_id: str) -> None:
        if session_id:
            self._store.drop_session(session_id)

    def require_user(self, session_id: str | None) -> User:
        if not session_id:
            raise BizException("未登录", code=BizCode.UNAUTHORIZED)
        raw_id = self._store.user_id_for(session_id)
        if not raw_id:
            raise BizException("未登录", code=BizCode.UNAUTHORIZED)
        user = self._session.get(User, uuid.UUID(raw_id))
        if user is None or user.status != UserStatus.ACTIVE:
            raise BizException("未登录", code=BizCode.UNAUTHORIZED)
        return user

    def _upsert_user(self, profile: ZhihuProfile) -> User:
        user = self._session.scalar(select(User).where(User.zhihu_url_token == profile.url_token))
        now = datetime.now(UTC)
        if user is None:
            user = User(
                zhihu_url_token=profile.url_token,
                zhihu_open_id=profile.open_id,
                display_name=profile.name,
                avatar_url=profile.avatar_url,
                headline=profile.headline,
                status=UserStatus.ACTIVE,
                last_login_at=now,
            )
            self._session.add(user)
            self._session.flush()
            return user
        user.display_name = profile.name
        user.avatar_url = profile.avatar_url
        user.headline = profile.headline
        if profile.open_id:
            user.zhihu_open_id = profile.open_id
        user.last_login_at = now
        self._session.flush()
        return user
