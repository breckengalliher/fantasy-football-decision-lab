"""Build a bounded certification checkpoint from retained, reviewed evidence."""
import json
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'reports/release-certification-20261009'
fresh = json.loads((DEST / 'fresh-sources.json').read_text())
sources = [
    {'id':'fresh','label':'Read-only provider verification','path':'reports/release-certification-20261009/fresh-sources.json'},
    {'id':'tests','label':'Regression test results','path':'reports/release-certification-20261009/tests.xml'},
    {'id':'browser','label':'Browser checkpoint evidence','path':'reports/release-certification-20261009/browser-checkpoint.json'},
    {'id':'repair','label':'Preserved October 9 repair tracker','path':'reports/football-repair-20261009/repair-tracker.md'},
]
title = 'SDL release certification — October 9 checkpoint'
sections = [
('title', '# '+title, ''),
('summary','## Hold release certification',
 'Local regression and browser smoke checks passed, and one deployment packaging defect was repaired. **This is not a release certificate.** Official per-player injury/depth freshness, precise hosted latency, full authenticated concurrency, and Python 3.12 container execution are still unverified. No production data, saved assignments, projection methodology, hosting plan, or deployment was changed.'),
('scope','## What the measurements mean',
 'Evidence was collected October 9. Regression counts cover the existing local suite. The browser batch consists of ten separate anonymous Streamlit sessions sharing one browser profile, not ten independent accounts or real phones. Ready means the expected Puka/JSN comparison was rendered in the DOM. Provider timings are single read-only retrieval/normalization samples, not percentiles, official report age, or user-interface latency.'),
('tests','## Local regressions pass; packaging now includes identity data',
 '230 tests passed in 7.88 seconds, with two pre-existing Pandas future warnings. Initial test attempts failed because of sandbox temporary-directory permissions and Windows path length; the same suite passed with a shorter writable temporary directory. The Dockerfile previously omitted data/external/player_identity_crosswalk.csv. Added its COPY instruction and a permanent packaging regression. Docker is unavailable locally; this is not a completed container build.'),
('browser','## Mobile roster restoration and comparison smoke checks pass',
 'The restarted local server restored the existing sign-in and disposable QA team: seven starters, two occupied bench slots, six-point passing TD scoring. No saved assignments were mutated. At 390 × 844, the Command Center had no document horizontal overflow and no broken roster images. Player fantasy details/game log opened; onboarding dismissal worked; smart search matched Puka and Jaxon, and adding them produced the expected 0.6-PPR close call. Analysis Hub stayed open when switching from Projection to Matchup. Desktop was inspected at 1366 × 768. This does not certify physical iOS/Android, account recovery, multi-account isolation, or a newly edited roster surviving a next-day visit.'),
('fresh','## Source access succeeds; official freshness remains a gate',
 'NFLverse returned 346 Week 5 injury rows, but no date/time fields. Sleeper returned 329 normalized recent status records. SportsDataIO returned 30 team-game rows and 1,866 depth rows; depth normalization has no report timestamp. Retrieval success must not be interpreted as confirmed current official availability. The local dashboard correctly displayed VERIFY DATA for stale essential context. Provider checks wrote evidence only, never published app snapshots.'),
('chart-note','## Provider retrieval duration',
 'The bars show seconds for one source-check operation each. The SportsDataIO operation includes three existing endpoints; the others include one. All completed quickly in this sample, but they are not like-for-like provider performance rankings. Additional endpoint probing was omitted to avoid unnecessary API usage. No latency percentile is inferred.'),
('hosting','## Ten hosted browser sessions rendered; speed targets remain unproven',
 'All ten concurrent hosted browser tabs rendered the expected comparison without visible tracebacks. Tab creation took 11.53 seconds; all were observed ready by 26.16 seconds from batch start. These are orchestration upper bounds with tool overhead and observation gaps—not per-user page-load times. The preliminary raw-protocol harness timed out locally and remotely, so its timeouts are explicitly invalid as website benchmarks. It requires browser-component handshake support before certification use. Render confirmed one 0.5-CPU/512-MB service. Dashboard charts visually showed memory around 75% (~384 MB) and CPU near 0–5% of allocation; these are graph estimates, not exported exact peaks. Response-time percentiles are Pro-gated; no upgrade was made. Dashboard collection lag prevents attributing exact peaks to this short batch.'),
('model','## Approved forecasting and uncertainty remain intact',
 'No model inputs, weights, scoring rules, ranges, or historical metrics were changed during this checkpoint. The preserved repair tracker still identifies three inverted negative-forecast intervals requiring an approved range policy or explicit publication quarantine. Passing tests does not establish improved forecasting accuracy. Prior 2025 benchmark results are retained, not newly retested against new outcomes.'),
('next','## Required work before certification and deployment approval',
 '1. Validate a Python 3.12 production container including the crosswalk.\n2. Resolve the documented range-policy/publication gate without changing methodology silently.\n3. Establish timestamped official injury/inactive and depth evidence; recheck stale-data behavior with that source.\n4. Finish the complete disposable-team edit → save → close → reopen journey, scoring changes, compare/return, and authorization checks.\n5. Measure repeated browser-ready and interaction timings plus exact Render resource samples; test independent authenticated sessions and real mobile browsers.\n6. Request deployment approval only after the gates pass.\n\nFurther questions: Can the existing providers supply official report timestamps? Which approved interval/publication policy should control the remaining negative backup forecasts? Render Starter remains a candidate, not a proven ten-account capacity guarantee.'),
]
blocks = [{'id':i,'type':'markdown','body':h+'\n\n'+body} for i,h,body in sections]
blocks.insert(7, {'id':'provider-duration','type':'chart','chartId':'durations'})
rows = [{'source':name,'seconds':value['seconds'],'status':value['status'],
         'checked_at':fresh['checked_at'],'official_freshness_confirmed':False,
         'endpoint_count':3 if name=='sportsdataio_depth_schedule' else 1}
        for name,value in fresh['sources'].items()]
query = 'SELECT source, seconds, status, checked_at, official_freshness_confirmed, endpoint_count FROM source_verification ORDER BY seconds DESC'
connection = duckdb.connect()
connection.register('source_verification',pd.DataFrame(rows))
rows = connection.execute(query).df().to_dict('records')
connection.close()
for row in rows:
    row['source_label'] = {'sportsdataio_depth_schedule':'SportsDataIO', 'sleeper_status':'Sleeper', 'nflverse_injuries':'NFLverse'}[row['source']]
sources[0]['query'] = {'sql':query,'engine':'duckdb','tables_used':['source_verification'],
   'description':'Registered local verification JSON source operations, one observed retrieval each',
   'metric_definitions':{'seconds':'Elapsed retrieval and normalization wall time, seconds; single sample, not percentile'}}
artifact = {'surface':'report','manifest':{'version':1,'surface':'report','title':title,'blocks':blocks,'sources':sources,
    'charts':[{'id':'durations','title':'Source-check duration','subtitle':'Seconds; one sample per operation, October 9',
       'type':'bar','dataset':'durations','sourceId':'fresh','source':sources[0],
       'encodings':{'x':{'field':'source_label'},'y':{'field':'seconds'}},'options':{'showLegend':False}}]},
    'snapshot':{'version':1,'status':'ready','generatedAt':fresh['checked_at'],'datasets':{'durations':rows}},'sources':sources}
(DEST / 'artifact.json').write_text(json.dumps(artifact,indent=2),encoding='utf-8')
print(DEST / 'artifact.json')
