"""
SAARTHI Security — credentials aur sensitive data ka safe handling.

Abhi ismein credential store hai (email/password), taaki agent
websites pe user ki taraf se login kar sake.
"""

from .credentials import Credential, CredentialStore

__all__ = ["Credential", "CredentialStore"]
