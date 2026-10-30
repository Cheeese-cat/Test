from django.db import models

from apps.users.models import User


class AnalysisJob(models.Model):
    """一次源码分析任务。"""

    STATUS_CHOICES = [
        ('running', '分析中'),
        ('done', '已完成'),
        ('failed', '失败'),
    ]

    project_path = models.CharField(max_length=500, verbose_name='项目路径')
    framework = models.CharField(max_length=50, blank=True, default='', verbose_name='识别框架')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    endpoints = models.JSONField(default=list, blank=True, verbose_name='接口列表')
    stats = models.JSONField(default=dict, blank=True, verbose_name='统计信息')
    mode = models.CharField(max_length=20, default='rule', verbose_name='生成方式')
    error = models.TextField(blank=True, default='', verbose_name='错误信息')
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sa_analysis_job'
        ordering = ['-created_at']

    def __str__(self):
        return '%s (%s)' % (self.project_path, self.status)


class GeneratedCase(models.Model):
    """由源码分析生成的测试用例（导入前暂存）。"""

    SCENE_CHOICES = [
        ('normal', '正常'),
        ('boundary', '边界'),
        ('exception', '异常'),
        ('auth', '权限'),
    ]

    job = models.ForeignKey(AnalysisJob, on_delete=models.CASCADE, related_name='cases')
    module = models.CharField(max_length=100, blank=True, default='')
    method = models.CharField(max_length=10, blank=True, default='')
    path = models.CharField(max_length=300, blank=True, default='')
    title = models.CharField(max_length=300)
    scene = models.CharField(max_length=20, choices=SCENE_CHOICES, default='normal')
    priority = models.CharField(max_length=5, default='P2')
    preconditions = models.TextField(blank=True, default='')
    steps = models.TextField(blank=True, default='')
    expected = models.TextField(blank=True, default='')
    imported = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sa_generated_case'
        ordering = ['id']

    def __str__(self):
        return self.title
