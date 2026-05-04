"""
One-time setup: creates the database and seeds default departments.
Run: python setup.py
"""
import os
import sys

def check_env():
    env_file = '.env'
    if not os.path.exists(env_file):
        if os.path.exists('.env.example'):
            import shutil
            shutil.copy('.env.example', '.env')
            print("Created .env from .env.example — please edit it with your MySQL credentials.")
        else:
            print("No .env file found. Create one with DB_USER, DB_PASSWORD, DB_NAME.")
        sys.exit(1)

def main():
    check_env()
    from app import create_app
    from extensions import db
    from models.user import User
    from models.department import Department

    app = create_app()
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Tables created successfully.")

        depts = [
            ('Computer Science', 'CS'),
            ('Information Technology', 'IT'),
            ('Electronics & Communication', 'ECE'),
            ('Mechanical Engineering', 'ME'),
            ('Civil Engineering', 'CE'),
        ]
        for name, code in depts:
            if not Department.query.filter_by(code=code).first():
                db.session.add(Department(name=name, code=code))
        db.session.commit()
        print("Default departments seeded.")
        if not User.query.filter_by(role='admin').first():
            print("No admin account exists yet. Create one with: flask create-admin")
        print("\nSetup complete! Run the app with: python run.py")

if __name__ == '__main__':
    main()
