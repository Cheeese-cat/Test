import os

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project
from apps.testcases.models import TestCase

from .analyzer import analyze
from .generator import generate
from .models import AnalysisJob, GeneratedCase

PRIORITY_MAP = {'P0': 'critical', 'P1': 'high', 'P2': 'medium', 'P3': 'low'}


def _job_payload(job, with_cases=True):
    data = {
        'id': job.id,
        'project_path': job.project_path,
        'framework': job.framework,
        'status': job.status,
        'mode': job.mode,
        'stats': job.stats,
        'error': job.error,
        'created_at': job.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'endpoints': job.endpoints,
    }
    if with_cases:
        data['cases'] = [{
            'id': c.id,
            'module': c.module,
            'method': c.method,
            'path': c.path,
            'title': c.title,
            'scene': c.scene,
            'priority': c.priority,
            'preconditions': c.preconditions,
            'steps': c.steps,
            'expected': c.expected,
            'imported': c.imported,
        } for c in job.cases.all()]
    return data


class AnalyzeView(APIView):
    """输入本地项目路径，静态解析并生成用例。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        path = str(request.data.get('path', '')).strip().strip('"')
        if not path:
            return Response({'error': '请填写项目路径'}, status=status.HTTP_400_BAD_REQUEST)
        if not os.path.isdir(path):
            return Response({'error': '目录不存在：%s' % path}, status=status.HTTP_400_BAD_REQUEST)

        job = AnalysisJob.objects.create(project_path=path, created_by=request.user)
        try:
            analysis = analyze(path)
            job.framework = analysis['framework']
            job.endpoints = analysis['endpoints']
            cases, mode = generate(analysis)
            job.mode = mode

            GeneratedCase.objects.bulk_create([
                GeneratedCase(
                    job=job,
                    module=c.get('module', '')[:100],
                    method=c.get('method', '')[:10],
                    path=c.get('path', '')[:300],
                    title=c.get('title', '未命名用例')[:300],
                    scene=c.get('scene', 'normal'),
                    priority=c.get('priority', 'P2'),
                    preconditions=c.get('preconditions', ''),
                    steps=c.get('steps', ''),
                    expected=c.get('expected', ''),
                ) for c in cases
            ])

            job.stats = {
                'file_count': analysis['file_count'],
                'endpoint_count': len(analysis['endpoints']),
                'case_count': len(cases),
                'table_count': len(analysis['tables']),
                'auth': analysis['auth'],
                'languages': analysis['languages'],
                'tables': analysis['tables'],
            }
            job.status = 'done'
        except Exception as exc:
            job.status = 'failed'
            job.error = str(exc)[:1000]
        job.save()
        return Response(_job_payload(job))


class JobListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        jobs = AnalysisJob.objects.all()[:20]
        return Response([_job_payload(j, with_cases=False) for j in jobs])


class JobDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        job = get_object_or_404(AnalysisJob, pk=pk)
        return Response(_job_payload(job))


class ImportView(APIView):
    """把生成的用例导入到项目（不传 project_id 时自动建一个）。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        job = get_object_or_404(AnalysisJob, pk=pk)
        project_id = request.data.get('project_id')

        if project_id:
            project = get_object_or_404(Project, pk=project_id)
        else:
            name = '源码分析 · %s' % os.path.basename(job.project_path.rstrip('\\/'))[:180]
            project = Project.objects.filter(name=name, owner=request.user).first()
            if not project:
                project = Project.objects.create(
                    name=name,
                    description='由「源码分析生成用例」导出的用例集',
                    owner=request.user,
                )

        created = 0
        for case in job.cases.filter(imported=False):
            TestCase.objects.create(
                project=project,
                title=case.title[:500],
                description='%s %s（%s）' % (case.method, case.path, case.module),
                preconditions=case.preconditions,
                steps=case.steps,
                expected_result=case.expected or '—',
                priority=PRIORITY_MAP.get(case.priority, 'medium'),
                status='draft',
                test_type='api',
                tags=[case.scene],
                author=request.user,
            )
            case.imported = True
            case.save(update_fields=['imported'])
            created += 1

        return Response({'imported': created, 'project_id': project.id, 'project_name': project.name})
