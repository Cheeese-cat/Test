from django.apps import AppConfig


class SourceAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.source_analysis'
    verbose_name = '源码分析生成用例'
