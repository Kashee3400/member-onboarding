from io import BytesIO

from PIL import Image, ImageOps

from apps.documents.images import invalid, open_image

MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_LOGIN_IMAGE_BYTES = 10 * 1024 * 1024
MAX_LOGO_SIDE = 1024
MAX_LOGIN_IMAGE_SIDE = 2560
WEBP_QUALITY = 85
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
UNSUPPORTED = "Upload a PNG, JPEG or WEBP image."


def _open(raw: bytes) -> Image.Image:
    return ImageOps.exif_transpose(open_image(raw, ALLOWED_FORMATS, UNSUPPORTED))


def normalize_logo(raw: bytes) -> tuple[bytes, str]:
    """Keeps transparency, so a logo sits cleanly on light and dark surfaces."""
    if len(raw) > MAX_LOGO_BYTES:
        raise invalid("A logo can be at most 2 MB.")

    image = _open(raw).convert("RGBA")
    image.thumbnail((MAX_LOGO_SIDE, MAX_LOGO_SIDE))
    output = BytesIO()
    image.save(output, "PNG", optimize=True)
    return output.getvalue(), "image/png"


def normalize_login_image(raw: bytes) -> tuple[bytes, str]:
    if len(raw) > MAX_LOGIN_IMAGE_BYTES:
        raise invalid("A login image can be at most 10 MB.")

    image = _open(raw).convert("RGB")
    image.thumbnail((MAX_LOGIN_IMAGE_SIDE, MAX_LOGIN_IMAGE_SIDE))
    output = BytesIO()
    image.save(output, "WEBP", quality=WEBP_QUALITY)
    return output.getvalue(), "image/webp"
