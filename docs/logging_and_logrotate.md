# Logging and Logrotate Best Practices

This guide covers persistent operational log files created by the Training ETL platform.

## Adding a New Persistent Log File

Persistent operational logs are stored under:

```text
/opt/training/logs/
```

Every new persistent `.log` file in this directory must also be added to the Training logrotate configuration:

```text
/etc/logrotate.d/training
```

An unlisted log file will not be rotated and may continue growing indefinitely.

## 1. Determine Who Writes the Log

Identify the process owner before adding a file to logrotate. Typical writers are:

- Mike's user crontab: `mike`
- Root's crontab: `root`
- Root maintenance scripts: `root`
- Docker containers: managed by Docker, not Linux logrotate

Check the current file when it exists:

```bash
ls -l /opt/training/logs/new_log.log
```

The owner determines which logrotate group should contain the file.

## 2. Add the Log to the Correct Rotation Group

Edit the Training rule:

```bash
sudoedit /etc/logrotate.d/training
```

For logs written by Mike, add the path to the block using:

```text
create 0640 mike mike
```

For logs written by root, add the path to the block using:

```text
create 0640 root mike
```

Example root-owned group:

```text
/opt/training/logs/pg_restore_test.log
/opt/training/logs/training_restore_output.log
/opt/training/logs/health_check.log
/opt/training/logs/weekly_health.log
/opt/training/logs/new_root_job.log {
    weekly
    rotate 8
    compress
    dateext
    missingok
    notifempty
    maxsize 10M
    create 0640 root mike
}
```

Example Mike-owned group:

```text
/opt/training/logs/pg_backup.log
/opt/training/logs/new_mike_job.log {
    weekly
    rotate 8
    compress
    dateext
    missingok
    notifempty
    maxsize 10M
    create 0640 mike mike
}
```

Do not combine files written by different users in one block unless the `create` ownership is correct for every file in that block.

## 3. Validate the Configuration

Run logrotate in debug mode after changing the configuration:

```bash
sudo logrotate --debug /etc/logrotate.d/training
```

Debug mode validates the configuration without rotating files or changing logrotate state. Normal messages may include:

- `log does not need rotating`
- `log does not exist -- skipping`
- `empty log files are not rotated`

Fix syntax, ownership, duplicate-pattern, and permission errors before proceeding.

## 4. Test Rotation When Needed

A forced rotation is optional, but useful after changing ownership or adding an important log:

```bash
sudo logrotate --force --verbose /etc/logrotate.d/training
```

Inspect the results:

```bash
ls -lah /opt/training/logs
ls -l /opt/training/logs/*.log
```

Expected results:

- The old log has a dated suffix and may be compressed with gzip.
- A new empty log exists.
- The new log has mode `0640`.
- The new log has the correct owner and group.

Example rotated files:

```text
health_check.log
health_check.log-20260906.gz
```

## 5. Confirm the Writer Can Still Append

For a root-owned cron log, put both the command and redirection inside `sudo bash -c`:

```bash
sudo bash -c '/opt/training/etl/example_job.py >> /opt/training/logs/new_root_job.log 2>&1'
```

For a Mike-owned cron log:

```bash
/opt/training/etl/example_job.sh >> /opt/training/logs/new_mike_job.log 2>&1
```

Confirm output was written:

```bash
tail -20 /opt/training/logs/new_mike_job.log
```

This form can fail for a root-owned log:

```bash
sudo command >> /opt/training/logs/root_owned.log
```

The current user's shell opens the log before `sudo` runs. For root-owned logs, use `sudo bash -c` so the command and redirection run with the required privileges.

## Docker Logs Are Different

Do not add Docker's internal container logs to `/etc/logrotate.d/training`.

Docker manages container stdout and stderr through its logging driver. For the `json-file` driver, a compose configuration may use:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"
```

Verify a container's Docker logging policy with:

```bash
sudo docker inspect training-web --format '{{json .HostConfig.LogConfig}}'
```

Linux logrotate manages only the explicit operational log files under `/opt/training/logs/`.

## Tools Used

- `sudoedit`: safely edit `/etc/logrotate.d/training`
- `logrotate --debug`: validate without changing files
- `logrotate --force --verbose`: perform a controlled test rotation
- `ls -l`: verify file ownership and permissions
- `tail`: verify that the responsible job can write to the log
- `systemctl`: confirm Ubuntu's automatic logrotate timer
- `docker inspect`: verify Docker-native container-log rotation

## New-Log Checklist

Whenever a new persistent log is added:

- Store it under `/opt/training/logs/`.
- Determine whether `mike` or `root` writes it.
- Add it to the correct block in `/etc/logrotate.d/training`.
- Keep mode `0640`.
- Run `sudo logrotate --debug /etc/logrotate.d/training`.
- Force a rotation only when additional validation is useful.
- Verify the replacement file's ownership.
- Confirm the originating process can append to it.
- Do not add Docker internal logs to Linux logrotate.
- Update this documentation if the retention policy changes.
