from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.plumbing import build_bearer_security_scheme_object


class OrganizationJWTScheme(OpenApiAuthenticationExtension):
    target_class = "apps.organizations.authentication.OrganizationJWTAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return build_bearer_security_scheme_object("Authorization", "Bearer", "JWT")
