"""
The membership form, version 1, matching the printed application.

Fields are declared once and served to clients, so the app and the server cannot
disagree about what the form contains. Drafts may be incomplete. `validate_for_submit`
is the single gate into the approval workflow.
"""

import copy
import re
from datetime import date

from .form_hindi import FIELD_LABELS, OPTION_LABELS, SECTION_TITLES

FORM_VERSION = 1
MINIMUM_MEMBER_AGE = 18
# Older than this is almost surely a mistyped year, so the form is stopped to check it.
MAXIMUM_MEMBER_AGE = 100
ANIMAL_TYPES = ("indigenous", "crossbred", "buffalo")
ANIMAL_COUNTS = ("heifer", "dry", "in_milk")

MAX_FAMILY_MEMBERS = 6  # The printed form has six rows.


def _choices(*pairs):
    return [{"value": value, "label": label} for value, label in pairs]


GENDERS = _choices(("male", "Male"), ("female", "Female"), ("other", "Other"))
RELATIONS = _choices(("father", "Father"), ("husband", "Husband"), ("guardian", "Guardian"))
CATEGORIES = _choices(("general", "General"), ("obc", "OBC"), ("sc", "SC"), ("st", "ST"))
FAMILY_STATUS = _choices(("bpl", "BPL"), ("apl", "APL"))
# How the facilitator collects the member fee. Online opens once a gateway is set up.
PAYMENT_MODES = _choices(("cash", "Cash"), ("online", "Online"))
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

# --- Option lists -------------------------------------------------------------------
# The values above are what each organization starts with. From then on it keeps its
# own lists (see form_lists.py); a field names its list with `option_list`.
OPTION_LISTS = {
    "gender": GENDERS,
    "relation_type": RELATIONS,
    "education": EDUCATION,
    "category": CATEGORIES,
    "family_status": FAMILY_STATUS,
    "family_relation": FAMILY_RELATIONS,
    "nominee_relation": FAMILY_RELATIONS,
    "payment_mode": PAYMENT_MODES,
}
DEFAULT_CHOICES = {key: {o["value"] for o in options} for key, options in OPTION_LISTS.items()}
# ------------------------------------------------------------------------------------


def _field(key, label, kind="text", required=True, **extra):
    return {"key": key, "label": label, "type": kind, "required": required, **extra}


# Locked: the server copies these from the MPP whenever the MPP knows them.
FROM_MPP = {"locked": True, "source": "mpp"}

# Served with the fields that use them, so the app checks while typing by the same rules.
MOBILE_PATTERN = r"^[6-9]\d{9}$"
PINCODE_PATTERN = r"^[1-9]\d{5}$"
IFSC_PATTERN = r"^[A-Z]{4}0[A-Z0-9]{6}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _choice(key, label, option_list, required=True):
    options = OPTION_LISTS[option_list]
    return _field(key, label, "choice", required, options=options, option_list=option_list)


FORM_SCHEMA = {
    "version": FORM_VERSION,
    "sections": [
        {
            "key": "applicant",
            "title": "Applicant",
            "fields": [
                _field("full_name", "Full name"),
                _choice("relation_type", "Relation", "relation_type"),
                _field("relation_name", "Father / husband name"),
                _choice("gender", "Gender", "gender"),
                _field(
                    "date_of_birth",
                    "Date of birth",
                    "date",
                    min_age=MINIMUM_MEMBER_AGE,
                    max_age=MAXIMUM_MEMBER_AGE,
                ),
                _choice("education", "Education", "education"),
                _choice("category", "Category", "category"),
                _choice("family_status", "Family status", "family_status", required=False),
                _field("is_shg_member", "Member of a UPSRLM SHG", "boolean", required=False),
            ],
        },
        {
            "key": "address",
            "title": "Address",
            "fields": [
                _field("house_number", "House number", required=False),
                # Place fields: filled from the MPP, which the client cannot override.
                _field("pooling_point_code", "Pooling point code", required=False, **FROM_MPP),
                _field("village_name", "Revenue village", required=False, **FROM_MPP),
                _field("village_code", "Revenue village code", required=False, **FROM_MPP),
                _field("hamlet_name", "Hamlet", required=False, **FROM_MPP),
                _field("hamlet_code", "Hamlet code", required=False, **FROM_MPP),
                _field("post_office", "Post office", **FROM_MPP),
                _field("tehsil", "Tehsil", **FROM_MPP),
                _field("district", "District", **FROM_MPP),
                _field("state", "State", **FROM_MPP),
                _field("pincode", "PIN code", pattern=PINCODE_PATTERN, **FROM_MPP),
                _field("mobile", "Mobile number", pattern=MOBILE_PATTERN),
                _field("landline", "Landline", required=False),
                _field("email", "Email", pattern=EMAIL_PATTERN),
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
                _field("ifsc", "IFSC", pattern=IFSC_PATTERN),
                _field("bank_name", "Bank"),
                _field("branch_name", "Branch"),
            ],
        },
        {
            "key": "nominee",
            "title": "Nominee",
            "fields": [
                _field("name", "Nominee name"),
                _choice("relation", "Relation with applicant", "nominee_relation"),
                _field(
                    "date_of_birth", "Nominee date of birth", "date", adult_age=MINIMUM_MEMBER_AGE
                ),
                _field("address", "Nominee address"),
                _field("guardian_name", "Guardian name", required=False),
            ],
        },
        {
            # Collected in the village, before the member signs. Finance records the deposit.
            "key": "fee",
            "title": "Member fee",
            "fields": [
                _choice("payment_mode", "Payment mode", "payment_mode"),
                _field("amount_received", "Amount received", "number"),
                _field("transaction_id", "Transaction ID", required=False),
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

# (section, field, list) for every choice on the form; the household rows use two more.
CHOICE_FIELDS = tuple(
    (section["key"], field["key"], field["option_list"])
    for section in FORM_SCHEMA["sections"]
    for field in section["fields"]
    if "option_list" in field
)
FAMILY_CHOICES = (("gender", "gender"), ("relation", "family_relation"))


def _split(options):
    shown = lambda o: {k: o[k] for k in ("value", "label", "label_hi")}  # noqa: E731
    return (
        [shown(o) for o in options if o["active"]],
        [shown(o) for o in options if not o["active"]],
    )


def schema_with(lists: dict[str, list[dict]]) -> dict:
    """
    The form with an organization's own lists. Retired choices travel separately, so
    old answers still read correctly while no one can pick them again.
    """
    schema = copy.deepcopy(FORM_SCHEMA)
    for section in schema["sections"]:
        for field in section["fields"]:
            if "option_list" in field:
                field["options"], field["retired_options"] = _split(lists[field["option_list"]])
    family = schema["family"]
    family["genders"], family["retired_genders"] = _split(lists["gender"])
    family["relations"], family["retired_relations"] = _split(lists["family_relation"])
    return schema


def _allowed(value, option_list, choices, kept) -> bool:
    """An active choice, or one already on the form before it was retired."""
    if value in (None, ""):
        return True
    return isinstance(value, str) and (value in choices[option_list] or value in kept)


_AADHAAR = re.compile(r"^[2-9]\d{11}$")
_MOBILE = re.compile(MOBILE_PATTERN)
_PINCODE = re.compile(PINCODE_PATTERN)
_IFSC = re.compile(IFSC_PATTERN)
_EMAIL = re.compile(EMAIL_PATTERN)
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


def _kept_choices(data: dict | None, section: str, key: str) -> set:
    if not data:
        return set()
    if section == "family":
        family = data.get("family")
        people = family if isinstance(family, list) else []
        found = [person.get(key) for person in people if isinstance(person, dict)]
    else:
        values = data.get(section)
        found = [values.get(key)] if isinstance(values, dict) else []
    return {value for value in found if isinstance(value, str) and value}


def clean_draft(data: dict, *, saved: dict | None = None, choices=None) -> dict:
    """
    Drafts accept anything shaped like the form, so unknown sections are dropped. A
    choice that is not in its list is cleared, unless the form already held it.
    """
    choices = choices or DEFAULT_CHOICES
    cleaned = {key: value for key, value in data.items() if key in _SECTION_KEYS}
    for section, key, option_list in CHOICE_FIELDS:
        values = cleaned.get(section)
        if isinstance(values, dict) and not _allowed(
            values.get(key), option_list, choices, _kept_choices(saved, section, key)
        ):
            cleaned[section] = {**values, key: ""}
    if isinstance(cleaned.get("family"), list):
        cleaned["family"] = [
            {
                **person,
                **{
                    key: ""
                    for key, option_list in FAMILY_CHOICES
                    if not _allowed(
                        person.get(key),
                        option_list,
                        choices,
                        _kept_choices(saved, "family", key),
                    )
                },
            }
            if isinstance(person, dict)
            else person
            for person in cleaned["family"]
        ]
    return cleaned


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


def validate_for_submit(
    data: dict,
    *,
    has_aadhaar: bool,
    has_account: bool,
    today: date,
    choices=None,
    previous: dict | None = None,
) -> dict:
    """
    Returns {"section.field": message}. Empty means the form may enter approval.
    `choices` holds each list's active values; `previous` is the last submission,
    whose choices stay acceptable after they are retired.
    """
    errors = {}
    choices = choices or DEFAULT_CHOICES

    for section in FORM_SCHEMA["sections"]:
        values = data.get(section["key"], {})
        for field in section["fields"]:
            value = values.get(field["key"])
            path = f"{section['key']}.{field['key']}"
            if field["required"] and value in (None, "", False):
                errors[path] = "This is required."
            elif "option_list" in field and not _allowed(
                value,
                field["option_list"],
                choices,
                _kept_choices(previous, section["key"], field["key"]),
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
    elif born and age_on(born, today) > MAXIMUM_MEMBER_AGE:
        errors["applicant.date_of_birth"] = (
            f"Check the date of birth: that is over {MAXIMUM_MEMBER_AGE} years old."
        )

    if address.get("mobile") and not _MOBILE.match(str(address["mobile"])):
        errors["address.mobile"] = "Enter a 10-digit mobile number."
    if address.get("pincode") and not _PINCODE.match(str(address["pincode"])):
        errors["address.pincode"] = "Enter a 6-digit PIN code."
    if bank.get("ifsc") and not _IFSC.match(str(bank["ifsc"])):
        errors["bank.ifsc"] = "Enter a valid IFSC."
    if address.get("email") and not _EMAIL.match(str(address["email"]).strip()):
        errors["address.email"] = "Enter a valid email."

    totals = computed_totals(data)
    if totals["total_animals"] == 0:
        errors["animals.indigenous_heifer"] = "Enter at least one animal."
    production = _number(animals.get("production_lpd"))
    consumption = _number(animals.get("consumption_lpd"))
    if production is not None and production <= 0:
        errors["animals.production_lpd"] = "Enter the daily production."
    for key, amount in (("production_lpd", production), ("consumption_lpd", consumption)):
        if amount is None and animals.get(key) not in (None, ""):
            errors[f"animals.{key}"] = "Enter a number."
    if consumption is not None and consumption < 0:
        errors["animals.consumption_lpd"] = "Enter the daily consumption."
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

    errors |= _family_errors(data.get("family", []), choices, previous)
    return errors


def _family_errors(family, choices=None, previous=None) -> dict:
    if not isinstance(family, list):
        return {"family": "Enter the family as a list."}
    if len(family) > MAX_FAMILY_MEMBERS:
        return {"family": f"The form has room for {MAX_FAMILY_MEMBERS} family members."}

    errors = {}
    choices = choices or DEFAULT_CHOICES
    genders = choices["gender"] | _kept_choices(previous, "family", "gender")
    relations = choices["family_relation"] | _kept_choices(previous, "family", "relation")
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
