# Alert threshold table

All thresholds are fiction-free operations defaults for a member-space platform.
Metrics come from node_exporter / postgres_exporter / redis_exporter / blackbox_exporter
and app-side metrics. `runbook_url` and `dashboard_url` annotations exist on every rule.

| # | Alert | Family | Series | Condition | For | Severity |
|---|-------|--------|--------|-----------|-----|----------|
| 1 | HostDiskUsageHigh | host | node_filesystem_avail_bytes / node_filesystem_size_bytes | used > 85% | 10m | warning |
| 2 | HostDiskUsageCritical | host | node_filesystem_avail_bytes / node_filesystem_size_bytes | used > 95% | 5m | critical |
| 3 | HostMemoryHigh | host | node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes | used > 90% | 10m | warning |
| 4 | NodeExporterDown | host | up{job="node_exporter"} | == 0 | 3m | critical |
| 5 | DBConnectionRatioHigh | database | pg_stat_database_numbackends / pg_settings_max_connections | > 80% | 5m | warning |
| 6 | DBReplicationLagHigh | database | pg_replication_lag_seconds | > 30s | 2m | warning |
| 7 | DBSlowQueriesHigh | database | increase(pg_slow_queries_total[5m]) | > 50 / 5m | 5m | warning |
| 8 | DBBackupOverdue | database | time() - pg_last_backup_success_timestamp_seconds | > 26h | 5m | warning |
| 9 | RedisMemoryHigh | redis | redis_memory_used_bytes / redis_memory_max_bytes | > 85% | 10m | warning |
| 10 | RedisQueueKeysEvicted | redis | increase(redis_evicted_keys_total{key_prefix="queue:"}[5m]) | > 0 | 1m | critical |
| 11 | QueueBacklogHigh | queue | queue_backlog | > 1000 | 10m | warning |
| 12 | QueueOldestTaskAgeHigh | queue | queue_oldest_task_age_seconds | > 900s | 5m | warning |
| 13 | API5xxRateHigh | api | rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) | > 2% | 5m | critical |
| 14 | APIP95LatencyHigh | api | histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) | > 2s | 10m | warning |
| 15 | CertExpiringSoon | cert | probe_ssl_earliest_cert_expiry - time() | < 14d | 1h | warning |

## Routing / timing

- group_by: alertname, env, severity
- group_wait: 5m ; group_interval: 5m ; repeat_interval: 4h ; resolve_timeout: 5m
- send_resolved: true on all relay receivers
- dev env: `dev-noop` receiver (no integrations) — no notification
- inhibition: critical suppresses warning on same (family, instance); HostDiskUsageCritical suppresses HostDiskUsageHigh explicitly

## Notification content contract

WeCom markdown and Feishu interactive cards carry ONLY: alert name, environment,
instance, start time, panel link, runbook link, and (for resolved) resolved time.
Business-data-like / PII-like labels and annotations are dropped by the serializer
whitelist and asserted absent by tests.

## Integration points (stubs where a dependency ticket is pending)

- `pg_slow_queries_total`, `pg_last_backup_success_timestamp_seconds`: app/exporter metrics — if the metric differs in the target stack, edit the expression in `alerts/database.yml` only.
- `redis_evicted_keys_total{key_prefix="queue:"}`: app-side exporter must tag queue keys with `key_prefix="queue:"`; this is the "queue keys must not be evicted" guardrail.
- `queue_backlog`, `queue_oldest_task_age_seconds`, `http_requests_total`, `http_request_duration_seconds_bucket`: application metrics from the metrics ticket.
- Webhook URLs: resolved at runtime from KMS into `WECOM_WEBHOOK_URL` / `FEISHU_WEBHOOK_URL`; never written into any file in this repo.
