from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.pagination import DefaultPagination
from apps.rbac.permissions import require_permission

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditPagination(DefaultPagination):
    ordering = "-occurred_at"


class AuditEventListView(generics.ListAPIView):
    queryset = AuditEvent.objects.all()
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated, require_permission("audit.view")]
    pagination_class = AuditPagination
    filterset_fields = ["action", "actor_id", "target_type", "target_id"]
    search_fields = ["action", "target_type", "target_id"]
    ordering_fields = ["occurred_at", "action"]
    actor_names: dict = {}

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        wanted = {event.actor_id for event in page if event.actor_id}
        self.actor_names = {
            user.pk: user.full_name or user.email
            for user in get_user_model().objects.filter(pk__in=wanted)
        }
        return page

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "actor_names": self.actor_names}
