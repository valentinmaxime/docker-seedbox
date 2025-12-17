#!/bin/sh

# Path to log file
LOG_FILE=/logs/cleanup.log
mkdir -p "$(dirname "$LOG_FILE")"

while true; do
  TS="$(date +%Y-%m-%d\ %H:%M:%S)"

  # Delete old files in /downloads and log each deletion
  find /downloads \
    -path "*/.stfolder" -prune -o \
    -type f -mtime +7 \
    ! -name ".keep" \
    -print -delete \
    | while read f; do
        echo "$TS DELETE $f" >> "$LOG_FILE"
      done

  # Delete empty directories in /downloads (except base and .stfolder)
  find /downloads \
    -path "*/.stfolder" -prune -o \
    -type d -empty \
    ! -path /downloads \
    -print -delete \
    | while read d; do
        echo "$TS RMDIR $d" >> "$LOG_FILE"
      done

  # Delete old files in /media and log each deletion
  find /media \
    -path "*/.stfolder" -prune -o \
    -type f -mtime +7 \
    ! -name ".keep" \
    ! -name ".sync*" \
    -print -delete \
    | while read f; do
        echo "$TS DELETE $f" >> "$LOG_FILE"
      done

  # Delete empty directories in /media (except base, .sync, movies, tv)
  find /media \
    -path "*/.stfolder" -prune -o \
    -path "/media/movies" -prune -o \
    -path "/media/tv" -prune -o \
    -type d -empty \
    ! -path /media \
    ! -name ".sync" \
    -print -delete \
    | while read d; do
        echo "$TS RMDIR $d" >> "$LOG_FILE"
      done

  # Wait 24 hours before next cleanup
  sleep 24h
done
