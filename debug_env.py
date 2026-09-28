from config import settings
print("API_KEYS value:", repr(settings.api_keys))
print("Auth on:", bool(settings.api_key_list))