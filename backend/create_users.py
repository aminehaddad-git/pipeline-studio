import auth

# ─── Create initial users ─────────────────────────────────
users_to_create = [
    {
        "username": "admin",
        "full_name": "Amine Haddad",
        "password": "admin123",
        "role": "admin"
    },
    {
        "username": "operator",
        "full_name": "Data Operator",
        "password": "operator123",
        "role": "operator"
    },
    {
        "username": "viewer",
        "full_name": "Business Viewer",
        "password": "viewer123",
        "role": "viewer"
    },
]

print("Creating users...\n")

for u in users_to_create:
    try:
        existing = auth.get_user(u["username"])
        if existing:
            print(f"⚠️  User '{u['username']}' already exists — skipping")
        else:
            auth.create_user(u["username"], u["full_name"], u["password"], u["role"])
            print(f"✅ Created '{u['username']}' (role: {u['role']})")
    except Exception as e:
        print(f"❌ Error creating '{u['username']}': {e}")

print("\nDone! You can now log in with these accounts.")