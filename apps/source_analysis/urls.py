from django.urls import path

from .views import AnalyzeView, ImportView, JobDetailView, JobListView

urlpatterns = [
    path('analyze/', AnalyzeView.as_view(), name='source-analyze'),
    path('jobs/', JobListView.as_view(), name='source-jobs'),
    path('jobs/<int:pk>/', JobDetailView.as_view(), name='source-job-detail'),
    path('jobs/<int:pk>/import/', ImportView.as_view(), name='source-job-import'),
]
