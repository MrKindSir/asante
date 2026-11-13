"""Local password authentication with server-owned roles and revocable cookies."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
from typing import Literal
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from .database import get_session
from .models import AccountRecord, AccountSession, ContributorRecord, LoginAttempt, WorkspaceSession

router = APIRouter(prefix="/v1/auth")
ACCOUNT_COOKIE = "asante_account"
WORKSPACE_COOKIE = "asante_workspace"
CSRF_COOKIE = "asante_csrf"
CSRF_HEADER = "x-asante-csrf"
HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def now() -> datetime:
    return datetime.now(timezone.utc)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(session_token: str) -> str:
    """Derive a browser-readable token that is bound to one opaque session."""
    return hmac.new(session_token.encode(), b"asante-csrf-v1", hashlib.sha256).hexdigest()


def _cookie(request: Request, name: str) -> str | None:
    value = request.cookies.get(name)
    return value if isinstance(value, str) and value else None


def _set_csrf_cookie(request: Request, response: Response, session_token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token(session_token),
        max_age=7 * 86400 if session_token == _cookie(request, ACCOUNT_COOKIE) else 90 * 86400,
        httponly=False,
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
        samesite="strict",
        # The portal and reviewer dashboard live outside the API prefix and
        # must be able to read this non-HttpOnly value to send the header.
        path="/asante",
    )


def mutation(request: Request) -> None:
    """Allow same-site browser mutations with a session-bound CSRF token."""
    if request.headers.get("x-asante-request") != "1":
        raise HTTPException(403, "Use the Asante application to make this request")
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip().lower()
        host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
        if not host:
            raise HTTPException(403, "Use the Asante application to make this request")
        if ":" in host:
            name, _, port = host.rpartition(":")
            if (proto == "https" and port == "443") or (proto == "http" and port == "80"):
                host = name
        expected = {f"{proto}://{host}"}
        # Edge HTTPS often terminates before the Asante proxy, which still sees http.
        if proto == "http":
            expected.add(f"https://{host}")
        if origin not in expected:
            raise HTTPException(403, "Use the Asante application to make this request")

    account_token = _cookie(request, ACCOUNT_COOKIE)
    workspace_token = _cookie(request, WORKSPACE_COOKIE)
    session_token = account_token or workspace_token
    if not session_token:
        return
    path = request.url.path if isinstance(request.url.path, str) else ""
    # Authentication and workspace-session calls bootstrap/recover the readable token.
    if path.endswith("/auth/login") or path.endswith("/auth/register") or path.endswith("/workspace/session"):
        return
    presented = request.headers.get(CSRF_HEADER)
    stored = _cookie(request, CSRF_COOKIE)
    expected_token = csrf_token(session_token)
    if not presented or not stored or not hmac.compare_digest(presented, expected_token) or not hmac.compare_digest(stored, expected_token):
        raise HTTPException(403, "A valid Asante CSRF token is required")


def public_account(account: AccountRecord) -> dict:
    return {"id": account.id, "email": account.email, "role": account.role, "profileId": account.contributor_id}


async def optional_account(request: Request, session: AsyncSession) -> AccountRecord | None:
    token = request.cookies.get(ACCOUNT_COOKIE)
    record = await session.get(AccountSession, token_hash(token)) if token else None
    if not record or record.expires_at <= now():
        return None
    return await session.get(AccountRecord, record.account_id)


async def require_account(request: Request, session: AsyncSession = Depends(get_session)) -> AccountRecord:
    account = await optional_account(request, session)
    if not account:
        raise HTTPException(401, "Sign in to your Asante account")
    return account


async def require_reviewer(account: AccountRecord = Depends(require_account)) -> AccountRecord:
    if account.role != "reviewer":
        raise HTTPException(403, "An Asante reviewer account is required")
    return account


async def require_contributor(account: AccountRecord = Depends(require_account)) -> AccountRecord:
    if account.role != "contributor":
        raise HTTPException(403, "An Asante contributor account is required")
    return account


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalized_email(cls, value: str) -> str:
        value = value.strip().lower()
        if value.count("@") != 1 or any(char.isspace() for char in value) or not all(value.split("@")):
            raise ValueError("Enter a valid email address")
        return value


class Registration(Credentials):
    name: str = Field(min_length=2, max_length=120)
    consent: Literal[True]
    import_device: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def attribution_name(cls, value):
        return value.strip() if isinstance(value, str) else value


DEMO_ACCOUNTS = (
    {"id": "demo", "name": "Asante demo narration", "email": "demo@asante.test", "role": "contributor"},
    {"id": "nomsa", "name": "Nomsa M.", "email": "nomsa@asante.test", "role": "contributor"},
    {"id": "thabo", "name": "Thabo K.", "email": "thabo@asante.test", "role": "contributor"},
    {"id": "amina", "name": "Amina S.", "email": "amina@asante.test", "role": "contributor"},
    {"id": "reviewer", "name": "Asante test reviewer", "email": "reviewer@asante.test", "role": "reviewer"},
)
DEMO_ACCOUNT_IDS = frozenset(item["id"] for item in DEMO_ACCOUNTS)


class DemoLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account: str = Field(min_length=1, max_length=32)


def demo_login_enabled() -> bool:
    """Keep passwordless profile switching restricted to the local development app."""
    return os.environ.get("ASANTE_ENV", "").strip().lower() == "development"


def require_demo_login() -> None:
    if not demo_login_enabled():
        raise HTTPException(404, "Demo account selection is unavailable")


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


async def issue_session(request: Request, response: Response, session: AsyncSession, account: AccountRecord) -> None:
    previous = request.cookies.get(ACCOUNT_COOKIE)
    if previous:
        await session.execute(delete(AccountSession).where(AccountSession.token_hash == token_hash(previous)))
    token = secrets.token_urlsafe(48)
    session.add(AccountSession(token_hash=token_hash(token), account_id=account.id, expires_at=now() + timedelta(days=7)))
    await session.commit()
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(ACCOUNT_COOKIE, token, max_age=7 * 86400, httponly=True, secure=secure, samesite="strict", path="/asante/api")
    _set_csrf_cookie(request, response, token)
    response.headers["Cache-Control"] = "no-store"


@router.post("/register", status_code=201, dependencies=[Depends(mutation)])
async def register(body: Registration, request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    if await optional_account(request, session):
        raise HTTPException(409, "Sign out before creating another account")
    if await session.scalar(select(AccountRecord.id).where(AccountRecord.email == body.email)):
        raise HTTPException(409, "Account could not be created. Sign in if you already have an account.")
    contributor = None
    if body.import_device:
        token = request.cookies.get("asante_workspace", "")
        device = await session.get(WorkspaceSession, token_hash(token)) if token else None
        if not device or device.expires_at <= now():
            raise HTTPException(409, "The device workspace is unavailable; create an account without importing it")
        contributor = await session.get(ContributorRecord, device.contributor_id, with_for_update=True)
        if await session.scalar(select(AccountRecord.id).where(AccountRecord.contributor_id == contributor.id)):
            raise HTTPException(409, "This workspace already belongs to an account; sign in instead")
        if contributor.profile and contributor.profile.get("name") != body.name:
            raise HTTPException(409, "Use the existing attribution name when linking this workspace")
    if contributor is None:
        contributor = ContributorRecord(id=uuid4().hex, profile={}, preferences={})
        session.add(contributor)
        await session.flush()
    contributor.profile = {**contributor.profile, "name": body.name.strip(), "email": body.email, "bio": contributor.profile.get("bio", ""), "language": contributor.profile.get("language", "en")}
    account = AccountRecord(id=uuid4().hex, contributor_id=contributor.id, email=body.email, password_hash=await run_in_threadpool(HASHER.hash, body.password), role="contributor")
    session.add(account)
    try:
        await session.flush()
        # Device capabilities must no longer access a newly account-owned workspace.
        await session.execute(delete(WorkspaceSession).where(WorkspaceSession.contributor_id == contributor.id))
        await issue_session(request, response, session, account)
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(409, "Account could not be created. Try signing in.") from error
    return public_account(account)


@router.post("/login", dependencies=[Depends(mutation)])
async def login(body: Credentials, request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    identity = token_hash(body.email)
    await session.execute(insert(LoginAttempt).values(identity_hash=identity, attempts=0, window_ends_at=now() + timedelta(minutes=15)).on_conflict_do_nothing())
    attempt = await session.get(LoginAttempt, identity, with_for_update=True, populate_existing=True)
    if attempt.window_ends_at <= now():
        attempt.attempts, attempt.window_ends_at = 0, now() + timedelta(minutes=15)
    if attempt.attempts >= 10:
        raise HTTPException(429, "Too many sign-in attempts. Try again after fifteen minutes.", headers={"Retry-After": "900"})
    account = await session.scalar(select(AccountRecord).where(AccountRecord.email == body.email))
    valid = await run_in_threadpool(verify_password, account.password_hash if account else DUMMY_HASH, body.password)
    if not account or not valid:
        attempt.attempts += 1
        await session.commit()
        raise HTTPException(401, "Email or password is incorrect")
    attempt.attempts = 0
    if HASHER.check_needs_rehash(account.password_hash):
        account.password_hash = await run_in_threadpool(HASHER.hash, body.password)
    await issue_session(request, response, session, account)
    return public_account(account)


@router.get("/demo-accounts", dependencies=[Depends(require_demo_login)])
async def demo_accounts() -> list[dict[str, str]]:
    return [dict(item) for item in DEMO_ACCOUNTS]


@router.post("/demo-login", dependencies=[Depends(mutation), Depends(require_demo_login)])
async def demo_login(body: DemoLogin, request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    if body.account not in DEMO_ACCOUNT_IDS:
        raise HTTPException(404, "Demo account not found")
    descriptor = next(item for item in DEMO_ACCOUNTS if item["id"] == body.account)
    account = await session.scalar(select(AccountRecord).where(AccountRecord.email == descriptor["email"]))
    if not account or account.role != descriptor["role"]:
        raise HTTPException(404, "Demo account is not provisioned")
    await issue_session(request, response, session, account)
    return public_account(account)


@router.get("/me")
async def me(account: AccountRecord = Depends(require_account)) -> dict:
    return public_account(account)


@router.post("/logout", dependencies=[Depends(mutation)])
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    token = request.cookies.get(ACCOUNT_COOKIE)
    if token:
        await session.execute(delete(AccountSession).where(AccountSession.token_hash == token_hash(token)))
        await session.commit()
    response.delete_cookie(ACCOUNT_COOKIE, path="/asante/api", httponly=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/asante", samesite="strict")
    response.delete_cookie("asante_review_media", path="/asante/api/v1/review")
    response.headers["Cache-Control"] = "no-store"
    return {"signedOut": True}
