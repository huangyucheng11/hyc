"""Select an installed game without confusing the official and channel clients."""
import re


def select_package(packages, activity_dump=''):
    packages = list(dict.fromkeys(packages))
    if len(packages) == 1:
        return packages[0]
    # Only a resumed/focused activity counts; background task history does not.
    for line in activity_dump.splitlines():
        if not any(marker in line for marker in ('topResumedActivity', 'mResumedActivity', 'mCurrentFocus')):
            continue
        for package in packages:
            if re.search(r'(?<![\w.])' + re.escape(package) + r'/', line):
                return package
    return None
