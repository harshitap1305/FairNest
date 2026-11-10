"""Demo data loader: 4 hostels, 5 floors each, ~100 beds, 300 students."""

from __future__ import annotations

import asyncio
import os
import sys
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.client import close_db, connect_db, get_db
from app.db.indexes import create_indexes
from app.db.validators import create_validators
from app.repositories import catalogue as cat_repo, core_repos as repo, users as user_repo

HOSTELS = [
    {
        "name": "Boys Hostel 1",
        "code": "BH1",
        "allowed_gender": "M",
        "allowed_years": [1, 2, 3, 4],
        "active": True,
    },
    {
        "name": "Boys Hostel 2",
        "code": "BH2",
        "allowed_gender": "M",
        "allowed_years": [1, 2, 3, 4],
        "active": True,
    },
    {
        "name": "Girls Hostel 1",
        "code": "GH1",
        "allowed_gender": "F",
        "allowed_years": [1, 2, 3, 4],
        "active": True,
    },
    {
        "name": "Girls Hostel 2",
        "code": "GH2",
        "allowed_gender": "F",
        "allowed_years": [1, 2, 3, 4],
        "active": True,
    },
]

# Rooms per floor: (from, to, capacity) — giving ~25 beds/hostel = 100 total
FLOOR_ROOMS = [
    [(101, 102, 1), (103, 106, 2)],       # floor 1: 2 singles + 4 doubles = 10 beds
    [(201, 202, 1), (203, 206, 2)],       # floor 2
    [(301, 302, 2), (303, 304, 3)],       # floor 3: 4 doubles + 6 triple = 14 beds
    [(401, 402, 2), (403, 404, 3)],       # floor 4
    [(501, 501, 4), (502, 503, 2)],       # floor 5: 1 quad + 2 doubles = 8 beds
]

rng = random.Random(42)
NAMES = [
    "Aarav", "Aditya", "Amit", "Ananya", "Arjun", "Ayesha", "Deepak", "Divya",
    "Gaurav", "Harsha", "Ishaan", "Jaya", "Kiran", "Lakshmi", "Manish", "Meera",
    "Nikhil", "Nisha", "Pankaj", "Priya", "Rahul", "Riya", "Rohit", "Sakshi",
    "Sandeep", "Shreya", "Siddharth", "Simran", "Sunil", "Swati", "Tarun", "Uma",
    "Varun", "Vidya", "Vikram", "Vinita", "Vishal", "Yamini", "Zaheer", "Zara",
]


async def main():
    settings = get_settings()
    await connect_db(settings.MONGO_URI)
    db = get_db(settings.MONGO_DB)
    await create_indexes(db)
    await create_validators(db)

    print("Creating hostels, floors, and rooms...")
    hostel_ids: dict[str, str] = {}
    for h_data in HOSTELS:
        existing = await cat_repo.get_hostel_by_code(db, h_data["code"])
        if existing:
            if existing.get("active") is None:
                await cat_repo.update_hostel(db, str(existing["_id"]), {"active": True})
            hostel_ids[h_data["code"]] = str(existing["_id"])
            print(f"  Hostel {h_data['code']} already exists")
            continue
        hid = await cat_repo.create_hostel(db, h_data)
        hostel_ids[h_data["code"]] = hid
        for floor_no in range(1, 6):
            fid = await cat_repo.create_floor(db, {
                "hostel_id": hid,
                "floor_no": floor_no,
                "label": f"Floor {floor_no}",
                "active": True,
            })
            rooms_config = FLOOR_ROOMS[floor_no - 1]
            for (from_no, to_no, cap) in rooms_config:
                for room_no_int in range(from_no, to_no + 1):
                    await cat_repo.create_room(db, {
                        "hostel_id": hid,
                        "floor_id": fid,
                        "floor_no": floor_no,
                        "room_no": str(room_no_int),
                        "capacity": cap,
                        "features": [],
                        "status": "ACTIVE",
                    })
        print(f"  Created hostel {h_data['code']} with 5 floors")

    print("Creating 300 demo students...")
    created_count = 0
    for i in range(1, 301):
        gender = "M" if i <= 150 else "F"
        hostel_code = rng.choice(["BH1", "BH2"] if gender == "M" else ["GH1", "GH2"])
        hid = hostel_ids[hostel_code]
        roll_no = f"2024{i:04d}"
        email = f"student{i}@college.edu"
        name = rng.choice(NAMES) + f" {i}"
        year = rng.choice([1, 2, 3, 4])
        existing = await user_repo.find_user_by_email(db, email)
        if existing:
            continue
        uid = await user_repo.create_user(db, {
            "roll_no": roll_no,
            "email": email,
            "name": name,
            "password_hash": hash_password("demo_password_123"),
            "role": "STUDENT",
            "hostel_ids": [hid],
            "managed_hostel_ids": [],
            "status": "ACTIVE",
            "gender": gender,
            "year": year,
            "program": "B.Tech",
            "token_version": 0,
            "activation_token_hash": None,
        })
        await repo.create_credit_account(db, uid, settings.C_INIT)
        created_count += 1

    print(f"  Created {created_count} students")
    print("Demo data loaded successfully!")
    print("Login: student1@college.edu / demo_password_123")
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
