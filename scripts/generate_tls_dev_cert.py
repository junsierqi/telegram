"""Generate a local self-signed TLS certificate for development."""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509  # type: ignore[import-not-found]
from cryptography.hazmat.primitives import hashes, serialization  # type: ignore[import-not-found]
from cryptography.hazmat.primitives.asymmetric import rsa  # type: ignore[import-not-found]
from cryptography.x509.oid import NameOID  # type: ignore[import-not-found]


def generate_self_signed_cert(
    *,
    cert_file: Path,
    key_file: Path,
    common_name: str = "localhost",
    dns_names: list[str] | None = None,
    ip_addresses: list[str] | None = None,
    days: int = 30,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    if not overwrite:
        for path in (cert_file, key_file):
            if path.exists():
                raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")

    cert_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.parent.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "telegram-like local dev"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )

    alt_names: list[x509.GeneralName] = []
    for name in dns_names or ["localhost"]:
        alt_names.append(x509.DNSName(name))
    for raw_ip in ip_addresses or ["127.0.0.1"]:
        alt_names.append(x509.IPAddress(ipaddress.ip_address(raw_ip)))

    now = dt.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1))
        .not_valid_after(now + dt.timedelta(days=max(1, days)))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .sign(key, hashes.SHA256())
    )

    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_file, key_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate local dev TLS PEM material.")
    parser.add_argument("--out-dir", default="deploy/tls/certs")
    parser.add_argument("--cert-name", default="server.crt")
    parser.add_argument("--key-name", default="server.key")
    parser.add_argument("--common-name", default="localhost")
    parser.add_argument("--dns", action="append", default=[])
    parser.add_argument("--ip", action="append", default=[])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    cert_file, key_file = generate_self_signed_cert(
        cert_file=out_dir / args.cert_name,
        key_file=out_dir / args.key_name,
        common_name=args.common_name,
        dns_names=args.dns or ["localhost"],
        ip_addresses=args.ip or ["127.0.0.1"],
        days=args.days,
        overwrite=args.overwrite,
    )
    print(f"created cert: {cert_file}")
    print(f"created key:  {key_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
