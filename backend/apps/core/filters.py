from rest_framework.filters import OrderingFilter, SearchFilter


class TableSearch(SearchFilter):
    """`?q=`, only offered by views that name `search_fields`."""

    def get_schema_operation_parameters(self, view):
        return super().get_schema_operation_parameters(view) if self._searchable(view) else []

    @staticmethod
    def _searchable(view) -> bool:
        return bool(getattr(view, "search_fields", None))


class TableOrdering(OrderingFilter):
    """
    `?ordering=name` or `-name`. Only what a view lists in `ordering_fields` is
    accepted, so a client cannot sort by a field it may not read. A dict maps
    public names to database paths.
    """

    def get_valid_fields(self, queryset, view, context=None):
        return [(name, name) for name in getattr(view, "ordering_fields", None) or ()]

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)
        if not ordering:
            return queryset
        fields = getattr(view, "ordering_fields", None) or ()
        paths = fields if isinstance(fields, dict) else {name: name for name in fields}
        return queryset.order_by(
            *(
                f"-{paths[name.removeprefix('-')]}" if name.startswith("-") else paths[name]
                for name in ordering
            )
        )

    def get_schema_operation_parameters(self, view):
        if not getattr(view, "ordering_fields", None):
            return []
        return super().get_schema_operation_parameters(view)
