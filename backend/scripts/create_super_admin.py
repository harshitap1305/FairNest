#!/usr/bin/env python3
"""Bootstrap a super admin user. Run once after first deploy (safe & idempotent)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import clock as _clock
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.client import close_db, connect_db, get_db
from app.db.indexes import create_indexes
from app.db.validators import create_validators
from app.repositories import users as user_repo


async def main() -> None:
    settings = get_settings()
    default_domain = (
        settings.allowed_email_domains_list[0]
        if settings.allowed_email_domains_list
        else "iitbhilai.demo"
    )
    email = (
        os.environ.get("BOOTSTRAP_SUPER_ADMIN_EMAIL")
        or settings.BOOTSTRAP_SUPER_ADMIN_EMAIL
        or f"admin@{default_domain}"
    ).strip().lower()
    password = os.environ.get("BOOTSTRAP_SUPER_ADMIN_PASSWORD")
    if not password:
        import getpass
        password = getpass.getpass("Super admin password: ")
    if not password or len(password) < 12:
        print("ERROR: Password must be at least 12 characters.", file=sys.stderr)
        sys.exit(1)

    await connect_db(settings.MONGO_URI)
    try:
        db = get_db(settings.MONGO_DB)
        await create_indexes(db)
        await create_validators(db)

        pw_hash = hash_password(password)
        now = _clock.now()

        existing = await user_repo.find_user_by_email(db, email)
        if not existing:
            uid = await user_repo.create_user(db, {
                "roll_no": None,
                "email": email,
                "name": "Super Admin",
                "password_hash": pw_hash,
                "role": "SUPER_ADMIN",
                "hostel_ids": [],
                "managed_hostel_ids": [],
                "status": "ACTIVE",
                "gender": "",
                "year": None,
                "program": None,
                "accessibility_verified": False,
                "failed_logins": 0,
                "locked_until": None,
                "token_version": 0,
                "activation_token_hash": None,
                "activation_expires_at": None,
                "last_login_at": None,
            })
            print(f"Created super admin: {email} (id={uid})")
        else:
            uid = str(existing["_id"])
            await user_repo.update_user(db, uid, {
                "role": "SUPER_ADMIN",
                "status": "ACTIVE",
                "password_hash": pw_hash,
                "failed_logins": 0,
                "locked_until": None,
                "updated_at": now,
            })
            print(f"User {email} already existed — updated role to SUPER_ADMIN, status to ACTIVE.")
    finally:
        await close_db()

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
