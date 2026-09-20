# Idle-window retry after Metal host validation

The preceding watcher was stopped before launching a calibration so that source
builds and tests would not overlap the frozen experiment. Its suspension receipt
is retained in `../20260920-calibration-retry-03/watch-suspended.json`.

This watcher is an unchanged copy of that scheduling script with a fresh control
directory and fresh observations. It targets the previously unused complete
`../20260920-command-storage-calibration-window-03` cohort. The launch guard checks
unchanged frozen inputs and required free space, then waits for sustained observed
GPU inactivity. The guard does not establish exclusive GPU access or change the
per-process interference rejection policy. It does not stop Doppler or Chrome.

Run from the repository root:

```bash
python3 -u -c 'import runpy; runpy.run_path("bench/out/compute-program/20260920-calibration-retry-04/watch_and_run.py", run_name="__main__")'
```

`watch.log`, `launch-guard.json`, and `watch-*.json` retain scheduling observations.
If launched, `command.json`, `execution-commit.txt`, `launch-working-tree.txt`,
`execution.log` and `execution-result.json` record the independent attempt.
Absence of `execution-result.json` is not successful calibration. No interrupted
cohort is combined with this attempt, and no candidate or accepted package is
changed.
