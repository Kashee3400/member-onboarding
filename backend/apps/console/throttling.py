from rest_framework.throttling import SimpleRateThrottle


class OrganizationRateThrottle(SimpleRateThrottle):
    """
    A ceiling on one organization's requests together, so a runaway app or script in
    one organization cannot slow every other one down. Per-person limits still apply.
    """

    scope = "organization"

    def get_cache_key(self, request, view):
        membership = getattr(request.user, "active_membership", None)
        if membership is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": membership.organization_id}
