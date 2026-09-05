import base64
import binascii
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings


PASSWORD_ITERATIONS = 120_000
LEGACY_LOCAL_SECRET_PREFIX = "dev-v1"
LOCAL_SECRET_PREFIX = "local-v2"
OCI_KMS_SECRET_PREFIX = "oci-kms-v1"
LOCAL_SECRET_NONCE_BYTES = 12
LOCAL_SECRET_KEY_BYTES = 32
LOCAL_SECRET_HKDF_INFO = b"angmoo:credential:local-v2"
_KMS_CLIENT: Any | None = None


@dataclass(frozen=True)
class SecretScope:
    owner_id: str = ""
    character_id: str = ""
    provider: str = ""
    purpose: str = "generic"

    def as_dict(self) -> dict[str, str]:
        return {
            "character_id": self.character_id,
            "owner_id": self.owner_id,
            "provider": self.provider,
            "purpose": self.purpose,
        }


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    parts = password_hash.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = _b64decode(parts[2])
        expected = _b64decode(parts[3])
    except (ValueError, binascii.Error):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def create_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def fingerprint_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


def _credential_key() -> bytes:
    return hashlib.sha256(settings.app_secret.encode("utf-8")).digest()


def _local_v2_key() -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=LOCAL_SECRET_KEY_BYTES,
        salt=None,
        info=LOCAL_SECRET_HKDF_INFO,
    ).derive(settings.app_secret.encode("utf-8"))


def _scope_aad(scope: SecretScope | None) -> bytes:
    normalized = scope or SecretScope()
    return json.dumps(
        normalized.as_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_scope_aad(aad: bytes) -> None:
    try:
        decoded = json.loads(aad.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid local-v2 credential scope") from exc
    if not isinstance(decoded, dict) or set(decoded) != {
        "character_id",
        "owner_id",
        "provider",
        "purpose",
    }:
        raise ValueError("Invalid local-v2 credential scope")
    if not all(isinstance(value, str) for value in decoded.values()):
        raise ValueError("Invalid local-v2 credential scope")
    canonical = json.dumps(
        decoded,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if not hmac.compare_digest(aad, canonical):
        raise ValueError("Invalid local-v2 credential scope")


def _xor_stream(length: int, nonce: bytes) -> bytes:
    key = _credential_key()
    chunks: list[bytes] = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        chunks.append(
            hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        )
        counter += 1
    return b"".join(chunks)[:length]


def _encrypt_secret_legacy_local(secret: str) -> str:
    nonce = secrets.token_bytes(16)
    plain = secret.encode("utf-8")
    stream = _xor_stream(len(plain), nonce)
    cipher = bytes(left ^ right for left, right in zip(plain, stream, strict=True))
    mac = hmac.new(_credential_key(), nonce + cipher, hashlib.sha256).digest()
    return (
        f"{LEGACY_LOCAL_SECRET_PREFIX}:"
        f"{_b64encode(nonce)}:{_b64encode(cipher)}:{_b64encode(mac)}"
    )


def _decrypt_secret_legacy_local(payload: str) -> str:
    try:
        version, nonce_raw, cipher_raw, mac_raw = payload.split(":", 3)
    except ValueError as exc:
        raise ValueError("Invalid credential envelope") from exc
    if version != LEGACY_LOCAL_SECRET_PREFIX:
        raise ValueError("Unsupported credential envelope")
    nonce = _b64decode(nonce_raw)
    cipher = _b64decode(cipher_raw)
    mac = _b64decode(mac_raw)
    expected = hmac.new(_credential_key(), nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Credential envelope failed authentication")
    stream = _xor_stream(len(cipher), nonce)
    plain = bytes(left ^ right for left, right in zip(cipher, stream, strict=True))
    return plain.decode("utf-8")


def _encrypt_secret_local_v2(secret: str, *, scope: SecretScope | None) -> str:
    nonce = secrets.token_bytes(LOCAL_SECRET_NONCE_BYTES)
    aad = _scope_aad(scope)
    ciphertext = AESGCM(_local_v2_key()).encrypt(
        nonce,
        secret.encode("utf-8"),
        aad,
    )
    return (
        f"{LOCAL_SECRET_PREFIX}:"
        f"{_b64encode(nonce)}:{_b64encode(aad)}:{_b64encode(ciphertext)}"
    )


def _decrypt_secret_local_v2(
    payload: str,
    *,
    scope: SecretScope | None,
) -> str:
    try:
        version, nonce_raw, aad_raw, ciphertext_raw = payload.split(":", 3)
    except ValueError as exc:
        raise ValueError("Invalid local-v2 credential envelope") from exc
    if version != LOCAL_SECRET_PREFIX:
        raise ValueError("Unsupported credential envelope")
    try:
        nonce = _b64decode(nonce_raw)
        aad = _b64decode(aad_raw)
        ciphertext = _b64decode(ciphertext_raw)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid local-v2 credential envelope") from exc
    if len(nonce) != LOCAL_SECRET_NONCE_BYTES:
        raise ValueError("Invalid local-v2 credential nonce")
    _validate_scope_aad(aad)
    if scope is not None and not hmac.compare_digest(aad, _scope_aad(scope)):
        raise ValueError("Credential scope does not match")
    try:
        plaintext = AESGCM(_local_v2_key()).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise ValueError("Credential envelope failed authentication") from exc
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Credential plaintext is not valid UTF-8") from exc


def _kms_client() -> Any:
    global _KMS_CLIENT
    if _KMS_CLIENT is not None:
        return _KMS_CLIENT
    if not settings.oci_kms_crypto_endpoint:
        raise ValueError("OCI_KMS_CRYPTO_ENDPOINT is required for oci_kms encryption")
    if settings.oci_auth_mode != "instance_principal":
        raise ValueError("Only OCI_AUTH_MODE=instance_principal is supported")
    try:
        import oci
        from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
        from oci.key_management import KmsCryptoClient
    except ImportError as exc:
        raise ValueError("OCI SDK is required for oci_kms encryption") from exc
    signer = InstancePrincipalsSecurityTokenSigner()
    config: dict[str, str] = {}
    if settings.oci_region:
        config["region"] = settings.oci_region
    _KMS_CLIENT = KmsCryptoClient(
        config,
        signer=signer,
        service_endpoint=settings.oci_kms_crypto_endpoint,
        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY,
    )
    return _KMS_CLIENT


def _encrypt_secret_oci_kms(secret: str) -> str:
    if not settings.oci_kms_key_id:
        raise ValueError("OCI_KMS_KEY_ID is required for oci_kms encryption")
    try:
        from oci.key_management.models import EncryptDataDetails
    except ImportError as exc:
        raise ValueError("OCI SDK is required for oci_kms encryption") from exc
    plain_b64 = base64.b64encode(secret.encode("utf-8")).decode("ascii")
    details = EncryptDataDetails(
        key_id=settings.oci_kms_key_id,
        plaintext=plain_b64,
        encryption_algorithm=EncryptDataDetails.ENCRYPTION_ALGORITHM_AES_256_GCM,
    )
    response = _kms_client().encrypt(details)
    ciphertext = response.data.ciphertext
    if not ciphertext:
        raise ValueError("OCI KMS returned empty ciphertext")
    return (
        f"{OCI_KMS_SECRET_PREFIX}:"
        f"{_b64encode(settings.oci_kms_key_id.encode('utf-8'))}:"
        f"{_b64encode(ciphertext.encode('utf-8'))}"
    )


def _decrypt_secret_oci_kms(payload: str) -> str:
    try:
        version, key_id_raw, ciphertext_raw = payload.split(":", 2)
    except ValueError as exc:
        raise ValueError("Invalid OCI KMS credential envelope") from exc
    if version != OCI_KMS_SECRET_PREFIX:
        raise ValueError("Unsupported OCI KMS credential envelope")
    try:
        from oci.key_management.models import DecryptDataDetails
    except ImportError as exc:
        raise ValueError("OCI SDK is required for oci_kms decryption") from exc
    key_id = _b64decode(key_id_raw).decode("utf-8")
    ciphertext = _b64decode(ciphertext_raw).decode("utf-8")
    details = DecryptDataDetails(
        key_id=key_id,
        ciphertext=ciphertext,
        encryption_algorithm=DecryptDataDetails.ENCRYPTION_ALGORITHM_AES_256_GCM,
    )
    response = _kms_client().decrypt(details)
    plain_b64 = response.data.plaintext
    if not plain_b64:
        raise ValueError("OCI KMS returned empty plaintext")
    return base64.b64decode(plain_b64).decode("utf-8")


def encrypt_local_secret(secret: str, *, scope: SecretScope) -> str:
    """Write the current local envelope; legacy dev-v1 is read-only."""

    return _encrypt_secret_local_v2(secret, scope=scope)


def encrypt_secret(secret: str, *, scope: SecretScope | None = None) -> str:
    provider = settings.credential_encryption_provider
    if provider in {"local", "dev", LOCAL_SECRET_PREFIX}:
        return _encrypt_secret_local_v2(secret, scope=scope)
    if provider in {"oci_kms", "oci-kms"}:
        return _encrypt_secret_oci_kms(secret)
    raise ValueError(f"Unsupported credential encryption provider: {provider}")


def decrypt_secret(payload: str, *, scope: SecretScope | None = None) -> str:
    if payload.startswith(f"{LOCAL_SECRET_PREFIX}:"):
        return _decrypt_secret_local_v2(payload, scope=scope)
    if payload.startswith(f"{LEGACY_LOCAL_SECRET_PREFIX}:"):
        return _decrypt_secret_legacy_local(payload)
    if payload.startswith(f"{OCI_KMS_SECRET_PREFIX}:"):
        return _decrypt_secret_oci_kms(payload)
    raise ValueError("Unsupported credential envelope")
