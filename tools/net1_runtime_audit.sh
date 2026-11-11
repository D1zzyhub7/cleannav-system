#!/usr/bin/env bash
# READ-ONLY NET-1 AUDIT. This script only queries host and ROS state.
set -u
printf '%s\n' 'READ-ONLY NET-1 AUDIT'
printf 'hostname: '; hostname 2>/dev/null || true
printf '%s\n' 'OS:'
if [ -r /etc/os-release ]; then sed -n '1,8p' /etc/os-release; else uname -a; fi
printf 'ROS_DISTRO environment: %s\n' "${ROS_DISTRO:-UNSET}"
if [ -d /opt/ros ]; then printf 'Installed ROS distributions: '; find /opt/ros -mindepth 1 -maxdepth 1 -type d -printf '%f ' 2>/dev/null; printf '\n'; else printf 'Installed ROS distributions: none found under /opt/ros\n'; fi
if command -v rosversion >/dev/null 2>&1; then printf 'ROS1 distro: '; rosversion -d 2>/dev/null || true; fi
printf '%s\n' 'ip -br link:'; ip -br link 2>&1 || true
printf '%s\n' 'ip -br addr:'; ip -br addr 2>&1 || true
printf '%s\n' 'ip route:'; ip route 2>&1 || true
printf '%s\n' 'ip neigh:'; ip neigh 2>&1 || true
printf '%s\n' 'ss -lunp:'; ss -lunp 2>&1 || true
if command -v rosnode >/dev/null 2>&1 && command -v rostopic >/dev/null 2>&1 && command -v rosparam >/dev/null 2>&1; then
  printf '%s\n' 'ROS1 nodes:'; rosnode list 2>&1 || true
  printf '%s\n' 'ROS1 topics:'; rostopic list 2>&1 || true
  printf '%s\n' 'ROS1 topic info /vehicle_cmd:'; rostopic info /vehicle_cmd 2>&1 || true
  printf '%s\n' 'ROS1 topic info /vehicle_velocity:'; rostopic info /vehicle_velocity 2>&1 || true
  printf '%s\n' 'ROS1 topic info /can_info:'; rostopic info /can_info 2>&1 || true
  printf '%s\n' 'ROS1 xsugv parameters:'
  found=0
  while IFS= read -r parameter; do
    case "$parameter" in *xsugv*|*XSUGV*) found=1; printf '%s\n' "$parameter"; rosparam get "$parameter" 2>&1 || true;; esac
  done < <(rosparam list 2>/dev/null || true)
  if [ "$found" -eq 0 ]; then printf '%s\n' 'No xsugv-named parameters found.'; fi
else
  printf '%s\n' 'ROS1 tools unavailable; ROS1 graph and parameters were not queried.'
fi
