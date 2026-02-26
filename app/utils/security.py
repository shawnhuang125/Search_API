# app/utils/security.py
import hashlib

# 密碼Hash雜湊加密
# 使用sha256
def password_cryptography(password):
    return hashlib.sha256(password.encode()).hexdigest()