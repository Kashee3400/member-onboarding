from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import exceptions

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SIGNATURE_BYTES = 5 * 1024 * 1024
SIGNATURE_WIDTH = 1200
MAX_PIXELS = 40_000_000
JPEG_QUALITY = 85
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}
UNSUPPORTED = "Upload a JPEG or PNG image."
MAX_PHOTO_BYTES = 2 * 1024 * 1024
PHOTO_SIDE = 512
PHOTO_FORMATS = {**ALLOWED_FORMATS, "WEBP": "image/webp"}


def invalid(message: str):
    return exceptions.ValidationError({"file": [message]})


def open_image(raw: bytes, allowed=ALLOWED_FORMATS, unsupported=UNSUPPORTED) -> Image.Image:
    """Trusts the bytes, never the file name or the type the client claimed."""
    try:
        with Image.open(BytesIO(raw)) as probe:
            kind = probe.format
            width, height = probe.size
            probe.verify()
        if kind not in allowed:
            raise invalid(unsupported)
        if width * height > MAX_PIXELS:
            raise invalid("This image is too large.")
        return Image.open(BytesIO(raw))
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise invalid(unsupported) from exc
    except Image.DecompressionBombError as exc:
        raise invalid("This image is too large.") from exc


def normalize_document(raw: bytes) -> tuple[bytes, str]:
    """Re-encodes the picture, dropping location metadata and anything hidden in the file."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise invalid("Images can be at most 5 MB.")

    image = ImageOps.exif_transpose(open_image(raw))
    output = BytesIO()
    image.convert("RGB").save(output, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return output.getvalue(), "image/jpeg"


def normalize_photo(raw: bytes) -> bytes:
    """A staff photo: a square WebP, with location metadata and anything hidden dropped."""
    if len(raw) > MAX_PHOTO_BYTES:
        raise invalid("A photo can be at most 2 MB.")

    image = ImageOps.exif_transpose(
        open_image(raw, PHOTO_FORMATS, "Upload a JPEG, PNG or WEBP image.")
    )
    square = ImageOps.fit(image.convert("RGB"), (PHOTO_SIDE, PHOTO_SIDE))
    output = BytesIO()
    square.save(output, "WEBP", quality=88)
    return output.getvalue()


def normalize_signature(raw: bytes) -> tuple[bytes, str]:
    """
    A signature for the printed form: a transparent PNG holding only the ink.
    A photo of a signature on paper has its background taken away here, so nobody
    needs an editing app. A PNG that already has a clear background is kept as is.
    """
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise invalid("A signature photo can be at most 5 MB.")

    image = ImageOps.exif_transpose(
        open_image(raw, PHOTO_FORMATS, "Upload a JPEG, PNG or WEBP image.")
    ).convert("RGBA")
    if image.getchannel("A").getextrema()[0] < 250:
        ink = image
    else:
        ink = _lift_ink(image)

    box = ink.getchannel("A").point(lambda alpha: 255 if alpha > 40 else 0).getbbox()
    if box is None:
        raise invalid("No signature found. Sign with a dark pen on plain white paper.")
    left, top, right, bottom = box
    pad = max(4, (right - left) // 40)
    ink = ink.crop(
        (
            max(0, left - pad),
            max(0, top - pad),
            min(ink.width, right + pad),
            min(ink.height, bottom + pad),
        )
    )
    ink.thumbnail((SIGNATURE_WIDTH, SIGNATURE_WIDTH // 2))

    output = BytesIO()
    ink.save(output, "PNG", optimize=True)
    return output.getvalue(), "image/png"


def _lift_ink(image):
    """Paper turns transparent, ink stays, however light or uneven the paper is."""
    gray = ImageOps.grayscale(image)
    # The paper is most of the picture, so the bright end of it is the paper.
    histogram = gray.histogram()
    total = sum(histogram)
    seen, paper = 0, 255
    for level in range(255, -1, -1):
        seen += histogram[level]
        if seen >= total * 0.5:
            paper = level
            break
    if paper < 90:
        raise invalid("The paper is too dark. Sign on white paper, in good light.")

    start = paper - 35
    alpha = gray.point(lambda value: 0 if value >= start else min(255, (start - value) * 4))
    if alpha.getbbox() is None:
        raise invalid("No signature found. Sign with a dark pen on plain white paper.")

    # Ink colour darkened a little, so a faint pen still prints clearly.
    ink = ImageOps.autocontrast(image.convert("RGB"), cutoff=2).point(
        lambda value: int(value * 0.75)
    )
    ink = ink.convert("RGBA")
    ink.putalpha(alpha)
    return ink
