'''
   Copyright 2025-2026 AIIrondev

   Licensed under the Inventarsystem EULA (Endbenutzer-Lizenzvertrag).
   See Legal/LICENSE for the full license text.
   Unauthorized commercial use, SaaS hosting, or removal of branding is prohibited.
   For commercial licensing inquiries: https://github.com/AIIrondev
'''
import user
import sys
import getpass
import re

def is_valid_username(username):
    """Check if username follows valid pattern (letters, numbers, underscore)"""
    return bool(re.match(r'^[a-zA-Z0-9_]+$', username))

def is_valid_password(password):
    """Check if password meets minimum requirements"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    return True, ""

def generate_user_interactive():
    print("========================================")
    print("       User Generation Interface        ")
    print("========================================")
    
    # Get username
    while True:
        username = input("Enter username: ").strip()
        if not username:
            print("Error: Username cannot be empty")
            continue
        if not is_valid_username(username):
            print("Error: Username can only contain letters, numbers, and underscores")
            continue
        break
    
    # Get password
    while True:
        password = getpass.getpass("Enter password: ")
        if not password:
            print("Error: Password cannot be empty")
            continue
        
        valid, message = is_valid_password(password)
        if not valid:
            print(f"Error: {message}")
            continue
            
        confirm_password = getpass.getpass("Confirm password: ")
        if password != confirm_password:
            print("Error: Passwords do not match")
            continue
        
        break
    
    # Ask if admin
    while True:
        admin_input = input("Make this user an admin? (y/n): ").lower().strip()
        if admin_input in ['y', 'yes']:
            is_admin = True
            break
        elif admin_input in ['n', 'no']:
            is_admin = False
            break
        else:
            print("Please enter 'y' or 'n'")
    
    while True:
        name_input = input("Enter a first name for the user:")
        if not name_input:
            print("You have to provide a name!")
        else:
            break
    
    while True:
        last_name_input = input("Enter a last name for the user:")
        if not last_name_input:
            print("You have to provide a name!")
        else:
            break

    
    # Add the user
    added = user.add_user(username, password, name_input, last_name_input)
    
    if added:
        print(f"User '{username}' created successfully.")
        if is_admin:
            admin_result = user.make_admin(username)
            if admin_result:
                print(f"User '{username}' has been given administrator privileges.")
            else:
                print(f"Warning: Failed to make user '{username}' an administrator.")
    else:
        print(f"Error: Failed to create user '{username}'. Username may already exist.")
    
    return added

if __name__ == "__main__":
    generate_user_interactive()
