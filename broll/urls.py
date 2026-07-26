from django.urls import path
from broll.views import AnalyzeView, JobListView, JobDetailView, JobDownloadView

urlpatterns = [
    path("analyze/", AnalyzeView.as_view(), name="analyze"),
    path("jobs/", JobListView.as_view(), name="job-list"),
    path("jobs/<uuid:job_id>/", JobDetailView.as_view(), name="job-detail"),
    path("jobs/<uuid:job_id>/download/", JobDownloadView.as_view(), name="job-download"),
]
