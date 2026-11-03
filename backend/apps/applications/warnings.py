"""
Risk hints for reviewers, each tied to the field it concerns. None of them blocks a
form: they point an approver at what is worth a second look. A warning never shows
another member's details; it names another form only to staff who can open it.
"""

import math
import statistics

from django.db.models import F
from django.utils import timezone

from apps.hierarchy.services import accessible_mpps

from . import form
from .models import Application, Member, Status

# Ages outside this range are allowed, but rarely right.
YOUNGEST_USUAL_AGE = form.MINIMUM_MEMBER_AGE
OLDEST_USUAL_AGE = 80

# A good crossbred cow gives about 15 litres a day in a village; 20 is generous for any
# animal here, so more per animal in milk usually means a mistyped figure or a borrowed
# animal count.
MAX_LITRES_PER_ANIMAL = 20

# How far from the MPP's usual spot a form may be filled before it is pointed out, and
# how many earlier forms are needed before that spot is trusted.
FAR_KM = 10
NEARBY_FORMS_NEEDED = 3
NEARBY_FORMS_READ = 200

# A sent form has a number a reviewer can look up; a draft has none.
SENT_FIRST = F("submitted_at").desc(nulls_last=True)


def data_warnings(data: dict, *, on) -> dict[str, str]:
    """What the form's own answers suggest, as of the date `on`."""
    warnings = {}
    applicant = data.get("applicant", {})
    animals = data.get("animals", {})

    applicant_name = str(applicant.get("full_name", "")).strip().lower()
    holder = str(data.get("bank", {}).get("holder_name", "")).strip().lower()
    if applicant_name and holder and applicant_name != holder:
        warnings["bank.holder_name"] = (
            "The applicant's name differs from the name on the bank account."
        )

    born = form._parse_date(applicant.get("date_of_birth"))
    if born:
        age = form.age_on(born, on)
        if age < YOUNGEST_USUAL_AGE:
            warnings["applicant.date_of_birth"] = f"The applicant was {age} when this was sent."
        elif age > OLDEST_USUAL_AGE:
            warnings["applicant.date_of_birth"] = (
                f"The applicant was {age} when this was sent. Check the date of birth."
            )

    production = form._number(animals.get("production_lpd"))
    consumption = form._number(animals.get("consumption_lpd"))
    in_milk = form.computed_totals(data)["total_in_milk"]
    if production is not None and consumption is not None and consumption > production:
        warnings["animals.consumption_lpd"] = "Household consumption is more than production."
    if production and production > 0:
        if in_milk == 0:
            warnings["animals.production_lpd"] = "Milk is entered, but no animal is in milk."
        elif production > in_milk * MAX_LITRES_PER_ANIMAL:
            warnings["animals.production_lpd"] = (
                f"{production:g} litres a day from {in_milk} in milk is over "
                f"{MAX_LITRES_PER_ANIMAL} litres an animal."
            )
    return warnings


def _others(application):
    return Application.objects.exclude(pk=application.pk).exclude(status=Status.DISCARDED)


def _named(other, visible_mpps) -> str:
    """The other form's number, only if this reviewer may open it."""
    if other is None or not other.form_number or other.mpp_id not in visible_mpps:
        return ""
    return f" ({other.form_number})"


def _distance_km(a, b) -> float:
    """Great-circle distance, which is plenty for telling a village from the next town."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(h))


def _position(location) -> tuple[float, float] | None:
    if not isinstance(location, dict):
        return None
    latitude = form._number(location.get("latitude"))
    longitude = form._number(location.get("longitude"))
    if latitude is None or longitude is None:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def _usual_spot(application) -> tuple[float, float] | None:
    """
    Where this MPP's forms are usually filled. MPPs have no coordinates of their own,
    so the median of the others stands in; a median ignores the odd stray reading.
    """
    locations = (
        _others(application)
        .filter(mpp_id=application.mpp_id)
        .order_by("-created_at")
        .values_list("data__location", flat=True)[:NEARBY_FORMS_READ]
    )
    positions = [found for found in map(_position, locations) if found]
    if len(positions) < NEARBY_FORMS_NEEDED:
        return None
    return (
        statistics.median(lat for lat, _ in positions),
        statistics.median(lon for _, lon in positions),
    )


def record_warnings(application, visible_mpps) -> dict[str, str]:
    """What only a look at other forms can tell. `visible_mpps` are the reviewer's MPP ids."""
    warnings = {}
    others = _others(application)

    if application.account_index:
        other = (
            others.filter(account_index=application.account_index)
            .order_by(SENT_FIRST)
            .only("form_number", "mpp_id", "status")
            .first()
        )
        if other:
            approved = other.status == Status.APPROVED
            whose = "an existing member's form" if approved else "another form"
            warnings["bank.account_number"] = (
                f"This bank account is on {whose}{_named(other, visible_mpps)}."
            )

    mobile = str(application.data.get("address", {}).get("mobile") or "").strip()
    if mobile:
        member = (
            Member.objects.filter(mobile=mobile)
            .exclude(application=application)
            .select_related("application")
            .first()
        )
        other = (
            member.application
            if member
            else others.filter(data__address__mobile=mobile)
            .order_by(SENT_FIRST)
            .only("form_number", "mpp_id", "status")
            .first()
        )
        if other:
            whose = "an existing member" if member else "another form"
            warnings["address.mobile"] = (
                f"This mobile number is on {whose}{_named(other, visible_mpps)}."
            )

    here = _position(application.data.get("location"))
    spot = _usual_spot(application) if here else None
    if here and spot:
        distance = _distance_km(here, spot)
        if distance > FAR_KM:
            warnings["location.latitude"] = (
                f"Filled {distance:.0f} km from where this MPP's other forms were filled."
            )
    return warnings


def field_warnings(application, membership=None, permissions=()) -> dict[str, str]:
    """
    {"section.field": message}. Drafts get only what their answers show: they are saved
    every few seconds, and the checks against other forms matter once one is sent.
    """
    sent = application.submitted_at
    on = timezone.localdate(sent) if sent else timezone.localdate()
    warnings = data_warnings(application.data, on=on)
    if application.status == Status.DRAFT:
        return warnings
    visible = (
        set(accessible_mpps(membership, permissions).values_list("id", flat=True))
        if membership
        else set()
    )
    return warnings | record_warnings(application, visible)
