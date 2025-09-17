#!/usr/bin/env python3
"""
Database Manager for Health Tracker
Use this script to manage users and view database contents
"""

import sqlite3
import sys
from datetime import datetime
from werkzeug.security import generate_password_hash

def connect_db():
    """Connect to the database"""
    return sqlite3.connect('database.db')

def list_users():
    """List all users in the database"""
    db = connect_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT id, username, email, name, created_at, target_calories FROM users')
    users = cursor.fetchall()
    
    if not users:
        print("📭 No users in database")
        return
    
    print("\n👥 USERS IN DATABASE:")
    print("=" * 80)
    for user in users:
        print(f"ID: {user[0]}")
        print(f"  Username: {user[1]}")
        print(f"  Email: {user[2] or 'Not provided'}")
        print(f"  Name: {user[3] or 'Not provided'}")
        print(f"  Target Calories: {user[5]}")
        print(f"  Created: {user[4]}")
        print("-" * 40)
    
    db.close()

def create_user(username, password, email=None, name=None):
    """Create a new user"""
    db = connect_db()
    cursor = db.cursor()
    
    # Check if user exists
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cursor.fetchone():
        print(f"❌ User '{username}' already exists")
        db.close()
        return
    
    # Create user
    password_hash = generate_password_hash(password)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO users (username, password_hash, email, name, created_at, target_calories)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (username, password_hash, email, name or username, created_at, 2000))
    
    db.commit()
    print(f"✅ User '{username}' created successfully!")
    db.close()

def delete_user(username):
    """Delete a user and all their data"""
    db = connect_db()
    cursor = db.cursor()
    
    # Get user ID
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    
    if not user:
        print(f"❌ User '{username}' not found")
        db.close()
        return
    
    user_id = user[0]
    
    # Delete all user data
    cursor.execute('DELETE FROM meals WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM activities WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM vitals WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM daily_summary WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    
    db.commit()
    print(f"✅ User '{username}' and all their data deleted")
    db.close()

def view_user_stats(username):
    """View statistics for a specific user"""
    db = connect_db()
    cursor = db.cursor()
    
    # Get user
    cursor.execute('SELECT id, name, target_calories FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    
    if not user:
        print(f"❌ User '{username}' not found")
        db.close()
        return
    
    user_id = user[0]
    
    print(f"\n📊 STATS FOR: {user[1] or username}")
    print("=" * 60)
    
    # Count meals
    cursor.execute('SELECT COUNT(*) FROM meals WHERE user_id = ?', (user_id,))
    meals_count = cursor.fetchone()[0]
    print(f"🍽️  Total meals logged: {meals_count}")
    
    # Count activities
    cursor.execute('SELECT COUNT(*) FROM activities WHERE user_id = ?', (user_id,))
    activities_count = cursor.fetchone()[0]
    print(f"🏃 Total activities logged: {activities_count}")
    
    # Count vitals entries
    cursor.execute('SELECT COUNT(*) FROM vitals WHERE user_id = ?', (user_id,))
    vitals_count = cursor.fetchone()[0]
    print(f"📈 Total vitals entries: {vitals_count}")
    
    # Get latest weight
    cursor.execute('SELECT weight FROM vitals WHERE user_id = ? ORDER BY date DESC LIMIT 1', (user_id,))
    weight = cursor.fetchone()
    if weight:
        print(f"⚖️  Latest weight: {weight[0]} kg")
    
    # Get average daily calories
    cursor.execute('''
        SELECT AVG(total_calories_consumed) 
        FROM daily_summary 
        WHERE user_id = ?
    ''', (user_id,))
    avg_calories = cursor.fetchone()[0]
    if avg_calories:
        print(f"🔥 Average daily calories: {avg_calories:.0f}")
        print(f"🎯 Target calories: {user[2]}")
    
    db.close()

def reset_database():
    """Reset the entire database (delete all data)"""
    response = input("⚠️  This will DELETE ALL DATA. Are you sure? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Cancelled")
        return
    
    db = connect_db()
    cursor = db.cursor()
    
    # Delete all data from all tables
    cursor.execute('DELETE FROM meals')
    cursor.execute('DELETE FROM activities')
    cursor.execute('DELETE FROM vitals')
    cursor.execute('DELETE FROM daily_summary')
    cursor.execute('DELETE FROM api_cache')
    cursor.execute('DELETE FROM food_cache')
    cursor.execute('DELETE FROM users')
    
    db.commit()
    print("✅ Database reset - all data deleted")
    db.close()

def main():
    """Main menu"""
    while True:
        print("\n" + "=" * 60)
        print("🏥 HEALTH TRACKER DATABASE MANAGER")
        print("=" * 60)
        print("1. List all users")
        print("2. Create a user")
        print("3. Delete a user")
        print("4. View user statistics")
        print("5. Reset database (delete all data)")
        print("6. Exit")
        print("-" * 60)
        
        choice = input("Select option (1-6): ")
        
        if choice == '1':
            list_users()
        
        elif choice == '2':
            username = input("Username: ")
            password = input("Password: ")
            email = input("Email (optional): ") or None
            name = input("Full name (optional): ") or None
            create_user(username, password, email, name)
        
        elif choice == '3':
            username = input("Username to delete: ")
            confirm = input(f"Delete '{username}' and all their data? (yes/no): ")
            if confirm.lower() == 'yes':
                delete_user(username)
        
        elif choice == '4':
            username = input("Username to view: ")
            view_user_stats(username)
        
        elif choice == '5':
            reset_database()
        
        elif choice == '6':
            print("👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid option")

if __name__ == "__main__":
    # Initialize database if needed
    from app import init_db
    init_db()
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == 'list':
            list_users()
        elif sys.argv[1] == 'create' and len(sys.argv) >= 4:
            username = sys.argv[2]
            password = sys.argv[3]
            email = sys.argv[4] if len(sys.argv) > 4 else None
            name = sys.argv[5] if len(sys.argv) > 5 else None
            create_user(username, password, email, name)
        elif sys.argv[1] == 'delete' and len(sys.argv) >= 3:
            delete_user(sys.argv[2])
        elif sys.argv[1] == 'stats' and len(sys.argv) >= 3:
            view_user_stats(sys.argv[2])
        elif sys.argv[1] == 'reset':
            reset_database()
        else:
            print("Usage:")
            print("  python db_manager.py                    # Interactive menu")
            print("  python db_manager.py list               # List all users")
            print("  python db_manager.py create <username> <password> [email] [name]")
            print("  python db_manager.py delete <username>  # Delete user")
            print("  python db_manager.py stats <username>   # View user stats")
            print("  python db_manager.py reset              # Reset database")
    else:
        main()
