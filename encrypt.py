from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()
password ="Y2J@protect"  # Replace with your actual password

hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
print("Hashed Password:", hashed_password)
