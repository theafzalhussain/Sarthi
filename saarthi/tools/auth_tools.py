"""
Auth Tools — website login + credential management.

Ye tools agent ko user ki taraf se websites pe login karne dete hain.

FLOW:
    1. User ek baar credential save karta hai:
         "github ka login save kar — email me@x.com, password hunter2"
       -> credential_save_karo

    2. Baad mein agent khud login kar leta hai:
         "github pe login kar aur mera profile khol"
       -> login_karo (store se username/password uthaata hai)

SECURITY (ye samajhna zaroori hai):
    - Password credential store mein obfuscated save hota hai
      (data/credentials.json — gitignored). Detail: security/credentials.py
    - Login ke waqt password Playwright `fill()` se browser mein jaata
      hai — text_likho wale keystroke path se nahi. Isliye password
      wala safety-block (jo passwords ko type hone se rokta hai) yahan
      LAAGU NAHI hota — ye JAAN-BOOJH ke hai, kyunki ye login ka
      controlled, user-authorized flow hai.
    - OTP / 2FA / PIN yahan handle NAHI hote — wo hamesha user khud
      daalega. Login tool wahin ruk jaata hai aur user ko bolta hai.
    - Passwords kabhi tool ke output/reply mein nahi aate.
"""

from __future__ import annotations

import logging

from ..devices.base import ActionResult
from ..security import CredentialStore
from .base import Tool, ToolContext

log = logging.getLogger("saarthi.tools.auth")


def _get_store(ctx: ToolContext) -> CredentialStore:
    """Credential store scratch mein cache karo (har turn naya ctx banta hai)."""
    store = ctx.scratch.get("credential_store")
    if store is None:
        store = CredentialStore()
        ctx.scratch["credential_store"] = store
    return store


class SaveCredentialTool(Tool):
    name = "login_save_karo"
    description = (
        "Save a website login (username/email + password) so the agent "
        "can sign in later on its own. Use this when the user says things "
        "like 'ye login yaad rakh', 'github ka password save kar', 'mera "
        "email-password store kar' (remember/save this login). The password "
        "is stored obfuscated. Never save an OTP/PIN — the user enters those."
    )
    parameters = {
        "type": "object",
        "properties": {
            "site": {
                "type": "string",
                "description": "The website name or domain, e.g. 'github.com' or 'gmail'",
            },
            "username": {
                "type": "string",
                "description": "Email or username",
            },
            "password": {
                "type": "string",
                "description": "Password",
            },
            "login_url": {
                "type": "string",
                "description": "Optional — the full login page URL (if known)",
            },
        },
        "required": ["site", "username", "password"],
    }
    risky = True  # storing a credential — the user should know

    async def run(
        self,
        ctx: ToolContext,
        site: str,
        username: str,
        password: str,
        login_url: str = "",
    ) -> ActionResult:
        store = _get_store(ctx)
        try:
            cred = store.save(site, username, password, login_url=login_url)
        except ValueError as exc:
            return ActionResult.failure(str(exc))

        # Password kabhi output mein nahi — masked dikhao
        return ActionResult.success(
            f"Login save ho gaya: {cred.masked()}\n"
            f"Ab bol sakta hai '{cred.site} pe login kar' — main khud kar dunga."
        )


class ListCredentialsTool(Tool):
    name = "logins_dikhao"
    description = (
        "Show which websites have a saved login (password hidden). "
        "Use this when the user asks 'which logins are saved'."
    )
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext) -> ActionResult:
        store = _get_store(ctx)
        creds = store.list_sites()
        if not creds:
            return ActionResult.success(
                "Abhi koi login save nahi hai. 'login_save_karo' se save kar sakta hai."
            )
        lines = [f"{len(creds)} login save hain:"]
        lines += [f"  - {c.masked()}" for c in creds]
        return ActionResult.success("\n".join(lines))


class DeleteCredentialTool(Tool):
    name = "login_hata_do"
    description = "Delete a website's saved login."
    parameters = {
        "type": "object",
        "properties": {
            "site": {"type": "string", "description": "The website name or domain"}
        },
        "required": ["site"],
    }
    risky = True

    async def run(self, ctx: ToolContext, site: str) -> ActionResult:
        store = _get_store(ctx)
        if store.delete(site):
            return ActionResult.success(f"'{site}' ka login hata diya.")
        return ActionResult.failure(f"'{site}' naam ka koi saved login nahi mila.")


class LoginTool(Tool):
    name = "login_karo"
    description = (
        "Log in to a website — on the user's behalf. Open the site in the "
        "browser (or use one already open) and fill in email/username + "
        "password, then click sign-in.\n"
        "Credentials come from TWO sources:\n"
        "  1. The site's login was saved earlier via 'login_save_karo' -> "
        "just give the site and it is pulled from the store: site='github'\n"
        "  2. The user just gave username/password -> pass them directly: "
        "site='github', username='me@x.com', password='...'\n"
        "AFTER logging in, use screenshot_lo/page_padho (device='browser') "
        "to confirm it worked. If it asks for OTP/2FA, let the user enter "
        "it — you do not type that."
    )
    parameters = {
        "type": "object",
        "properties": {
            "site": {
                "type": "string",
                "description": "The website name/domain, e.g. 'github' or 'gmail'",
            },
            "username": {
                "type": "string",
                "description": (
                    "Email/username. If omitted, taken from the saved credential."
                ),
            },
            "password": {
                "type": "string",
                "description": (
                    "Password. If omitted, taken from the saved credential."
                ),
            },
            "login_url": {
                "type": "string",
                "description": (
                    "Optional — the login page URL. If omitted, the site "
                    "name/saved URL is used."
                ),
            },
        },
        "required": ["site"],
    }
    risky = True  # Login karna — user ko pata hona chahiye

    async def run(
        self,
        ctx: ToolContext,
        site: str,
        username: str = "",
        password: str = "",
        login_url: str = "",
    ) -> ActionResult:
        # Credentials: args se ya store se
        if not (username and password):
            store = _get_store(ctx)
            cred = store.get(site)
            if cred is None:
                return ActionResult.failure(
                    f"'{site}' ka koi saved login nahi hai aur username/"
                    f"password bhi nahi diya. Pehle 'login_save_karo' se "
                    f"save kar, ya username aur password de."
                )
            username = username or cred.username
            password = password or cred.password
            if not login_url:
                login_url = cred.login_url

        if not password:
            return ActionResult.failure(
                "Password nahi mila. Bina password ke login nahi ho sakta."
            )

        # login_url na ho to site ka naam hi de do — browser resolve kar lega
        target_url = login_url or site

        # Browser device dhoondo
        browser = ctx.devices.get("browser")
        if browser is None:
            return ActionResult.failure(
                "Browser device available nahi hai. Playwright install kar: "
                "pip install playwright && playwright install chromium"
            )

        login_fn = getattr(browser, "login", None)
        if login_fn is None:
            return ActionResult.failure(
                "Ye browser login support nahi karta."
            )

        result = await login_fn(
            username=username, password=password, login_url=target_url
        )
        return result


def auth_tools() -> list[Tool]:
    return [
        LoginTool(),
        SaveCredentialTool(),
        ListCredentialsTool(),
        DeleteCredentialTool(),
    ]
