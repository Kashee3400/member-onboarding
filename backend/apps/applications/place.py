"""
The address fields an MPP already knows: its village, hamlet, tehsil, district,
state, post office and PIN code. They are copied from the MPP on every save, so
whatever a phone sends for them is ignored. A value the masters do not hold yet is
still typed in, until an administrator fills it in the MPP.
"""

from apps.hierarchy.services import mpp_place

from .form import FORM_SCHEMA

LOCKED_FIELDS = tuple(
    field["key"]
    for section in FORM_SCHEMA["sections"]
    if section["key"] == "address"
    for field in section["fields"]
    if field.get("locked")
)


def locked_values(mpp) -> dict:
    place = mpp_place(mpp)
    return {key: place[key] for key in LOCKED_FIELDS if place.get(key)}


def apply(application) -> None:
    """Overwrites the place fields with the MPP's, in place on the application."""
    values = locked_values(application.mpp)
    if values:
        address = application.data.get("address")
        address = address if isinstance(address, dict) else {}
        application.data = {**application.data, "address": {**address, **values}}
