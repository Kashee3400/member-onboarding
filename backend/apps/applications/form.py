"""
The membership form, version 1, matching the printed application.

Fields are declared once and served to clients, so the app and the server cannot
disagree about what the form contains. Drafts may be incomplete. `validate_for_submit`
is the single gate into the approval workflow.
"""

import re
from datetime import date

from .form_hindi import FIELD_LABELS, OPTION_LABELS, SECTION_TITLES

FORM_VERSION = 1
MINIMUM_MEMBER_AGE = 18
ANIMAL_TYPES = ("indigenous", "crossbred", "buffalo")
ANIMAL_COUNTS = ("heifer", "dry", "in_milk")

MAX_FAMILY_MEMBERS = 6  # The printed form has six rows.


def _choices(*pairs):
    return [{"value": value, "label": label} for value, label in pairs]


GENDERS = _choices(("male", "Male"), ("female", "Female"), ("other", "Other"))
RELATIONS = _choices(("father", "Father"), ("husband", "Husband"), ("guardian", "Guardian"))
CATEGORIES = _choices(("general", "General"), ("obc", "OBC"), ("sc", "SC"), ("st", "ST"))
FAMILY_STATUS = _choices(("bpl", "BPL"), ("apl", "APL"))
EDUCATION = _choices(
    ("none", "None"),
    ("primary", "Primary"),
    ("8th", "8th"),
    ("10th", "10th"),
    ("12th", "12th"),
    ("graduate", "Graduate"),
    ("postgraduate", "Postgraduate"),
)
FAMILY_RELATIONS = _choices(
    ("husband", "Husband"),
    ("wife", "Wife"),
    ("son", "Son"),
    ("daughter", "Daughter"),
    ("father", "Father"),
    ("mother", "Mother"),
    ("brother", "Brother"),
    ("sister", "Sister"),
    ("other", "Other"),
)


def _field(key, label, kind="text", required=True, **extra):
    return {"key": key, "label": label, "type": kind, "required": required, **extra}


FORM_SCHEMA = {
    "version": FORM_VERSION,
    "sections": [
        {
            "key": "applicant",
            "title": "Applicant",
            "fields": [
                _field("full_name", "Full name"),
                _field("full_name_hi", "Full name in Hindi", required=False),
                _field("relation_type", "Relation", "choice", options=RELATIONS),
                _field("relation_name", "Father / husband name"),
                _field("relation_name_hi", "Father / husband name in Hindi", required=False),
                _field("gender", "Gender", "choice", options=GENDERS),
                _field("date_of_birth", "Date of birth", "date"),
                _field("education", "Education", "choice", options=EDUCATION),
                _field("category", "Category", "choice", options=CATEGORIES),
                _field(
                    "family_status",
                    "Family status",
                    "choice",
                    required=False,
                    options=FAMILY_STATUS,
                ),
                _field("is_shg_member", "Member of a UPSRLM SHG", "boolean", required=False),
            ],
        },
        {
            "key": "address",
            "title": "Address",
            "fields": [
                _field("house_number", "House number", required=False),
                _field("hamlet_name", "Hamlet", required=False),
                _field("hamlet_code", "Hamlet code", required=False),
                _field("post_office", "Post office"),
                _field("tehsil", "Tehsil"),
                _field("district", "District"),
                _field("state", "State"),
                _field("pincode", "PIN code"),
                _field("mobile", "Mobile number"),
                _field("landline", "Landline", required=False),
                _field("email", "Email", required=False),
            ],
        },
        {
            "key": "location",
            "title": "Location",
            "fields": [
                _field("latitude", "Latitude", "decimal"),
                _field("longitude", "Longitude", "decimal"),
            ],
        },
        {
            "key": "animals",
            "title": "Animals and milk",
            "fields": [
                *[
                    _field(f"{animal}_{count}", f"{animal} {count}", "number", required=False)
                    for animal in ANIMAL_TYPES
                    for count in ANIMAL_COUNTS
                ],
                _field("production_lpd", "Milk production (litres per day)", "decimal"),
                _field("consumption_lpd", "Household consumption (litres per day)", "decimal"),
            ],
        },
        {
            "key": "bank",
            "title": "Bank account",
            "fields": [
                _field("holder_name", "Name as per passbook"),
                _field("ifsc", "IFSC"),
                _field("bank_name", "Bank"),
                _field("branch_name", "Branch"),
            ],
        },
        {
            "key": "nominee",
            "title": "Nominee",
            "fields": [
                _field("name", "Nominee name"),
                _field("relation", "Relation with applicant"),
                _field("date_of_birth", "Nominee date of birth", "date"),
                _field("address", "Nominee address"),
                _field("guardian_name", "Guardian name", required=False),
            ],
        },
        {
            "key": "declaration",
            "title": "Declaration",
            "fields": [
                _field("accepted_terms", "Terms read and accepted", "boolean"),
                _field("no_household_member", "No household member is a member", "boolean"),
                _field("not_sahayak_or_employee", "Not a Sahayak, or company employee", "boolean"),
            ],
        },
    ],
}


def _with_hindi(option):
    return {**option, "label_hi": OPTION_LABELS[option["value"]]}


for _section in FORM_SCHEMA["sections"]:
    _section["title_hi"] = SECTION_TITLES[_section["key"]]
    for _field_definition in _section["fields"]:
        _field_definition["label_hi"] = FIELD_LABELS[
            f"{_section['key']}.{_field_definition['key']}"
        ]
        if "options" in _field_definition:
            _field_definition["options"] = [_with_hindi(o) for o in _field_definition["options"]]

FORM_SCHEMA["family"] = {
    "max_members": MAX_FAMILY_MEMBERS,
    "genders": [_with_hindi(option) for option in GENDERS],
    "relations": [_with_hindi(option) for option in FAMILY_RELATIONS],
}

_SECTION_KEYS = {section["key"] for section in FORM_SCHEMA["sections"]} | {"family"}

_AADHAAR = re.compile(r"^[2-9]\d{11}$")
_MOBILE = re.compile(r"^[6-9]\d{9}$")
_PINCODE = re.compile(r"^[1-9]\d{5}$")
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_ACCOUNT = re.compile(r"^\d{9,18}$")

# Verhoeff tables, the checksum printed into every Aadhaar number.
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def is_valid_aadhaar(number: str) -> bool:
    if not _AADHAAR.match(number):
        return False
    checksum = 0
    for position, digit in enumerate(reversed(number)):
        checksum = _D[checksum][_P[position % 8][int(digit)]]
    return checksum == 0


def is_valid_account(number: str) -> bool:
    return bool(_ACCOUNT.match(number))


def age_on(born: date, today: date) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except TypeError, ValueError:
        return None


def _number(value):
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def clean_draft(data: dict) -> dict:
    """Drafts accept anything shaped like the form, so unknown sections are dropped."""
    return {key: value for key, value in data.items() if key in _SECTION_KEYS}


def computed_totals(data: dict) -> dict:
    """Derived on the server, so the printed totals can never disagree with the counts."""
    animals = data.get("animals", {})
    count = lambda animal, kind: int(_number(animals.get(f"{animal}_{kind}")) or 0)  # noqa: E731
    production = _number(animals.get("production_lpd")) or 0
    consumption = _number(animals.get("consumption_lpd")) or 0
    return {
        "total_animals": sum(count(a, c) for a in ANIMAL_TYPES for c in ANIMAL_COUNTS),
        "total_in_milk": sum(count(a, "in_milk") for a in ANIMAL_TYPES),
        "surplus_lpd": round(production - consumption, 2),
    }


def validate_for_submit(data: dict, *, has_aadhaar: bool, has_account: bool, today: date) -> dict:
    """Returns {"section.field": message}. Empty means the form may enter approval."""
    errors = {}

    for section in FORM_SCHEMA["sections"]:
        values = data.get(section["key"], {})
        for field in section["fields"]:
            value = values.get(field["key"])
            path = f"{section['key']}.{field['key']}"
            if field["required"] and value in (None, "", False):
                errors[path] = "This is required."
            elif (
                value not in (None, "")
                and "options" in field
                and value not in [option["value"] for option in field["options"]]
            ):
                errors[path] = "Choose one of the listed options."

    if not has_aadhaar:
        errors["applicant.aadhaar_number"] = "This is required."
    if not has_account:
        errors["bank.account_number"] = "This is required."

    applicant = data.get("applicant", {})
    address = data.get("address", {})
    bank = data.get("bank", {})
    nominee = data.get("nominee", {})
    animals = data.get("animals", {})

    born = _parse_date(applicant.get("date_of_birth"))
    if applicant.get("date_of_birth") and born is None:
        errors["applicant.date_of_birth"] = "Enter a valid date."
    elif born and age_on(born, today) < MINIMUM_MEMBER_AGE:
        errors["applicant.date_of_birth"] = f"The applicant must be {MINIMUM_MEMBER_AGE} or older."

    if address.get("mobile") and not _MOBILE.match(str(address["mobile"])):
        errors["address.mobile"] = "Enter a 10-digit mobile number."
    if address.get("pincode") and not _PINCODE.match(str(address["pincode"])):
        errors["address.pincode"] = "Enter a 6-digit PIN code."
    if bank.get("ifsc") and not _IFSC.match(str(bank["ifsc"])):
        errors["bank.ifsc"] = "Enter a valid IFSC."

    totals = computed_totals(data)
    if totals["total_animals"] == 0:
        errors["animals.indigenous_heifer"] = "Enter at least one animal."
    production = _number(animals.get("production_lpd"))
    consumption = _number(animals.get("consumption_lpd"))
    if production is not None and production <= 0:
        errors["animals.production_lpd"] = "Enter the daily production."
    if production is not None and consumption is not None and consumption > production:
        errors["animals.consumption_lpd"] = "Consumption cannot exceed production."

    nominee_born = _parse_date(nominee.get("date_of_birth"))
    if nominee.get("date_of_birth") and nominee_born is None:
        errors["nominee.date_of_birth"] = "Enter a valid date."
    elif nominee_born:
        is_minor = age_on(nominee_born, today) < MINIMUM_MEMBER_AGE
        if is_minor and not nominee.get("guardian_name"):
            errors["nominee.guardian_name"] = "A minor nominee needs a guardian."
        if not is_minor and nominee.get("guardian_name"):
            errors["nominee.guardian_name"] = "An adult nominee has no guardian."

    latitude = _number(data.get("location", {}).get("latitude"))
    longitude = _number(data.get("location", {}).get("longitude"))
    if latitude is not None and not -90 <= latitude <= 90:
        errors["location.latitude"] = "Enter a valid latitude."
    if longitude is not None and not -180 <= longitude <= 180:
        errors["location.longitude"] = "Enter a valid longitude."

    errors |= _family_errors(data.get("family", []))
    return errors


def _family_errors(family) -> dict:
    if not isinstance(family, list):
        return {"family": "Enter the family as a list."}
    if len(family) > MAX_FAMILY_MEMBERS:
        return {"family": f"The form has room for {MAX_FAMILY_MEMBERS} family members."}

    errors = {}
    genders = {option["value"] for option in GENDERS}
    relations = {option["value"] for option in FAMILY_RELATIONS}
    for position, person in enumerate(family):
        age = _number(person.get("age")) if isinstance(person, dict) else None
        if not isinstance(person, dict) or not str(person.get("name", "")).strip():
            errors[f"family.{position}.name"] = "Enter a name."
            continue
        if person.get("gender") not in genders:
            errors[f"family.{position}.gender"] = "Choose a gender."
        if age is None or not 0 <= age <= 120:
            errors[f"family.{position}.age"] = "Enter an age."
        if person.get("relation") not in relations:
            errors[f"family.{position}.relation"] = "Choose a relation."
    return errors


def name_warnings(data: dict) -> list[str]:
    """Worth an approver's attention, but not grounds to block a submission."""
    applicant = str(data.get("applicant", {}).get("full_name", "")).strip().lower()
    holder = str(data.get("bank", {}).get("holder_name", "")).strip().lower()
    if applicant and holder and applicant != holder:
        return ["The applicant's name differs from the name on the bank account."]
    return []
