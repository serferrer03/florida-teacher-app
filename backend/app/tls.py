"""Fase 6: HTTPS en la red local con una autoridad de certificación (CA) propia.

La CA se limita con "Name Constraints" a localhost y a direcciones IP privadas:
aunque alguien robara su clave, no serviría para suplantar webs de Internet en
la tablet. El certificado del servidor se regenera si cambia la IP del PC.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from .crypto import write_private

PRIVATE_NETS = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"]


def is_private(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr in ipaddress.ip_network(n) for n in PRIVATE_NETS)


def lan_ip() -> str:
    import os
    if os.environ.get("LAN_IP"):
        return os.environ["LAN_IP"].strip()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.1.1", 9))  # no envía paquetes: solo elige la interfaz
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _key_pem(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ensure_ca(tls_dir: Path):
    ca_crt, ca_key = tls_dir / "ca.crt", tls_dir / "ca.key"
    if ca_crt.exists() and ca_key.exists():
        cert = x509.load_pem_x509_certificate(ca_crt.read_bytes())
        if cert.not_valid_after_utc > _now() + dt.timedelta(days=30):
            return cert, serialization.load_pem_private_key(ca_key.read_bytes(), None)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Florida Teacher App (CA local)")])
    constraints = x509.NameConstraints(
        permitted_subtrees=[x509.DNSName("localhost")]
        + [x509.IPAddress(ipaddress.ip_network(n)) for n in PRIVATE_NETS],
        excluded_subtrees=None,
    )
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - dt.timedelta(minutes=5)).not_valid_after(_now() + dt.timedelta(days=5 * 365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(constraints, critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    write_private(ca_key, _key_pem(key))
    ca_crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tls_dir / "server.crt").unlink(missing_ok=True)  # forzar nuevo certificado de servidor
    return cert, key


def ensure_certs(data_dir: Path, ip: str | None = None) -> tuple[Path, Path, Path]:
    """Devuelve (server.crt, server.key, ca.crt), creándolos o renovándolos si hace falta."""
    tls_dir = data_dir / "tls"
    tls_dir.mkdir(parents=True, exist_ok=True)
    ip = ip or lan_ip()
    if not is_private(ip):  # la CA solo puede firmar IPs privadas (Name Constraints)
        import logging
        logging.getLogger(__name__).warning("La IP %s no es privada: HTTPS solo funcionará en localhost", ip)
        ip = "127.0.0.1"
    ca_cert, ca_key = _ensure_ca(tls_dir)
    crt, key_path = tls_dir / "server.crt", tls_dir / "server.key"
    if crt.exists() and key_path.exists():
        cert = x509.load_pem_x509_certificate(crt.read_bytes())
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if (ipaddress.ip_address(ip) in sans.get_values_for_type(x509.IPAddress)
                and cert.not_valid_after_utc > _now() + dt.timedelta(days=15)):
            return crt, key_path, tls_dir / "ca.crt"
    key = ec.generate_private_key(ec.SECP256R1())
    alt = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    if ip != "127.0.0.1":
        alt.append(x509.IPAddress(ipaddress.ip_address(ip)))
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Florida Teacher App")]))
        .issuer_name(ca_cert.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - dt.timedelta(minutes=5)).not_valid_after(_now() + dt.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    write_private(key_path, _key_pem(key))
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return crt, key_path, tls_dir / "ca.crt"
