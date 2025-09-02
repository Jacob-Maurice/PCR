import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# If you don't already have app.secret_key, you can hardcode it here or generate it.
# app.secret_key should be a 32-byte URL-safe base64 string, generated securely.
def generate_secret_key():
    return base64.urlsafe_b64encode(os.urandom(32))  # Generates a 32-byte key for Fernet

# Function to encrypt the generated Fernet key with the app's secret key
def encrypt_key_with_secret_key(secret_key, encryption_key):
    fernet = Fernet(secret_key)
    encrypted_key = fernet.encrypt(encryption_key)
    return encrypted_key

# Generate a new Fernet key (this will be the key we encrypt)
def generate_user_encryption_key():
    encryption_key = os.urandom(32)  # Generate a 32-byte encryption key
    return encryption_key

# Main function to generate and save the encrypted key
def generate_and_save_encrypted_key():
    # Generate the app's secret key (you can replace this with your own secret key)
    app_secret_key = generate_secret_key()
    
    # Generate a new encryption key
    encryption_key = generate_user_encryption_key()

    # Encrypt the encryption key using the app's secret key
    encrypted_key = encrypt_key_with_secret_key(app_secret_key, encryption_key)

    # Save the encrypted key to a file (you can name it as needed)
    encrypted_key_filename = "encrypted_key.bin"
    with open(encrypted_key_filename, 'wb') as file:
        file.write(encrypted_key)

    print(f"Encrypted key saved to {encrypted_key_filename}")
    print(f"App secret key (used for encryption): {app_secret_key.decode()}")  # Print for debugging purposes

if __name__ == "__main__":
    generate_and_save_encrypted_key()
