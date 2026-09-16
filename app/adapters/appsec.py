"""Read-only SCS 1.0 API; numeric DTO enum values are never guessed.

Classify by documented server-side string filters. No scan uploads, triggers,
status mutations, source snippets or presigned URLs are persisted.
"""
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import UUID
from .sourcecraft import SourceCraft, SourceError

SEVERITIES = ('NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
STATUSES = ('OPEN', 'RESOLVED_FIXED', 'RESOLVED_FP', 'RESOLVED_PROJECT_NOT_AFFECTED',
            'RESOLVED_TOLERABLE', 'RESOLVED_DUPLICATE', 'TRIAGE_IN_PROGRESS',
            'TRIAGED_TP', 'FIX_IN_PROGRESS', 'RESOLVED_AUTOFIXED')
RISK_STATUSES = ('OPEN', 'RESOLVED_TOLERABLE', 'TRIAGE_IN_PROGRESS', 'TRIAGED_TP', 'FIX_IN_PROGRESS')

def scan_time(value, at):
    # The draft omits epoch units. Accept only an unambiguous plausible seconds/ms date.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceError('appsec_scan_time_unknown')
    candidates = [x for x in (value, value / 1000) if 946684800 <= x <= at]
    if len(candidates) != 1:
        raise SourceError('appsec_scan_time_unknown')
    return candidates[0]

class AppSec(SourceCraft):
    def __init__(self, token, cache=None, transport=None, auth_scheme='Bearer'):
        super().__init__(token, cache, transport, service='appsec', auth_scheme=auth_scheme)

    def groups(self, repo_id, scan_id, kind, severities=(), statuses=()):
        params = [('gitRepo',repo_id), ('scanUuid',scan_id), ('scanType',''),
                  ('type',kind), ('description',''), ('file',''), ('rule',''), ('pageSize',50)]
        params += [('severity',s) for s in (severities or ('',))]
        params += [('status',s) for s in (statuses or ('',))]
        cursor = ''; seen_tokens = set(); ids = set(); total = None
        for _ in range(2000):
            page = self.get('/v1/defect-groups', params+[('pageToken',cursor)], cache=False)
            rows, size = page.get('data'), page.get('totalSize')
            if not isinstance(rows,list) or type(size) is not int or size < 0:
                raise SourceError('appsec_schema_mismatch')
            if total is not None and total != size:
                raise SourceError('appsec_changed_during_collection', True)
            total = size
            for row in rows:
                group_id = row.get('uuid')
                if not group_id or group_id in ids:
                    raise SourceError('appsec_duplicate_or_missing_group')
                ids.add(group_id)
                # Deliberately discard codeBlock, filename and all free-form descriptions.
                yield {'id':group_id, 'public_id':row.get('publicId')}
            next_token = page.get('nextPageToken')
            if not next_token:
                if len(ids) != total:
                    raise SourceError('appsec_incomplete_page')
                return
            if next_token in seen_tokens or not rows:
                raise SourceError('appsec_pagination_cycle')
            seen_tokens.add(next_token); cursor = next_token
        raise SourceError('appsec_pagination_budget')

    def collect(self, repo_id, slug, at):
        result = {'source':'SourceCraft AppSec','status':'partial','sast':None,'sca':None,'secrets':None,
                  'diagnostics':{'endpoint':'https://appsec.sourcecraft.tech','engines':{}}}
        # Public repository ID must actually be a UUID, or an internal decimal ID.
        try:
            repo_id = str(repo_id)
            if not repo_id.isdecimal(): UUID(repo_id)
            latest = self.get('/v1/scans/latest', {'gitRepo':repo_id}, cache=False)
            scan_id = str(UUID(latest['uuid']))
            detail = self.get('/v1/scans/'+quote(scan_id,safe=''), {'gitRepo':repo_id}, cache=False)
            if detail.get('uuid') != scan_id or detail.get('status') != 'FINISHED':
                raise SourceError('appsec_scan_not_finished')
            finished = scan_time(detail.get('timeFinished'),at)
            if at-finished > 30*86400: raise SourceError('appsec_scan_stale')
            result['diagnostics'].update(scan_id=scan_id, completed_at=finished, commit=detail.get('commitHash'))
        except (SourceError, ValueError, KeyError) as exc:
            reason = exc.reason if isinstance(exc,SourceError) else 'appsec_repository_or_scan_id_unknown'
            result.update(status='unavailable',reason=reason)
            return result
        for kind,key in [('SAST','sast'),('SCA','sca'),('SECRETS','secrets')]:
            try:
                all_ids = {g['id'] for g in self.groups(repo_id,scan_id,kind)}
                if not all_ids:
                    # FINISHED does not tell us which individual engines actually ran.
                    raise SourceError('appsec_no_engine_coverage_evidence')
                classified = {g['id'] for g in self.groups(repo_id,scan_id,kind,SEVERITIES,STATUSES)}
                if classified != all_ids: raise SourceError('appsec_unknown_classification')
                risks = {g['id'] for g in self.groups(repo_id,scan_id,kind,SEVERITIES,RISK_STATUSES)}
                findings = []; seen = set()
                for severity in SEVERITIES:
                    for group in self.groups(repo_id,scan_id,kind,(severity,),RISK_STATUSES):
                        if group['id'] in seen: raise SourceError('appsec_conflicting_severity')
                        seen.add(group['id'])
                        findings.append({'id':group['id'], 'public_id':group['public_id'],
                                         'severity':'info' if severity=='NONE' else severity.lower(),
                                         'status':'open', 'url':'https://sourcecraft.dev/'+slug})
                if seen != risks or not risks.issubset(all_ids):
                    raise SourceError('appsec_changed_during_collection',True)
                result[key] = {'id':scan_id,'status':'completed','complete':True,
                    'completed_at':datetime.fromtimestamp(finished,timezone.utc).isoformat(),
                    'findings':findings,'url':'https://sourcecraft.dev/'+slug}
                result['diagnostics']['engines'][key] = {'status':'ok','groups':len(all_ids),'open_groups':len(risks)}
            except SourceError as exc:
                result['diagnostics']['engines'][key] = {'status':'unavailable','reason':exc.reason}
        if all(result[k] is not None for k in ('sast','sca','secrets')):result['status']='ok'
        result['reason']='Подробности отсутствующих результатов указаны в диагностике AppSec'
        return result
