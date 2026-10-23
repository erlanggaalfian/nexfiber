"""One-off CLI to create the first admin user (PRD 4.6/X: no self-registration).
Usage: python scripts/create_admin.py <username> <email> <full_name> <password>
"""

import asyncio
import sys

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.user import User


async def main(username: str, email: str, full_name: str, password: str) -> None:
    async with SessionLocal() as db:
        db.add(
            User(
                username=username,
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                role="admin",
            )
        )
        await db.commit()
    print(f"Admin user '{username}' created.")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(*sys.argv[1:5]))
