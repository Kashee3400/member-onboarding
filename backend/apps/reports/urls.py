from django.urls import path

from .views import (
    PdfBatchCancelView,
    PdfBatchDetailView,
    PdfBatchFileView,
    PdfBatchListView,
    PdfBatchRetryView,
    PdfBatchZipView,
    PdfPreviewView,
    ReportExportView,
    ReportSummaryView,
)

urlpatterns = [
    path("summary/", ReportSummaryView.as_view(), name="report-summary"),
    path("export/", ReportExportView.as_view(), name="report-export"),
    path("pdf-batches/", PdfBatchListView.as_view(), name="pdf-batch-list"),
    path("pdf-batches/preview/", PdfPreviewView.as_view(), name="pdf-batch-preview"),
    path("pdf-batches/<uuid:pk>/", PdfBatchDetailView.as_view(), name="pdf-batch-detail"),
    path("pdf-batches/<uuid:pk>/cancel/", PdfBatchCancelView.as_view(), name="pdf-batch-cancel"),
    path("pdf-batches/<uuid:pk>/retry/", PdfBatchRetryView.as_view(), name="pdf-batch-retry"),
    path("pdf-batches/<uuid:pk>/zip/", PdfBatchZipView.as_view(), name="pdf-batch-zip"),
    path("pdf-batches/<uuid:pk>/file/", PdfBatchFileView.as_view(), name="pdf-batch-file"),
]
