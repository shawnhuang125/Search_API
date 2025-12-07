# /utils/security.py
# 這裡專門存放安全處理的工具程式
import hashlib

# 密碼Hash雜湊加密
# 使用sha256
def password_cryptography(password):
    return hashlib.sha256(password.encode()).hexdigest()