"""
PKI certificate management for hub_api.

Provides X.509 certificate generation, validation, and CA management.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import structlog
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend

logger = structlog.get_logger()


class CertificateManager:
    """
    Manages X.509 certificates for the cluster.

    Provides CA certificate generation, node certificate signing, and certificate validation.
    """

    def __init__(self) -> None:
        """
        Initialize the CertificateManager.

        Sets up instance variables for CA cert/key.
        Generates a self-signed CA certificate immediately so it's available
        for use without calling initialize().
        """
        self.ca_cert: Optional[x509.Certificate] = None
        self.ca_key: Optional[ec.EllipticCurvePrivateKey] = None
        self._initialized: bool = False

        # Generate CA immediately
        self._generate_ca()

    async def initialize(self) -> None:
        """
        Initialize the CA certificate.

        Loads CA from PEM files specified by CA_CERT_PATH and CA_KEY_PATH
        environment variables if they exist and are readable. If files don't
        exist but paths are set, persists the CA that was generated in __init__.

        If CA_CERT_PATH and CA_KEY_PATH are set, persists the CA with file
        permissions 0o600.

        Raises:
            ValueError: If loaded CA certificate is not a valid CA or fails validation.
        """
        try:
            ca_cert_path = os.getenv("CA_CERT_PATH")
            ca_key_path = os.getenv("CA_KEY_PATH")

            if ca_cert_path and ca_key_path and os.path.exists(ca_cert_path) and os.path.exists(ca_key_path):
                # Load existing CA from PEM files
                logger.info("Loading existing CA from files", cert_path=ca_cert_path, key_path=ca_key_path)
                with open(ca_cert_path, "rb") as f:
                    cert_pem = f.read()
                    self.ca_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

                with open(ca_key_path, "rb") as f:
                    key_pem = f.read()
                    self.ca_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())

                # Validate loaded CA is a valid CA certificate (fail closed on invalid)
                self._validate_ca_certificate(self.ca_cert)
                logger.info("CA loaded successfully and validated")
            elif ca_cert_path and ca_key_path:
                # Persist CA that was generated in __init__
                self._persist_ca(ca_cert_path, ca_key_path)
                logger.info("CA persisted to files", cert_path=ca_cert_path, key_path=ca_key_path)
            else:
                # CA already generated in __init__, just log
                logger.info("Using in-memory CA from __init__")

            self._initialized = True
            logger.info("CertificateManager initialized")
        except Exception as e:
            logger.error("Failed to initialize CertificateManager", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown the CertificateManager (cleanup/no-op)."""
        logger.info("CertificateManager shutdown")

    async def is_healthy(self) -> bool:
        """
        Check if the CertificateManager is healthy.

        Returns True if the CA certificate has been initialized.

        Returns:
            True if CA is present and initialized, False otherwise.
        """
        return self._initialized and self.ca_cert is not None

    async def generate_certificate(
        self,
        node_id: str,
        node_type: str,
        validity_days: int = 365,
    ) -> Dict[str, str]:
        """
        Generate a signed X.509 certificate for a node.

        Creates a leaf certificate signed by the CA. The node_id and node_type
        are encoded in the certificate subject (CN=node_id, OU=node_type).

        Args:
            node_id: Unique identifier for the node.
            node_type: Type of node (e.g., 'client', 'headend').
            validity_days: Certificate validity period in days (default: 365).

        Returns:
            Dictionary containing:
            - certificate: PEM-encoded certificate string
            - private_key: PEM-encoded private key string
            - ca_certificate: PEM-encoded CA certificate string
        """
        if not self.ca_cert or not self.ca_key:
            raise ValueError("CA not initialized")

        try:
            # Generate a new EC private key for the leaf certificate
            private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

            # Create certificate subject with node_id and node_type
            subject = x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, node_id),
                    x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, node_type),
                ]
            )

            # Get CA issuer
            issuer = self.ca_cert.subject

            # Build certificate
            cert_builder = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=validity_days))
            )

            # Sign with CA key
            certificate = cert_builder.sign(self.ca_key, hashes.SHA256(), default_backend())

            # Serialize to PEM
            cert_pem = certificate.public_bytes(serialization.Encoding.PEM).decode("utf-8")
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")
            ca_pem = self.ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

            return {
                "certificate": cert_pem,
                "private_key": key_pem,
                "ca_certificate": ca_pem,
            }
        except Exception as e:
            logger.error("Failed to generate certificate", node_id=node_id, error=str(e))
            raise

    async def validate_certificate(self, cert_pem: str) -> Dict[str, any]:
        """
        Validate an X.509 certificate.

        Verifies that the certificate was signed by the CA, checks the validity
        window (not_before/not_after), and verifies the issuer matches the CA.
        Extracts the node_id and node_type from the subject.

        Args:
            cert_pem: PEM-encoded certificate string.

        Returns:
            Dictionary containing:
            - valid: Boolean indicating certificate validity
            - node_id: Node identifier from certificate CN
            - node_type: Node type from certificate OU
            - not_before: Certificate validity start time (timezone-aware UTC)
            - not_after: Certificate validity end time (timezone-aware UTC)
        """
        try:
            # Load certificate
            certificate = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())

            # Verify signature using CA public key
            try:
                ca_public_key = self.ca_cert.public_key()
                # Verify will raise InvalidSignature if signature is invalid
                ca_public_key.verify(
                    certificate.signature,
                    certificate.tbs_certificate_bytes,
                    ec.ECDSA(hashes.SHA256()) if isinstance(ca_public_key, ec.EllipticCurvePublicKey) else None,
                )
            except Exception:
                return {
                    "valid": False,
                    "node_id": None,
                    "node_type": None,
                    "not_before": None,
                    "not_after": None,
                }

            # Verify issuer matches CA subject
            if certificate.issuer != self.ca_cert.subject:
                return {
                    "valid": False,
                    "node_id": None,
                    "node_type": None,
                    "not_before": None,
                    "not_after": None,
                }

            # Check validity window with timezone-aware UTC
            not_before = certificate.not_valid_before_utc
            not_after = certificate.not_valid_after_utc
            now = datetime.now(timezone.utc)

            if now < not_before or now > not_after:
                return {
                    "valid": False,
                    "node_id": None,
                    "node_type": None,
                    "not_before": not_before,
                    "not_after": not_after,
                }

            # Extract node_id (CN) and node_type (OU) from subject
            node_id = None
            node_type = None

            for attr in certificate.subject:
                if attr.oid == NameOID.COMMON_NAME:
                    node_id = attr.value
                elif attr.oid == NameOID.ORGANIZATIONAL_UNIT_NAME:
                    node_type = attr.value

            return {
                "valid": True,
                "node_id": node_id,
                "node_type": node_type,
                "not_before": not_before,
                "not_after": not_after,
            }
        except Exception as e:
            logger.error("Failed to validate certificate", error=str(e))
            return {
                "valid": False,
                "node_id": None,
                "node_type": None,
                "not_before": None,
                "not_after": None,
            }

    async def generate_headend_certificate(
        self,
        cluster_id: str,
        name: str,
        sans: List[str],
    ) -> Tuple[str, str, str]:
        """
        Generate a certificate for a headend node.

        Creates an X.509 certificate with SubjectAltName entries for the
        specified SANs.

        Args:
            cluster_id: Cluster identifier to use as node_id.
            name: Certificate common name.
            sans: List of Subject Alternative Names (DNS entries).

        Returns:
            Tuple of (private_key_pem, certificate_pem, ca_certificate_pem)
        """
        try:
            # Use internal method with headend node type
            cert_dict = await self.generate_certificate(cluster_id, "headend", validity_days=365)

            # Load certificate to add SANs
            certificate = x509.load_pem_x509_certificate(
                cert_dict["certificate"].encode(),
                default_backend(),
            )

            # Create new certificate with SANs
            private_key = serialization.load_pem_private_key(
                cert_dict["private_key"].encode(),
                password=None,
                backend=default_backend(),
            )

            # Rebuild with SANs
            san_list = [x509.DNSName(san) for san in sans]
            cert_builder = (
                x509.CertificateBuilder()
                .subject_name(certificate.subject)
                .issuer_name(certificate.issuer)
                .public_key(certificate.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(certificate.not_valid_before)
                .not_valid_after(certificate.not_valid_after)
                .add_extension(
                    x509.SubjectAlternativeName(san_list),
                    critical=False,
                )
            )

            signed_cert = cert_builder.sign(self.ca_key, hashes.SHA256(), default_backend())
            cert_pem = signed_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

            return (cert_dict["private_key"], cert_pem, cert_dict["ca_certificate"])
        except Exception as e:
            logger.error("Failed to generate headend certificate", cluster_id=cluster_id, error=str(e))
            raise

    async def generate_client_certificate(
        self,
        client_id: str,
        name: str,
        client_type: str,
    ) -> Tuple[str, str, str]:
        """
        Generate a certificate for a client node.

        Args:
            client_id: Client identifier to use as node_id.
            name: Certificate common name.
            client_type: Client type (docker, native, etc.).

        Returns:
            Tuple of (private_key_pem, certificate_pem, ca_certificate_pem)
        """
        try:
            cert_dict = await self.generate_certificate(client_id, "client", validity_days=365)
            return (cert_dict["private_key"], cert_dict["certificate"], cert_dict["ca_certificate"])
        except Exception as e:
            logger.error("Failed to generate client certificate", client_id=client_id, error=str(e))
            raise

    def _is_certificate_expiring(self, expiry: datetime, threshold_days: int = 30) -> bool:
        """
        Check if a certificate is expiring within the threshold.

        Args:
            expiry: Certificate expiration time (datetime object).
            threshold_days: Number of days to check before expiration.

        Returns:
            True if expiry is within threshold_days from now, False otherwise.
        """
        # Handle naive datetimes by comparing against naive utcnow
        now = datetime.utcnow()

        # If expiry has timezone info, make now aware; if naive, keep now naive
        if expiry.tzinfo is not None:
            now = now.replace(tzinfo=timezone.utc)

        threshold = timedelta(days=threshold_days)
        return expiry - now <= threshold

    def _validate_ca_certificate(self, cert: x509.Certificate) -> None:
        """
        Validate that a certificate is a valid CA certificate.

        Checks that the certificate has BasicConstraints extension with ca=True.
        Fails closed (raises exception) if validation fails.

        Args:
            cert: The certificate to validate.

        Raises:
            ValueError: If certificate is not a valid CA or lacks required constraints.
        """
        try:
            # Check for BasicConstraints extension
            try:
                basic_constraints = cert.extensions.get_extension_for_class(
                    x509.BasicConstraints
                )
            except x509.ExtensionNotFound:
                raise ValueError("CA certificate missing BasicConstraints extension")

            # Verify ca=True
            if not basic_constraints.value.ca:
                raise ValueError("Certificate BasicConstraints.ca is not True; not a valid CA")

            logger.info("CA certificate validated successfully")
        except (ValueError, AttributeError, TypeError) as e:
            # Fail closed: any validation error means reject the CA
            logger.error("CA certificate validation failed", error=str(e))
            raise

    def _generate_ca(self) -> None:
        """
        Generate a self-signed CA certificate.

        Creates an EC (SECP256R1) key pair and a self-signed CA certificate
        with basic constraints extension.
        """
        # Generate CA private key (EC)
        self.ca_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

        # Create CA subject
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SASEWaddle"),
                x509.NameAttribute(NameOID.COMMON_NAME, "SASEWaddle CA"),
            ]
        )

        # Build self-signed certificate
        cert_builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(self.ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=3650))  # 10 years
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
        )

        # Self-sign
        self.ca_cert = cert_builder.sign(self.ca_key, hashes.SHA256(), default_backend())

    def _persist_ca(self, cert_path: str, key_path: str) -> None:
        """
        Persist CA certificate and key to PEM files using atomic writes.

        Prevents TOCTOU (time-of-check-time-of-use) symlink attacks by writing to
        temp files with O_EXCL, then using os.replace() for atomic rename.

        Args:
            cert_path: Path to save CA certificate.
            key_path: Path to save CA private key.

        Raises:
            ValueError: If CA not initialized or file operations fail.
        """
        if not self.ca_cert or not self.ca_key:
            raise ValueError("CA not initialized")

        # Create directories if needed with secure permissions
        cert_dir = os.path.dirname(cert_path) or "."
        key_dir = os.path.dirname(key_path) or "."
        os.makedirs(cert_dir, mode=0o700, exist_ok=True)
        os.makedirs(key_dir, mode=0o700, exist_ok=True)

        # Write certificate: create temp file with O_EXCL, then atomic replace
        cert_pem = self.ca_cert.public_bytes(serialization.Encoding.PEM)
        cert_temp_fd, cert_temp_path = tempfile.mkstemp(dir=cert_dir, prefix=".ca_cert_", suffix=".tmp")
        try:
            # Ensure secure permissions on temp file
            os.chmod(cert_temp_path, 0o600)
            with os.fdopen(cert_temp_fd, "wb") as f:
                f.write(cert_pem)
            # Atomic rename (prevents symlink race if cert_path exists as symlink)
            os.replace(cert_temp_path, cert_path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(cert_temp_path)
            except Exception:
                pass
            raise

        # Write key: create temp file with O_EXCL, then atomic replace
        key_pem = self.ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_temp_fd, key_temp_path = tempfile.mkstemp(dir=key_dir, prefix=".ca_key_", suffix=".tmp")
        try:
            # Ensure secure permissions on temp file
            os.chmod(key_temp_path, 0o600)
            with os.fdopen(key_temp_fd, "wb") as f:
                f.write(key_pem)
            # Atomic rename (prevents symlink race if key_path exists as symlink)
            os.replace(key_temp_path, key_path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(key_temp_path)
            except Exception:
                pass
            raise
