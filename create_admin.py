import os
import sys
import argparse
from getpass import getpass

# Add the project root to the Python path to allow imports from 'app'
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

from app.database import SessionLocal
from app.models.pond import User, UserRole, Pond
from app.models.sensor import SensorData
from app.models.alert import Alert
from app.models.alert import PondHealth
from app.core.security import get_password_hash


def create_admin_user(db_session, username, email, password, recreate=False):
    """Creates an admin user, optionally deleting an existing one first."""
    
    # Check if user already exists
    existing_user = db_session.query(User).filter(
        (User.username == username) | (User.email == email)
    ).first()
    
    if existing_user:
        if recreate:
            print(f"Found existing user '{existing_user.username}'. Deleting before recreation.")
            db_session.delete(existing_user)
            db_session.commit()
        else:
            print(f"Error: User with username '{username}' or email '{email}' already exists.")
            print("Use the --recreate flag to delete the existing user first.")
            return

    # Hash the password
    hashed_password = get_password_hash(password)
    
    # Create the new admin user
    admin_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True  # Admins should be verified by default
    )
    
    db_session.add(admin_user)
    db_session.commit()
    
    print(f"Successfully created admin user '{username}' with email '{email}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or recreate an admin user.")
    parser.add_argument("--username", required=True, help="Username for the new admin.")
    parser.add_argument("--email", required=True, help="Email for the new admin.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="If the user already exists, delete them before creating the new admin."
    )
    
    args = parser.parse_args()
    
    password = getpass("Enter password for the new admin: ")
    password_confirm = getpass("Confirm password: ")
    
    if password != password_confirm:
        print("Error: Passwords do not match.")
        sys.exit(1)
        
    db = SessionLocal()
    try:
        create_admin_user(db, args.username, args.email, password, recreate=args.recreate)
    finally:
        db.close()