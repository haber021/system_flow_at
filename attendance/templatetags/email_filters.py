"""
Template filters for email masking and security.
"""
from django import template

register = template.Library()

@register.filter
def mask_email(email):
    """
    Mask email address for security - shows first 3 letters of local part,
    then asterisks, followed by @domain.
    Example: vincenthaber21@gmail.com -> vin****@gmail.com
    """
    if not email or '@' not in str(email):
        return email
    
    email_str = str(email)
    local_part, domain = email_str.split('@', 1)
    
    if len(local_part) <= 3:
        # If local part is 3 chars or less, show all
        masked_local = local_part + '****'
    else:
        # Show first 3 chars + asterisks
        masked_local = local_part[:3] + '****'
    
    return f"{masked_local}@{domain}"

