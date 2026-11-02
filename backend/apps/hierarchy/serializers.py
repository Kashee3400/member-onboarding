from rest_framework import serializers

from apps.organizations.models import Membership

from .models import (
    Bmc,
    Mcc,
    MccAssignment,
    Mpp,
    MppAssignment,
    Plant,
    Responsibility,
    Route,
)


def _person(membership) -> dict:
    user = membership.user
    return {
        "name": user.full_name or user.email,
        "roles": sorted(link.role.name for link in membership.role_links.all()),
    }


class CodeUniqueMixin:
    """The unique constraint includes the organization, which clients never send."""

    def validate_code(self, value):
        queryset = self.Meta.model.objects.filter(code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("This code already exists.")
        return value


class PlantSerializer(CodeUniqueMixin, serializers.ModelSerializer):
    class Meta:
        model = Plant
        fields = ["id", "code", "name", "is_active"]


class MccSerializer(CodeUniqueMixin, serializers.ModelSerializer):
    mpp_count = serializers.SerializerMethodField()
    allotted = serializers.SerializerMethodField()

    class Meta:
        model = Mcc
        fields = ["id", "plant", "code", "name", "is_active", "mpp_count", "allotted"]

    def get_mpp_count(self, mcc) -> int:
        return getattr(mcc, "mpp_count", 0)

    def get_allotted(self, mcc) -> list[dict]:
        held = getattr(mcc, "open_assignments", [])
        return [_person(item.membership) for item in held]


class BmcSerializer(CodeUniqueMixin, serializers.ModelSerializer):
    class Meta:
        model = Bmc
        fields = ["id", "mcc", "code", "name", "is_active"]


class RouteSerializer(CodeUniqueMixin, serializers.ModelSerializer):
    mcc = serializers.UUIDField(source="bmc.mcc_id", read_only=True)

    class Meta:
        model = Route
        fields = ["id", "bmc", "mcc", "code", "name", "is_active"]


def _two_digits(value: str) -> str:
    if value and not (len(value) == 2 and value.isdigit()):
        raise serializers.ValidationError("Use 2 digits, or leave it blank.")
    return value


class MppSerializer(CodeUniqueMixin, serializers.ModelSerializer):
    class Meta:
        model = Mpp
        fields = [
            "id",
            "mcc",
            "route",
            "code",
            "source_code",
            "name",
            "village_code",
            "village_name",
            "state_code",
            "hamlet_code",
            "is_active",
        ]
        # The rule below explains a clash better than the generic unique message.
        validators = []

    def validate_series(self, value):
        return _two_digits(value)

    def validate_segment(self, value):
        return _two_digits(value)

    def validate(self, attrs):
        current = self.instance
        mcc = attrs.get("mcc", current.mcc if current else None)
        route = attrs.get("route", current.route if current else None)
        if route and route.bmc.mcc_id != mcc.id:
            raise serializers.ValidationError({"route": ["This route is under another MCC."]})

        village = attrs.get("village_code", current.village_code if current else "")
        hamlet_code = attrs.get("hamlet_code", current.hamlet_code if current else "")
        queryset = Mpp.objects.filter(village_code=village, hamlet_code=hamlet_code)
        if current:
            queryset = queryset.exclude(pk=current.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                {"village_code": ["This village already has an MPP in this hamlet."]}
            )
        return attrs


class MppAssignmentSerializer(serializers.ModelSerializer):
    person = serializers.CharField(source="membership.user.email", read_only=True)

    class Meta:
        model = MppAssignment
        fields = ["id", "membership", "person", "responsibility", "started_at", "ended_at"]
        read_only_fields = fields


class MccAssignmentSerializer(serializers.ModelSerializer):
    person = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = MccAssignment
        fields = ["id", "membership", "person", "roles", "started_at", "ended_at"]
        read_only_fields = fields

    def get_person(self, assignment) -> str:
        return _person(assignment.membership)["name"]

    def get_roles(self, assignment) -> list[str]:
        return _person(assignment.membership)["roles"]


class AssignMccSerializer(serializers.Serializer):
    membership = serializers.PrimaryKeyRelatedField(
        queryset=Membership.objects.filter(is_active=True)
    )


class AssignMppSerializer(serializers.Serializer):
    membership = serializers.PrimaryKeyRelatedField(
        queryset=Membership.objects.filter(is_active=True)
    )
    responsibility = serializers.ChoiceField(choices=Responsibility.choices)


class MppImportSerializer(serializers.Serializer):
    file = serializers.FileField()


class MppImportProblemSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    problem = serializers.CharField()


class MppImportResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    problems = MppImportProblemSerializer(many=True)
