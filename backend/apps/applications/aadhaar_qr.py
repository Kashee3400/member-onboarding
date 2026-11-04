"""
Reading an Aadhaar QR code and proving it came from UIDAI.

The Secure QR (printed since 2018 on letters, PVC cards and e-Aadhaar, and shown
by mAadhaar) is a large decimal number. As bytes it is a gzip stream; unpacked,
its text fields are separated by 0xFF, the holder's photo (JPEG 2000) follows the
last field, and the final 256 bytes are UIDAI's RSA signature over everything
before them. Checking that signature against UIDAI's own published certificates
proves the details are UIDAI's, so nobody has to compare them by eye.

Every certificate UIDAI has signed with is pinned in `aadhaar_certs/`, taken from
uidai.gov.in/en/data-and-download. An old card was signed with the certificate of
its day: its expiry does not make an earlier signature less genuine, so all are
tried. The older XML QR carries no usable signature, so its details count as
scanned, not verified.
"""

import gzip
import re
import zlib
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from html import unescape
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

CERTIFICATES = Path(__file__).parent / "aadhaar_certs"
SIGNATURE_BYTES = 256
HASH_BYTES = 32
DELIMITER = 0xFF

# The Secure QR's text fields, in order. Versioned codes ("V2" and later) start
# with the version and end with the last 4 digits of the mobile.
FIELDS = (
    "email_mobile_status",
    "reference_id",
    "name",
    "date_of_birth",
    "gender",
    "care_of",
    "district",
    "landmark",
    "house",
    "location",
    "pincode",
    "post_office",
    "state",
    "street",
    "subdistrict",
    "village",
)


class Status:
    VERIFIED = "verified"  # UIDAI's signature checks out
    UNSIGNED = "unsigned"  # an older QR with no signature to check
    INVALID = "invalid"  # signed, but not by UIDAI, or altered since


@dataclass
class QrReading:
    status: str
    details: dict = field(default_factory=dict)
    aadhaar_last4: str = ""
    photo: bytes | None = None
    certificate: str = ""


@cache
def _uidai_keys() -> tuple:
    keys = []
    for path in sorted(CERTIFICATES.glob("*.cer")):
        raw = path.read_bytes()
        try:
            certificate = x509.load_pem_x509_certificate(raw)
        except ValueError:
            certificate = x509.load_der_x509_certificate(raw)
        keys.append((path.stem, certificate.public_key()))
    return tuple(keys)


def _signer(signed: bytes, signature: bytes) -> str:
    """The certificate UIDAI signed with, or "" when none of them did."""
    for name, key in _uidai_keys():
        try:
            key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            continue
        return name
    return ""


def _text(value: bytes) -> str:
    return value.decode("iso-8859-1").strip()


def _iso_date(value: str) -> str:
    """Cards print dd-mm-yyyy (or dd/mm/yyyy); some give only the year."""
    if match := re.fullmatch(r"(\d{2})[-/](\d{2})[-/](\d{4})", value):
        day, month, year = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    return value if re.fullmatch(r"\d{4}", value) else ""


def _gender(value: str) -> str:
    return {"F": "female", "M": "male", "T": "other"}.get(value.strip().upper()[:1], "")


def _care_of(value: str) -> tuple[str, str]:
    """ "W/O: Shyam Kushwaha" gives ("husband", "Shyam Kushwaha")."""
    match = re.match(r"^\s*([SDWC])\s*/?\s*O\s*:?\s*(.*)$", value, re.IGNORECASE)
    if not match:
        return "", value.strip()
    relation = {"W": "husband", "S": "father", "D": "father"}.get(match.group(1).upper(), "")
    return relation, match.group(2).strip()


def _details(raw: dict[str, str]) -> dict:
    relation, relation_name = _care_of(raw.get("care_of", ""))
    return {
        "name": raw.get("name", ""),
        "date_of_birth": _iso_date(raw.get("date_of_birth", "")),
        "gender": _gender(raw.get("gender", "")),
        "relation_type": relation,
        "relation_name": relation_name,
        "house": raw.get("house", ""),
        "village": raw.get("village", ""),
        "post_office": raw.get("post_office", ""),
        "subdistrict": raw.get("subdistrict", ""),
        "district": raw.get("district", ""),
        "state": raw.get("state", ""),
        "pincode": raw.get("pincode", ""),
    }


def _read_secure(digits: str) -> QrReading | None:
    try:
        number = int(digits)
        packed = number.to_bytes((number.bit_length() + 7) // 8, "big")
        data = gzip.decompress(packed)
    except ValueError, OSError, EOFError, zlib.error:
        return None
    if len(data) <= SIGNATURE_BYTES:
        return None

    signed, signature = data[:-SIGNATURE_BYTES], data[-SIGNATURE_BYTES:]
    versioned = signed[:1] == b"V"
    names = (("version",) if versioned else ()) + FIELDS + (("mobile_last4",) if versioned else ())
    # Only the text fields are split: the photo after them may hold 0xFF bytes too.
    values, start = [], 0
    for at, byte in enumerate(signed):
        if len(values) == len(names):
            break
        if byte == DELIMITER:
            values.append(signed[start:at])
            start = at + 1
    if len(values) < len(names):
        return None
    raw = dict(zip(names, (_text(value) for value in values), strict=True))

    # Older unversioned codes end with hashes of the email and mobile, before the signature.
    status = raw["email_mobile_status"]
    hashes_after = 0 if versioned else HASH_BYTES * {"0": 0, "1": 1, "2": 1, "3": 2}.get(status, 0)
    photo = signed[start : len(signed) - hashes_after] or None

    certificate = _signer(signed, signature)
    return QrReading(
        status=Status.VERIFIED if certificate else Status.INVALID,
        details=_details(raw),
        # The reference id begins with the last 4 digits of the Aadhaar number.
        aadhaar_last4=raw["reference_id"][:4] if raw["reference_id"][:4].isdigit() else "",
        photo=photo,
        certificate=certificate,
    )


def _read_xml(xml: str) -> QrReading | None:
    # Read with a pattern, not an XML parser: a scanned code is outside input, and
    # attributes are all the old QR has.
    attributes = {
        key.lower(): unescape(value)
        for key, value in re.findall(r'(?<![A-Za-z])([A-Za-z]+)="([^"]*)"', xml[:5000])
    }
    if not attributes.get("name"):
        return None
    uid = re.sub(r"\D", "", attributes.get("uid", ""))
    raw = {
        "name": attributes.get("name", ""),
        "date_of_birth": attributes.get("dob", "") or attributes.get("yob", ""),
        "gender": attributes.get("gender", ""),
        "care_of": attributes.get("co", "") or attributes.get("gname", ""),
        "house": attributes.get("house", ""),
        "village": attributes.get("vtc", ""),
        "post_office": attributes.get("po", ""),
        "subdistrict": attributes.get("subdist", ""),
        "district": attributes.get("dist", ""),
        "state": attributes.get("state", ""),
        "pincode": attributes.get("pc", ""),
    }
    return QrReading(
        status=Status.UNSIGNED,
        details=_details(raw),
        aadhaar_last4=uid[-4:] if len(uid) == 12 else "",
    )


def read(raw: str) -> QrReading | None:
    """What the QR holds and whether UIDAI signed it. None when it is no Aadhaar QR."""
    value = (raw or "").strip()
    if value.startswith("<"):
        return _read_xml(value)
    if value.isdigit():
        return _read_secure(value)
    return None


def scan_image(content: bytes) -> str | None:
    """The Aadhaar QR in a photo of the card, when it can be read."""
    import io

    import zxingcpp
    from PIL import Image, ImageOps

    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert("L")
    except OSError:
        return None
    # A dense code in a phone photo reads better at a moderate size than at full size.
    for size in (None, 2000, 1400):
        candidate = image.copy()
        if size:
            candidate.thumbnail((size, size))
        for result in zxingcpp.read_barcodes(candidate, formats=zxingcpp.BarcodeFormat.QRCode):
            if result.text and read(result.text):
                return result.text
    return None
