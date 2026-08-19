> ## Documentation Index
> Fetch the complete documentation index at: https://arize-ax.mintlify.site/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# On-Premise Releases

> Release notes for self-hosted Arize AX distribution images.

# Release 11.43.0 (2026-08-13)

## Updates

* Initial on-prem Signal and Managed-Agents support (GCP only) (#82102)
* Project-level user access managed with SAML (#72269)
* Editing a webhook integration does not persist changes, customer had to recreate it (#81132)
* Fixed Impossible to run setSpaceGateLimit because of query validation bug (#79800)
* Coordinator used-segment poll dropped from \~3 minutes to seconds (#80842)
* ADB console gained a read-only view of journal checkpoints (#82888)
* Generic OTLP traces are routed by project header (#82783)
* New REST endpoint GET /v2/evaluator-templates (#82410)
* Data fabric mutations are exposed to programmatic GraphQL (#83255)
* Custom summary-dashboard widgets, backend and GraphQL surface (#82299, #82756–#82763)
* Empty trace-filter state now offers to expand the time range (#82380)
* Error and exception data is surfaced in the app (#82400)
* Space experiments page supports multiselect and bulk delete (#82596)
* Standalone experiments gained a runs table (#81905)
* Dataset views are mounted on the experiment analysis tab (#80719, #80720)
* Media upload associations are cloned when copying into datasets (#81108)
* New predefined roles are synced into existing installs (#78108)
* Managed agents gained Edit schedule and Edit integration UI (#82610)
* Nightly cleanup removes empty directory markers on Azure ADLS Gen2 (#82748)
* Docs for mutable-segment backup alerts (#81647)
* Docs for cipher key and Postgres generation on AWS and OpenShift (#82809)
* Upgrade notes for the Bazel build/distribution release (#79943)
* Cross-tenant space-admin bypass closed in the REST RBAC authorizer (#82850)
* Non-admin USER\_CREATE holders can no longer mint account admins (#82855)
* Reset-password is restricted to account admins (#82872)
* Programmatic setModelBaseline is scoped to the caller's account (#81482)
* Java container metrics start correctly without isContainerized (#83238)
* Trace metrics gear is hidden when no metrics exist (#82883)
* Span input extraction prefers the last user message (#75404)
* Hyphenated annotation column names are validated at save time (#82597)
* Inverted query intervals are rejected as InvalidArgument (#82852)
* Oversized reconciliation windows are chunked to avoid LLM eval timeouts (#81980)
* Experiment name validation is enforced across API and web flows (#80574)
* Agent playground survives invalid request JSON (#82935)
* Playground no longer flashes an empty state while filtering (#83080)
* Settings tables keep action columns pinned under sticky headers (#82937)

***

# Release 11.42.0 (2026-08-11)

## Upgrade Notes

* AWS storage defaults move from gp2 to gp3: the Helm chart now creates gp3-400 (3K IOPS / 400 MB/s) and gp3-2000 (8K IOPS / 2000 MB/s), with storageClassAwsSsd defaulting to gp3-2000 and storageClassAwsStandard to gp3-400. Historicals (hot) follow the SSD class. No Terraform changes.
* Storage classes are immutable, so existing AWS clusters must pin storageClassAwsSsd and storageClassAwsStandard to their current class before upgrading; CheckStorageClassTiersUpgrade (\< v11.40.0) enforces this. Set storageClassCreationEnabled: false to manage the classes yourself.

## Updates

* Show Trace Latency Instead Span Latency on Main Page (#80884)
* Add `sqlglot` to custom code evaluator libraries (#81545)
* Exclude failed/error rows from being in evaluator scope on Evals on Experiments/Playground (#56904)
* Improve metric is zero alert with more details (#82392)
* Honor @include/@skip in extractFields for tracing table (#82339)
* Support Arize AX deployment in IBM Cloud (#79158)
* Auto-include new attribute values in grouped time series chart when "All" is selected (#71497)
* REST API/SDK - from\_dict should tolerate unknown fields rather than raising error (#79242)
* Enable --skip-errors by default on Gazette consumers in on-prem deployments (#78192)
* Correct traces tab shows no data while Spans tab and trace-metric charts are populated (#81328)
* Setting up Monitors for Datasets showing up under projects (#81361)
* Fix issue where last trace not shown in session view (#71518)
* Fix anthropic integration create modal in the UI does not expose base url field (#77946)

***

# Release 11.41.1 (2026-08-06)

## Updates

* Correct Large-interval compaction livelocked by hardcoded 120Min RPC Timeout (#81867)
* Add helper text for eval version pinning (#81526)

***

# Release 11.41.0 (2026-07-31)

## Updates

* Select nested output fields in the experiments column selector (#78614)
* Correct previous-days-high-segment-count alert misfires (#74217)
* Ability to export member lists (#76164)
* Support Kubernetes 1.36 (#74760)
* Require classification choices on GraphQL CreateEvaluatorMutationInput (#79347)
* Improve error display formatting in experiment results (#78883)
* Fixed reject empty/non-finite embedding vectors before upload (#77637)
* Extend LLM Alert Request Body Top Level Fields (#76489)
* Extend LLM Alert Payload Fields (#76490)
* Extend LLM Alert custom\_details Schema Fields (#76494)
* Bring dialog/error message to the top in SAML Config (#79288)
* Added REST API/SDK Spaces API ability to create private spaces using the api (#79239)
* Include requester identity in agent-invocation POST for downstream token/auth relay (#77902)
* Added Support for multi modal with Self-Hosted - Blob Offload (#80178)
* Render timestamp in readable format in Labeling Queue (#79549)
* Display NULL values in pivot table in dashboards (#77668)
* Add "First month of data" preset to time selector dropdown (#75559)
* Correct Azure precheck that failed to pass when using workload identity (#79500)
* List spans endpoints results in validation error for span kind (#79630)
* Task save blocked: variable-mapping validation incorrectly flags existing columns as invalid (#75980)
* Fix AX tasks silently runs only the first of multiple custom code evaluators (#79853)
* No monitors search bar when you are looking at monitors from the project level (#79346)
* Correct SAML Config page slowness, loading hundreds of role mappings (#79286)
* Fixed sort columns on the ML models list page (#80641)
* Test code on span goes through custom code path for templated code evals (#79785)
* Fix Custom Role Not Updating to Standard Role (#80944)
* Alyx Align Eval not recognizing eval and unclear steps following (#80640)
* Adding Dataset to Playground after Evaluator > Edit in Playground Resets Evaluator Prompt (#80722)
* Correct On-prem app-server spewing errors about missing secrets (#72989)
* Fix partial search for space name in SAML role mappings (#79287)

***

# Release 11.40.2 (2026-07-27)

## Updates

* Revert "Use topologySpreadConstraints to enforce zone placement" (#80713)

***

# Release 11.40.1 (2026-07-27)

## Updates

* Corrected Alyx not working with gemini flash with custom model endpoint (#80395)

***

# Release 11.40.0 (2026-07-21)

## Upgrade Notes

* ***Breaking Change***: Must upgrade to SDK 8.40.x for compatibility with 11.40.x
  This change only applies to the REST APIs. ML ingestion paths like SDK dataframe and single record log uploads, LLM OTLP ingestion paths are not affected.
  Arize recommends upgrading the Arize AX application to 11.40.x first and update to SDK 8.40.x following the upgrade.
* SDK 8.40.x is compatible with earlier versions where flightserver is used (flight path).
* SDK 8.40.x is incompatible with earlier versions where apiproxy is used (REST path).
* SDK 8.39.x is incompatible with REST APIs in Arize AX 11.40.x (Annotations APIs, Space APIs, etc.).

## Updates

* Pending segment scan alert too sensitive, its alerting after just 1 scan. (#78403)
* Add health to signal and agent replay (#78903, #79029)
* Druidloaderv2 scaling down issue when transferring work to another pod (#78412)
* Add Prometheus proxy (#78017)
* Preserve deep-link redirect through SAML login (#77499)
* Test single bucket for deployment (#55461)
* Correct "Action" Column Next to Evaluator to show Evaluator ID for Some Evals (#78244)
* Correct monitor range threshold description (#56575)
* Fix file-based SAML config failures with "email domain conflict" (#77908)
* Correct error saving evaluator when editing or renaming eval (#78765)
* Correct S3-compatible PutObject XAmzContentSHA256Mismatch (#77687)
* Fix Data Fabric S3 export failures: duplicate Iceberg field ID in BYOB schema conversion (#79150)
* Add changes to monitor notifications to audit log consistently (#70868)
* Fix Custom Model Endpoints Inconsistencies (#78111)
* Correct GPT 5.4 via Azure eval uses unsupported parameters (#79284)
* Clicking View Sessions from Dashboard > Share Link > Link leads to Dashboard Rather than Session (#76285)
* Fixed Monitor page displays stale state until user interaction intermittently (#77190)
* Correct Evaluator column mapping dropdown missing some span attributes (#75273)
* Fixed Evaluators Not Loading (#75259)
* PSI drift monitors permanently show 'No Data' when dimension\_config is missing (#72525)
* Gazette container race with istio-proxy and historical issues on GCP Cloud Mesh / Istio no Native Container (#77735)
* Session detail slideover shows "An error occurred" for high-volume projects (#79695)
* Dashboard Plots Times in the Future for Timezones that are UTC + X:30 (#74794)
* ApiProxy5xxAny 500s on CreateEvaluatorVersion/TriggerTaskRun — surface FK violation as 4xx (#72355)
* Correct Agent Graph where self-loop on start node if any node has a custom metadata.node.id = "start" (#69663)

***

# Release 11.39.2 (2026-07-18)

## Updates

* Fixed Session-level eval input variable that silently truncated at 100k chars (#76193)
* Fixed Deletion of Service Keys (#79267)

***

# Release 11.39.1 (2026-07-13)

## Updates

* Allow multiple session trace evals on tasks (#78251)
* Clear out deprecated models from Playground (#78189)
* Fix Cost Tracking with Trace header (#72959)
* Rename on-prem span payload limit for max\_span\_payload\_characters (#78811)
* Restore Ingestion dashboard to classic schema (#78678)
* Removal of alpine based postgres image (#78465)

***

# Release 11.39.0 (2026-07-10)

## Updates

* Allow Wildcard in Email Domain for SAML Config (#75104)
* Updated Eval Slideover UI (#77245)
* Improvements to session eval custom to turn schema preview UI (#77186)
* Ability to exclude retention to data fabric buckets (#74979)
* No way to restrict end users from seeing org settings/account settings (#76157)
* Change app-server max-old-space-size (#75673)
* FIPS Postgres fe\_sendauth: error sending password authentication (#77889)
* Stream span CSV exports directly to disk to fix large-download memory failures (#77257)
* Expose span I/O character limit via on-prem values.yaml (#78249)
* Add an option to use /chat/completions with openai models (#78113)
* Advance last run at (#77108)
* Advance when no data error (#77170)
* Buffer truncated window advancement (#77189)
* Fix service keys with custom space role cannot be deleted or refreshed (#76473)
* Bedrock Calls can use Wrong Region when Base URL is set (#70882)
* Performance monitors created via GraphQL API with custom metrics fail to render in UI (#63149)
* Org admins cannot create a service key with org-admin permissions (#77235)
* Broken drift monitors showing "No metric history data to display" despite data present (#76518)
* Evaluator config span preview: clicking on span text doesn't open the slideover (#76546)
* Correct REST API Returns Misleading 409 Conflict Error When Creating Annotation Queue with Invalid Annotator Email (#77662)
* Correct onlinetasksrunner backfill runs fail when context cancelled before result file is written (#76225)
* Widget plot modelId field returns raw database ID instead of global ID for LineChart and StatisticWidget (#77657)
* Correct Fileimport jobs picking up new files in bucket (#77985)
* Add support for mistral.magistral-small-2509 in Bedrock (#77732)
* Correct Prompt Playground with different dataset rows showing inconsistent error formatting when LLM provider returns 400 (#70441)
* Make I/O fields max char validation limit flag-configurable (#78237)
* Correct Filters ignorign Cardinality New/Missing Values monitor value list (#77753)
* Playground view not saving dataset (#75324)
* Fix Gpt 5.4 in the playground that throws a 400 error (#68682)
* Fix Snowflake import job bug where all features show as nulls if their names start with an underscore (#54059)

***

# Release 11.38.5 (2026-07-10)

## Updates

* Expose span I/O character limit via on-prem values.yaml (#78249)
* Make I/O fields max char validation limit flag-configurable (#78237)
* Convert legacy query filters to multi-span on load (#77196)

***

# Release 11.38.4 (2026-07-07)

## Updates

* Broken drift monitors showing "No metric history data to display" despite data present (#76518)
* Fixed REST API Returns Misleading 409 Conflict Error When Creating Annotation Queue with Invalid Annotator Email (#77662)
* Use non FIPS images for toolbox (#77904)

***

# Release 11.38.3 (2026-07-03)

## Updates

* Advance when no data error (#77170)
* Advance the last run on truncated window (#77108)
* Fix buffer truncated window advancement (#77189)
* Resolve CVE (#77627)
* Resolve CVE (#77503)
* Resolve CVE (#77638)

***

# Release 11.38.2 (2026-07-02)

## Updates

* Org admins cannot create a service key with org-admin permissions (#77235)

***

# Release 11.38.1 (2026-06-30)

## Updates

* Preserve newlines in highlighted code blocks (#77182)
* Adjust span delete interval timeout (#77175)

***

# Release 11.38.0 (2026-06-30)

## Updates

* Increase rate limits in EU (#75814)
* Add Alert to see when postgres connections are not being released (#75898)
* Add pagination param for listDatasetExamples endpoint (#72754)
* Datasets compare table hard to click into row (#75937)
* Make output on experiment run prettier for eval runs (#75933)
* Support Multi Region Deployment on AWS with AWS SDK v2 (#26849)
* Make the default span attributes display configurable (#71484)
* Support Data Fabric BYOB with on-prem (#70770)
* Update the username to match the SAML name attribute when existing user logs in (#73781)
* Hallucination Prompt Template Incorrect (#74519)
* Task logs UI does not surface skipped rows or errors, making failures difficult to debug (#72564)
* Can't filter on output column in dataset preview when setting up code evals (#74578)
* Add-user-to-space dropdown potentially capping available users, hiding users in large orgs (#74349)
* Deleting or annotating dataset records does not update `datasets.updated_at` (#75283)
* Querying for sessions is incorrect (#72280)
* Code eval fails with "Task was unable to handle template variable: documents" despite valid preview (#76120)
* Data is Truncated when Copying Examples to New Dataset (#74337)
* InferenceConfig Temperature Missing in AWS Bedrock Integration (#75775)
* TaskRuntimeError: Invalid column: attributes.input.value... errors occurring in online tasks when the attributes do exist (#75953)
* Input.value in eval variables mapping doesn't match the actual span attribute (#76483)
* Orgs not viewable after you hit 100 orgs (#76508)

***

# Release 11.37.1 (2026-06-24)

## Updates

* Update Netty (#75563)
* Correct filter dataset preview on experiment output column (#75896)

***

# Release 11.37.0 (2026-06-22)

## Updates

* cleanup azure MI docs (#73517)
* Support Multi Region Deployment on AWS with AWS SDK v2 (#26849)
* 502 error when deleting spans via Python SDK (#74705)
* Login Failed (#75490)
* Attentive: attributes.metadata.eval\_name overwritten to same value for all traces (#75615)

***

# Release 11.35.2 (2026-06-19)

## Updates

* Login failed after flood of space creations (#75490)

***

# Release 11.35.1 (2026-06-08)

## Updates

* Add internalendpoints bulk proxy (#74252)

***

# Release 11.35.0 (2026-06-08)

## Updates

* Update postgres username for adb control plane (#73552)
* Export per-service / per-endpoint REST API rate limits to docs (#73876)
* Bar chart bin logic creates double counting (#64812)
* Bad Transparent UI When Creating Drift Template Dashboard (#72332)
* Monitors page cannot scroll down (#74100)
* Generative-server not starting on IPv6-disabled clusters (#74013)
* Fix run\_experiment error in playground (#71886)
* Can't filter on tag when % Empty is very high (#72338)
* ADB UI config doesn't save empty decommissioned nodes list (#74045)
* Dashboard Bins are not being ordered correctly (#41501)

***

# Release 11.34.1 (2026-06-04)

## Updates

* Scale copilot memory (#73874)

***

# Release 11.34.0 (2026-06-02)

## Updates

* Ability to see date created and last usage on API Keys (#60313)
* Add value to set global max tasks for druidimporter (#71909)
* Include attributes.metadata.\* attributes in flight server span exports (#72532)
* Remove the ability to delete spaces by name (#72445)
* Add gemini-3.1-flash-lite to supported models (#72750)
* Expose source mapping config mutations (#72834)
* Allow Users to Add an Expiration Date to API Keys in the UI (#72522)
* Improve Metrics Tab Trace Graph View (#72666)
* Add kgateway example (#73046)
* Update postgres username for adb control plane (#73552)
* Unable to click update after adding a new eval to a task (#72467)
* Organization Admins can't get evals from private spaces in sdk (#72461)
* Prompts get - missing verbosity error (#72582)
* Eval Variable Mapping Column Selector (#72354)
* Revert fix tracing table height" (#72622)
* Dashboard tags flicker and conflict with UI element when applied (#72851)
* Post-login redirect drops monitor URL path and query params (#72331)
* Trace Workflow Doesn't Account for Time Window (#73187)
* Alyx Errors with Multi-Select (#73234)
* Evals Unexpectedly Added to Spans with "N/A" in label (#72610)

***

# Release 11.33.4 (2026-06-08)

## Updates

* Trace Slideover details not loading for late ingested spans (#74232)

***

# Release 11.33.3 (2026-05-29)

## Updates

* revert fix tracing table height (#72622)

***

# Release 11.33.2 (2026-05-29)

## Updates

* Dashboard Widget Account for Time Window (#73187)

***

# Release 11.33.1 (2026-05-26)

## Updates

* Expose source mapping config mutations (#72834)

***

# Release 11.33.0 (2026-05-21)

## Updates

* Ability to add other alerts to Pager Duty (#40027)
* Support Data Fabric BYOB with on-prem (#70770)
* Space Admins Cannot Add Members (#72321)
* UI user management unavailable despite disabled "sync permissions on each login" (#72444)
* Post-login redirect drops monitor URL path (#72331)
* Running Tasks + Tracing Projects Page Not Loading (#72249)
* UI restart required after on-prem upgrade (#72333)

***

# Release 11.32.3 (2026-05-20)

## Updates

* Resolve CVEs (#72040)

***

# Release 11.32.2 (2026-05-19)

## Updates

* Code Evals "Test Code on Example" does not complete (#71848)

***

# Release 11.32.1 (2026-05-18)

## Updates

* Add option to set clusterDomain (#72105)

***

# Release 11.32.0 (2026-05-16)

## Updates

* Enable realtime on all spaces on new installs (#70776)
* Update Druidloaderv2 Scaling Query (#71931)
* Enhanced Eval Visibility: Display Evaluation Status and Results in Log Tab (#59214)
* Online Tasks Continually get stuck in a pending state (#69565)
* Ingestion down and no pagerduty alert raised (#70820)
* Org Admins Unable to View Org or Space Members (#71707)
* Edit evaluator page issue when loading a project with typeahead dimensions (#71592)
* Evaluator edit page loads entire dataset (#69635)

***

# Release 11.31.1 (2026-05-14)

## Updates

* Online Tasks Continually in a pending state (#69565)
* Update Druidloaderv2 Scaling Query (#71931)

***

# Release 11.31.0 (2026-05-14)

## Updates

* Enable webhooks for all users (#70792)
* Inline Code Evals (#68912)
* Support base64 images larger than 16KB in traces table view (#70113)
* Update Terraform to have common tagging in AWS using default\_tags (#70715)
* Add reasoning/verbosity to LLM parameters for gpt-5 models (#60871)
* Comparison of the same time range on the perf dashboard yields different results (#44731)
* AX CLI v0.12.0 SSL regression for self-hosted/CloudFront deployments (#68477)
* request\_verify=false not respected on REST API code paths (#68454)
* Evaluator Variable Mappings page continuously calls SpansContentQuery (#70848)
* Dashboard "monitor summary" template not saving (#45173)
* export\_model\_to\_parquet fails when non-nullable columns contain nulls (#60320)
* Threshold field looks like it is editable when the monitor is not in edit mode (#55809)
* Contains Filter on Experiments Does Not Work (#70611)
* Task logs button doesn't work in the experiment comparison view (#71207)
* Settings Page API Keys Sort Does Not Work (#70810)
* Eval Tracing Toggle Not Saving (#71314)
* Non-admins can't access the account members page (#71535)
* Dashboards listing page cannot be scrolled (#71060)
* Bad formatting in the "pretty" input/output attributes display (#71487)

***

# Release 11.30.4 (2026-05-13)

## Updates

* Conditional apparmor annotation for inline custom code evals (#71594)

***

# Release 11.30.3 (2026-05-12)

## Updates

* Add internalendpoint req/resp log (#71337)
* `export_model_to_parquet` fails when non-nullable columns contain nulls (#60320)

***

# Release 11.30.2 (2026-05-07)

## Updates

* Evaluator Variable Mappings page continuously calls SpansContentQuery (#70848)

***

# Release 11.30.1 (2026-05-07)

## Updates

* Resolve CVE-2025-68121 (#70759)

***

# Release 11.30.0 (2026-05-07)

## Updates

* Support usage page with on-prem (#67038)
* Sign on-prem container images (#45971)
* Skip loading Stripe JS if onprem (#61020)
* Precheck postgres timezone/datestyle (#69216)
* Improve Alyx Error Messaging when Rate Limits are hit (#69963)
* Task run status stuck at running (#64054)
* Copy data easily in the compare experiments slideover (#61308)
* Add evaluate, langdetect to the custom code eval library (#70099)
* Alyx Generated Views (#69396)
* Evals on Datasets (#48761)
* Variable mapping issues (#69916)
* Eval Hover Modal linkage to Task Run (#65539)
* Expose mutation to set rate limits programmatically (#68295)
* Increment the default API version in Prompt Playground for Azure OpenAI (#59875)
* Additional span attributes aren't persisted in legacy code evals (#67380)
* Changes made to legacy custom code evals aren't persisted (#67381)
* Unable to scroll through all spaces in Custom Model Endpoint selection (#69307)
* Data uploaded to training environment without actuals is silently failing (#66881)
* Ranking Models - Rank showing up as a feature (#68642)
* Auto-add-to-dataset query filter parsing doesn't work with double quotes (#68938)
* Task Logs shows 0 for all counts on backfill eval tasks with multiple trace-level evaluators (#69567)
* Session filter incorrectly matches Boolean values for Custom Attribute despite 0 Count (#69641)
* Incorrect nodes and counts on the agent path (#69703)
* Experiment eval rows show score but no label/explanation when there's an error in the judge LLM response (#69632)
* Saved View Not Working Broken from Evaluator > Filter Sessions (#68234)
* Missing timestamp column in the performance dashboard table view (#63014)
* SAML role mapping mutation leaves organization field blank in UI despite successful backend update (#68621)
* New Org Not Propagated to Added Users Unless First Space is Created (#65131)
* View Experiment Traces returns unhelpful "An error occurred" (#70511)
* Log\_spans does not allow for custom attributes (#55015)

***

# Release 11.29.3 (2026-05-01) (Maintenance)

## Updates

* Turn off the date validator (#69908)

***

# Release 11.29.2 (2026-04-30) (Maintenance)

## Updates

* Auto-add-to-dataset query filter parsing with double quotes (#68938)

***

# Release 11.29.1 (2026-04-29) (Maintenance)

## Updates

* Inline Code Evals (#68912)
* Importer parameter update (#67818)

***

# Release 11.29.0 (2026-04-29) (Maintenance)

## Updates

* Support base64 images in playground that are not prefixed with data:image/ (#52538)
* Autosize generative server horizontally (#67732)
* Add Newer OA Models include O4 (#46958)
* Add developer checks to create api key mutations in app-server (#69715)
* Update service keys to do the deveoper checks in all places (#69852)
* Skip loading Stripe JS if onprem (#61020)
* Unable to successfully run evals on Base64 Images Without Prefix (#66884)
* List experiments endpoint returns 500: cannot unmarshal number into string for 'id' field (#68046)
* Fileimporter dialog keep reloading default schema (#69512)
* Annotation through SDK hits "Error logging arrow table to Arize AX" for permissions (#69540)
* Bedrock Throwing Error if using Custom Model Without Enabling Default Models (#69544)
* Updating dashboard widget with custom metric doesn't save (#69630)
* Dashboard text widget cut off after certain character limit (#67862)
* Cost Config Page Entries Duplicated (#69069)
* Alerts History API not showing past 30 days (#69854)

***

# Release 11.28.0 (2026-04-22) (Maintenance)

## Updates

* Add SERVICE\_KEY\_READ and SERVICE\_KEY\_UPDATE permissions (#68442)
* ADB control plane and rate limits (#68782)
* Add a search to space selector (#67735)
* VertexAI API Error ECONNRESET (#69151)

***

# Release 11.27.1 (2026-04-21) (Maintenance)

## Updates

* VertexAI API Error ECONNRESET (#69151)

***

# Release 11.27.0 (2026-04-21) (Maintenance)

## Updates

* Expose API to pull aggregated tracing metrics (#68683)
* Improve migrate/restore from pg pod to cloud external postgres (#64806)
* Wrong order of annotation configs in the dataset row view (#64513)
* Sort the order of annotations on the projects page (#60651)
* Auto expand cells in dataset (#68695)
* Carry Over Column Selection in Datasets Page to Dataset Row Detail (#68736)
* Trace-level eval with span filter incorrectly shows "Running" state on traces missing the required span (#67941)
* Vertex Gemini 2.5-pro and 2.5-flash throwing 'exception posting request to model' error (#67287)
* "History" for Filter Bar in Experiments Page Does Not Work (#62202)
* Labelling queue - column selection resetting (#68567)
* Eval config shows false "Column not found" for nested JSON string paths (#68603)
* parentId is non-nullable on TaskRun GraphQL schema (#66616)
* Rate Limits cannot be Reset to No Limit (#68296)
* Vertex AI Claude Haiku 4.5 returns 404 due to incorrect model ID (#68734)
* Duplicate eval columns in dataset when spans already carry evals and a task re-evaluates the same column (#68909)

***

# Release 11.26.2 (2026-04-20) (Maintenance)

## Updates

* Vertex Gemini 2.5-pro and 2.5-flash throwing 'exception posting request to model' error (#67287)

***

# Release 11.26.1 (2026-04-16) (Maintenance)

## Updates

* Bedrock proxy\_with\_headers improvements (#68593)
* Custom Code Evals improvements for Playground (#65884)

***

# Release 11.26.0 (2026-04-15) (Maintenance)

## Updates

* Fine Grained Access Control - Resource Level (#56430)
* Support realtime traces on existing spaces (#67916)
* Lift feature flag rbac (#68433)
* Respect user timezone setting on CSV export (#68315)
* Prompt Playground Azure OpenAI returns 400 for gpt-5.4-nano (#67221)
* Experiment compare slideover image render (#68239)
* Monitor Filter Saving (#68324)
* Incorrect Annotation Count on Example (#64578)
* Trace-level eval with span filter shows "Running" state on traces missing the required span (#67941)
* Login page 401 refresh (#67576)

***

# Release 11.25.1 (2026-04-12) (Maintenance)

## Updates

* Respect user timezone setting on CSV export (#68315)
* Monitor Filter Not Saving (#68324)

***

# Release 11.25.0 (2026-04-11) (Maintenance)

### Upgrade Notes

* ***values change***: gcpServiceAccountName and azureStorageAccountName are no longer base64 encoded

## Updates

* Enable count metric for non-numeric data in pivot tables (#62412)
* Enable Calico as a method for Network Policies in GKE in Terraform (#67559)
* Experiments page should render the rows with output != NULL filter pre-populated (#57195)
* Customize Rate Limit for Playground Runs (#67245)
* Link Back button on Dashboard to the Dashboards List Rather than Browser Page (#67821)
* Trace listing table shows blank input/output when detail view shows data (#65098)
* Alyx Issue When Asking Questions about Code Evals (#67096)
* Code eval ignores evaluator-level trace granularity — results merged at span level (#67575)
* Update does not update in Evaluator Version (#62656)
* Evaluator UI inconsistency Cannot remove LLM override once added (#65416)
* Dashboards - Unable to Duplicate Pivot Table Widget (#67847)
* Remove gcpServiceAccountName and azureStorageAccountName from secret (#65550)
* AX Profiles Create On Prem Throws Error When defining single host (#68040)
* Eval variables not mapping correctly (#68025)
* ArizeDB limit causes multi-span filters A and B yield different results than B & A (#65500)
* Playground run fails when eval is selected (#68126)

***

# Release 11.24.2 (2026-04-03) (Maintenance)

## Updates

* Remove control plane alert rule (#67790)

***

# Release 11.24.1 (2026-04-02) (Maintenance)

## Updates

* Trace listing table shows blank input/output when detail view shows data (#65098)

***

***

# Release 11.24.0 (2026-03-31) (Maintenance)

## Updates

* Project-level RBAC for Tracing (#66110)
* Prevent phantom session eval scores (#67056)
* Sessions metrics bar (#67107)
* Persist time range in the tracing page URL (#67229)
* Cannot cancel task run — wrong RBAC permission checked (#66844)
* Session Evals Attached with "0" to Sessions the Eval Has Not Run On (#67050)
* Base64 Images are cutoff in experiments view (#65926)
* Playground Runs on More Rows than Dataset Has if Dataset has Duplicate IDs (#66593)
* Validation error during regex matching code eval setup due to undefined span attribute (#64925)

***

# Release 11.23.1 (2026-03-28) (Maintenance)

## Updates

* Base64 Images are cutoff in experiments view (#65926)

***

# Release 11.23.0 (2026-03-27) (Maintenance)

## Updates

* Gemini 3 Pro deprecation thru GCP Vertex (#66865)
* Expand Eval Avg Score in Experiments (#66952)
* Enable easy mapping between Arize AX Space IDs and Space UUIDs in Grafana (#66329)
* Azure managed identity for all services on on-prem (#48506)
* Improve migrate/restore from pg pod to cloud external postgres (#64806)
* "View Spans" from dashboard bar chart applies wrong series filters, returning 0 results (#66425)
* "View Spans" drill-down from dashboard chart resets time filter to 15m instead of inheriting selected range (#66423)
* Updating Eval Task target datasource from Project to Dataset doesn't update target in Eval Tasks tab (#65064)
* Task Rename Incorrectly Says "Task Run Started" (#65737)
* Evaluator rename not propagated to tasks and eval\_results (#65736)
* Dashboard-Wide Filters Do Not Apply to Distribution Widgets (#65652)
* Show monitor summary template on dashboard slideover (#66311)
* VertexAI API Error. Streaming is strongly recommended for operations that may take longer than 10 minutes (#66494)

***

# Release 11.22.3 (2026-03-26) (Maintenance)

## Updates

* Gemini 3.1 models to Vertex AI provider (#66846)

***

# Release 11.22.2 (2026-03-20) (Maintenance)

## Updates

* Internal server error on playground run (#65651)
* Bedrock integration sends empty externalid causing aws validation error (#63805)

***

***

# Release 11.22.1 (2026-03-17) (Maintenance)

## Updates

* Copilot pod CrashLoop when using Azure Managed Identity (#65521)
* Alyx does not let user select a custom endpoint if model name is `gpt-4.1-custom` (#65785)

***

***

# Release 11.22.0 (2026-03-14) (Maintenance)

## Updates

* Support Data Fabric BYOB on GCP/AWS (#54438)
* Support Gemini integration (#64478)
* Remove the index in the Experiments table (#65285)
* Support a custom pre-install for customer to collect secrets (#62902)
* Custom Code Evals not working in playground (#61815)
* Prompt Hub doesn't support out-of-the-box OpenAI tools (#64864)
* Postgres not available during the upgrade (#62747)
* Experiment eval labels are wrong colors (#65283)
* Custom time filter in Traces page when default language other than English (#57334)
* Evaluator multiselect deduplication and unclear naming (#65469)

***

# Release 11.21.1 (2026-03-10) (Maintenance)

## Updates

* Setting retention on a datasource returns to global retention (#64585)

***

# Release 11.21.0 (2026-03-06) (Maintenance)

## Updates

* Alyx 2.0 (#60212)
* Scope Better Graph Legends Readability (#41615)
* Bump arizedb-indexing indexing-volume (#63942)
* Add docs for in-cluster service reference (#62417)
* Update alermanager email subject format (#63440)
* Keep ML models turned on by default for new spaces (#64018)
* Enable filters in scatter plots (#62410)
* Honor client-sent cost (#62815)
* Add alermanager support for Teams, TeamsV2, Slack (#63339)
* Can't select the output column in prompt optimization task (#50493)
* Span Query Filters Incorrect When Selecting View Spans in Dashboard Distribution Widget (#63969)
* Wrong filter value applied for numbers like 35.1k when going from dashboards to traces (#53319)
* Dataset UI breaks on Chinese dataset (#58674)
* FILTER clause is incorrectly handling WHERE clause on list of strings (#63461)
* Incomplete filters applied going from a stacked bar chart to view spans (#62409)
* PSI Seems very low for the visualized distributions (#63862)
* Cardinality metric missing from dashboard widget metric dropdown for LLM models (#63630)
* Drift shows no data for training dataset when all data has the same timestamp (#64118)

***

# Release 11.20.1 (2026-02-28) (Maintenance)

## Updates

* Add configurable custom IO parser (#64197)

***

# Release 11.20.0 (2026-02-23) (Maintenance)

## Updates

* Input/Output Table Rendering (#62223)
* Support custom model endpoint with bedrock API (#47740)
* Support for llm generation cost on playground, experiments (#50604)
* RBAC SAML UI (#63190)
* Tasks with multiple evaluators return NOT\_PARSABLE (#62760)
* Filtering on trace and session evals doesn't work (#62062)
* Cannot see nested attributes in eval variable preview (#62250)
* Can't use gpt-5-nano models for evals due to temperature settings (#60546)
* Online Evals - Gpt-5 max\_tokens error (#60031)
* Param Validation Error in Online Evals with Bedrock Sonnet 3.7, 4.5 (#61048)
* Incorrect routing applied from the time series chart hover (#62860)
* Can't scroll to see all session evals (#63173)
* DeleteSpace GraphQL call return "Success" regardless of success or failure (#61344)
* Building Dashboard Widgets is incorrect on Safari (#63148)
* Cost config table has same column names if applied to both prompt / completion columns (#63395)
* Missing AWS Bedrock Provider Params Validation Causes Task Failure (#62220)
* No traces with filter, but cost, tokens, latency still shows a value (#63015)
* Inputoutput table rendering (#62776)

***

# Release 11.19.2 (2026-02-19) (Maintenance)

## Updates

* Traces stats query causing incorrect data (#56226)
* Security updates (#63121, #63400, #63120, #63013)

***

# Release 11.19.1 (2026-02-12) (Maintenance)

## Updates

* Security update for grafana (#62875)
* Remove historicals OnRootMismatch (#62859)

***

# Release 11.19.0 (2026-02-12) (Maintenance)

## Updates

* Option to enable realtime traces for new spaces on GCP/Azure/AWS/Private Cloud (#43838)
* Support escaped curly braces in online eval templates (#61862)
* Generate java certificate from blobUserCertificate (#48207)
* ADB UI to replace existing console (#54676)
* Copilot support for LLM integrations (#62717)
* Add missing apiproxy discovery (#62415)
* Pred scores are incorrect when sending list of strings via java sdk (#61988)
* Annotations SDK does not support adding text annotations (#57343)
* dashboard\_time\_range\_key schema migration failure (#62735)
* Playground Erroring with Model Unreachable when Clicking "Function" (#62782)
* Tasks with multiple evaluators return NOT\_PARSABLE (#62760)

***

# Release 11.18.2 (2026-02-10) (Maintenance)

## Updates

* Users Still Able to Download Data via SDK with export disabled (#62580)

***

# Release 11.18.1 (2026-02-09) (Maintenance)

## Updates

* Parameter repoSubdir is not used in the chart/manifest (#61811)
* Parse json input and output attributes (#62386)

***

# Release 11.18.0 (2026-02-07) (Maintenance)

## Updates

* Option to enable realtime traces for new spaces on GCP/Azure/AWS (#43838)
* Support Azure Custom Endpoints with custom auth (#60430)
* Add traces to prober and datagenerator (#54981)
* Pivot table widget (#54533)
* Support not adding image pull secret when secret name is empty (#61810)
* Support Kubernetes 1.35 (#61880)
* Add Helm/ArgoCD hook to check operator reconcile status (#56917)
* Resolve CVE‑2025‑15467 (#62306)
* Session page unresponsive or crashing for very long sessions (#58881)
* Time selector doesn't work on sessions page (#59785)
* Copy+pasting text into playground doesn't update state (#61356)
* Responses Spans vs. Chat Completion Spans Differ in Image Attributes (#61194)
* Evals with more than 4 labels UI bug (#60890)
* Error when trying to log boolean labels via java sdk (#61983)
* Order in which we surface experiment results (#58918)
* Add missing rate limit controls (#62081)
* repoSubdir is not used in the chart/manifest (#61811)
* Clean up conditional PDB if defaultMinAvailable=0 (#59881)
* Granularity selection doesn't change drift timeseries chart (#60181)
* Configmap onprem-metadata creation issue (#62125)
* Annotation config names cut off at 30 characters (#61265)
* Dataset Evals Failing for Bedrock Models (#60862)

***

# Release 11.17.5 (2026-02-10) (Maintenance)

## Updates

* Users Still Able to Download Data via SDK with export disabled (#62580)

***
