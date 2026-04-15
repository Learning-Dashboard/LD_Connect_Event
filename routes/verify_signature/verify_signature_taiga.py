import hashlib
import hmac

def verify_taiga_signature(request, secret):
    """
    Validates the Taiga HMAC-SHA1 signature on the incoming request.

    """
    # Grab the signature from the header of the request
    signature_header = request.headers.get("X-TAIGA-WEBHOOK-SIGNATURE", "")

    # The raw request body, as bytes
    raw_body = request.data

    # If the secret is a string, encode it to bytes
    if isinstance(secret, str):
        secret = secret.encode("utf-8")

    # Re-compute the HMAC (sha1)
    mac = hmac.new(secret, msg=raw_body, digestmod=hashlib.sha1)
    expected_sig = mac.hexdigest()

    # Compare them
    return hmac.compare_digest(expected_sig, signature_header)
