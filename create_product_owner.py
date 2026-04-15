#!/usr/bin/env python3
"""
Create a Product Owner user for ScrumPilot.

This script creates a user with the 'product_owner' role, which is required
for the backlog pipeline approval workflow.
"""
import sys
from backend.db.connection import get_session
from backend.db.models import User, Role


def create_product_owner(
    display_name: str,
    email: str,
    telegram_user_id: int = None,
    telegram_chat_id: int = None
):
    """
    Create a product owner user.
    
    Args:
        display_name: User's display name
        email: User's email address
        telegram_user_id: Optional Telegram user ID
        telegram_chat_id: Optional Telegram chat ID
    """
    with get_session() as session:
        # Check if product_owner role exists
        po_role = session.query(Role).filter(
            Role.role_name == 'product_owner'
        ).first()
        
        if not po_role:
            print("ERROR: 'product_owner' role not found in database.")
            print("Please run database migrations first: alembic upgrade head")
            return False
        
        # Check if user with this email already exists
        existing_user = session.query(User).filter(
            User.email == email
        ).first()
        
        if existing_user:
            print(f"User with email '{email}' already exists (ID: {existing_user.id})")
            
            # Update role if needed
            if existing_user.role_id != po_role.role_id:
                print(f"Updating user role to 'product_owner'...")
                existing_user.role_id = po_role.role_id
                session.commit()
                print("✓ User role updated successfully")
            else:
                print("✓ User already has 'product_owner' role")
            
            # Update Telegram info if provided
            if telegram_user_id and telegram_chat_id:
                existing_user.telegram_user_id = telegram_user_id
                existing_user.telegram_chat_id = telegram_chat_id
                session.commit()
                print("✓ Telegram info updated")
            
            return True
        
        # Create new user
        new_user = User(
            display_name=display_name,
            email=email,
            role_id=po_role.role_id,
            account_status='active',
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id
        )
        
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        
        print(f"✓ Created product owner user successfully!")
        print(f"  ID: {new_user.id}")
        print(f"  Name: {new_user.display_name}")
        print(f"  Email: {new_user.email}")
        print(f"  Role: product_owner")
        
        if telegram_user_id:
            print(f"  Telegram User ID: {telegram_user_id}")
            print(f"  Telegram Chat ID: {telegram_chat_id}")
        else:
            print("\n⚠ Note: Telegram info not provided.")
            print("  To receive approval notifications, link Telegram using:")
            print("  1. Start a chat with your Telegram bot")
            print("  2. Send /start command")
            print("  3. Send /link command with your email")
        
        return True


def main():
    """Main entry point."""
    print("=" * 70)
    print("ScrumPilot - Create Product Owner User")
    print("=" * 70)
    print()
    
    # Get user input
    display_name = input("Enter display name (e.g., 'John Doe'): ").strip()
    if not display_name:
        print("ERROR: Display name is required")
        return 1
    
    email = input("Enter email address: ").strip()
    if not email:
        print("ERROR: Email is required")
        return 1
    
    print()
    print("Telegram Integration (Optional)")
    print("If you want to receive approval notifications via Telegram,")
    print("you need to provide your Telegram user ID and chat ID.")
    print("You can get these by chatting with your bot and using /start")
    print()
    
    telegram_input = input("Do you have Telegram info to add? (y/n): ").strip().lower()
    
    telegram_user_id = None
    telegram_chat_id = None
    
    if telegram_input == 'y':
        try:
            telegram_user_id = int(input("Enter Telegram user ID: ").strip())
            telegram_chat_id = int(input("Enter Telegram chat ID: ").strip())
        except ValueError:
            print("WARNING: Invalid Telegram IDs. Skipping Telegram integration.")
            telegram_user_id = None
            telegram_chat_id = None
    
    print()
    print("Creating user...")
    print()
    
    success = create_product_owner(
        display_name=display_name,
        email=email,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id
    )
    
    if success:
        print()
        print("=" * 70)
        print("Setup complete! You can now run the backlog pipeline.")
        print("=" * 70)
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
