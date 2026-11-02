from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Numbered pages with a total, so a table can show its size and jump to a page."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 5000
    ordering = "-created_at"

    def paginate_queryset(self, queryset, request, view=None):
        chosen = queryset.query.order_by or (self.ordering,)
        # Equal sort values would otherwise let a row repeat or vanish between pages.
        return super().paginate_queryset(queryset.order_by(*chosen, "-pk"), request, view)
