from app.core.security import get_password_hash, verify_password


def test_api_client_secret_can_be_hashed_and_verified():
    secret = "rag-manual-client-secret"

    hashed_secret = get_password_hash(secret)

    assert hashed_secret != secret
    assert verify_password(secret, hashed_secret)
    assert not verify_password("incorrect-secret", hashed_secret)
