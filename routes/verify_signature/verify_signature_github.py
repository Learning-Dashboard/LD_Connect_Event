import hashlib
import hmac


def verify_github_signature(request, secret):
    """
    Validates the GitHub HMAC signature on the incoming request.
    
    """
    # The signature sent by GitHub, e.g. "sha256=abc123..."
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    
    # The raw request body (as bytes), essential for computing HMAC
    raw_body = request.data
    
    # Compute our own HMAC sha256
    expected_signature = "sha256=" + hmac.new(
        secret,
        raw_body,
        hashlib.sha256
    ).hexdigest()

    # Safely compare the two
    return hmac.compare_digest(expected_signature, signature_header)
