"""Fail CI if the pinned official contract no longer matches adapter assumptions."""
import json
from pathlib import Path
s=json.loads((Path(__file__).resolve().parents[1]/'contracts/sourcecraft.swagger.json').read_text())
expected={
 '/repos':'DiscoverRepositoriesResponse',
 '/repos/{org_slug}/{repo_slug}':'Repository',
 '/orgs/{org_slug}/repos':'ListOrganizationRepositoriesResponse',
 '/repos/{org_slug}/{repo_slug}/trees':'ListTreeResponse',
 '/repos/{org_slug}/{repo_slug}/cicd/runs':'ListRunsResponse',
 '/repos/{org_slug}/{repo_slug}/issues':'ListRepositoryIssuesResponse',
 '/repos/{org_slug}/{repo_slug}/pulls':'ListRepositoryPullRequestsResponse',
 '/repos/{org_slug}/{repo_slug}/issues/{issue_slug}/comments':'ListIssueCommentsResponse',
 '/repos/{org_slug}/{repo_slug}/issues/{issue_slug}/issue_links':'ListLinksResponse',
}
for path,response in expected.items():
    assert s['paths'][path]['get']['responses']['200']['schema']['$ref']=='#/definitions/'+response
for field in ('trees','next_page_token'):assert field in s['definitions']['ListTreeResponse']['properties']
assert 'cancelled' in s['definitions']['StatusType']['enum']
a=json.loads((Path(__file__).resolve().parents[1]/'contracts/appsec.openapi.json').read_text())
for path in ('/v1/scans/latest','/v1/scans/{scanUuid}','/v1/defect-groups'):
    assert 'get' in a['paths'][path]
assert a['components']['schemas']['ScanDetailsDto']['properties']['status']['$ref'].endswith('/ScanStatus')
assert 'FINISHED' in a['components']['schemas']['ScanStatus']['enum']
print(f'Contract OK: {len(expected)} SourceCraft operations and 3 Security API operations.')
