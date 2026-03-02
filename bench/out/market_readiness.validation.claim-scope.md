# Claim Scope Report

- Generated: `2026-03-01T18:37:00.931375Z`
- Report: `bench/out/20260301T173606Z/metal.npm.compare.json`
- Comparison status: `comparable`
- Claim status: `claimable`
- Claimability mode: `local`
- Workloads: `7`

| Workload | Domain | p50% | p95% | p99% | Timing (L/R) | Backend (L/R) |
|---|---:|---:|---:|---:|---|---|
| par_buffer_upload_1kb | upload | 4601.2164104651165 | 4882.3915140624995 | 4882.3915140624995 | doe-execution-row-total-ns / dawn-perf-wall-time | doe_metal /  |
| par_buffer_upload_64kb | upload | 5857.330636597938 | 5690.292109223301 | 5690.292109223301 | doe-execution-row-total-ns / dawn-perf-wall-time | doe_metal /  |
| par_buffer_upload_1mb | upload | 47365.54265380952 | 38509.252658076926 | 38509.252658076926 | doe-execution-row-total-ns / dawn-perf-wall-time | doe_metal /  |
| par_buffer_upload_4mb | upload | 155790.92098384618 | 146432.98712357142 | 146432.98712357142 | doe-execution-row-total-ns / dawn-perf-wall-time | doe_metal /  |
| par_buffer_upload_16mb | upload | 963360.9850000001 | 809019.3527272729 | 809019.3527272729 | doe-execution-row-total-ns / dawn-perf-wall-time | doe_metal /  |
| ctr_resource_lifecycle_contract | p0-resource | 218924.6640536842 | 191329.67171727272 | 191329.67171727272 | doe-execution-total-ns / dawn-perf-wall-time | doe_metal /  |
| par_uniform_buffer_update_writebuffer_partial_single | render | 221.56382151423642 | 199.44606105843005 | 199.44606105843005 | doe-execution-total-ns / dawn-perf-wall-time | doe_metal /  |

## Citation-ready lines

- par_buffer_upload_1kb: comparisonStatus=comparable, claimStatus=claimable, workloadComparable=True, workloadComparableNow=True, workloadClaimableNow=True, delta(p50/p95/p99)=4601.2164104651165/4882.3915140624995/4882.3915140624995, timingSources(left/right)=['doe-execution-row-total-ns']/['dawn-perf-wall-time'], backend(left/right)=doe_metal/, report=bench/out/20260301T173606Z/metal.npm.compare.json
- par_buffer_upload_64kb: comparisonStatus=comparable, claimStatus=claimable, workloadComparable=True, workloadComparableNow=True, workloadClaimableNow=True, delta(p50/p95/p99)=5857.330636597938/5690.292109223301/5690.292109223301, timingSources(left/right)=['doe-execution-row-total-ns']/['dawn-perf-wall-time'], backend(left/right)=doe_metal/, report=bench/out/20260301T173606Z/metal.npm.compare.json
- par_buffer_upload_1mb: comparisonStatus=comparable, claimStatus=claimable, workloadComparable=True, workloadComparableNow=True, workloadClaimableNow=True, delta(p50/p95/p99)=47365.54265380952/38509.252658076926/38509.252658076926, timingSources(left/right)=['doe-execution-row-total-ns']/['dawn-perf-wall-time'], backend(left/right)=doe_metal/, report=bench/out/20260301T173606Z/metal.npm.compare.json
- par_buffer_upload_4mb: comparisonStatus=comparable, claimStatus=claimable, workloadComparable=True, workloadComparableNow=True, workloadClaimableNow=True, delta(p50/p95/p99)=155790.92098384618/146432.98712357142/146432.98712357142, timingSources(left/right)=['doe-execution-row-total-ns']/['dawn-perf-wall-time'], backend(left/right)=doe_metal/, report=bench/out/20260301T173606Z/metal.npm.compare.json
- par_buffer_upload_16mb: comparisonStatus=comparable, claimStatus=claimable, workloadComparable=True, workloadComparableNow=True, workloadClaimableNow=True, delta(p50/p95/p99)=963360.9850000001/809019.3527272729/809019.3527272729, timingSources(left/right)=['doe-execution-row-total-ns']/['dawn-perf-wall-time'], backend(left/right)=doe_metal/, report=bench/out/20260301T173606Z/metal.npm.compare.json
- ctr_resource_lifecycle_contract: comparisonStatus=comparable, claimStatus=claimable, workloadComparable=True, workloadComparableNow=True, workloadClaimableNow=True, delta(p50/p95/p99)=218924.6640536842/191329.67171727272/191329.67171727272, timingSources(left/right)=['doe-execution-total-ns']/['dawn-perf-wall-time'], backend(left/right)=doe_metal/, report=bench/out/20260301T173606Z/metal.npm.compare.json
- par_uniform_buffer_update_writebuffer_partial_single: comparisonStatus=comparable, claimStatus=claimable, workloadComparable=True, workloadComparableNow=True, workloadClaimableNow=True, delta(p50/p95/p99)=221.56382151423642/199.44606105843005/199.44606105843005, timingSources(left/right)=['doe-execution-total-ns']/['dawn-perf-wall-time'], backend(left/right)=doe_metal/, report=bench/out/20260301T173606Z/metal.npm.compare.json

