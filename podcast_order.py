"""Stable chapter-local ordering; citations keep their original timestamps."""
import re


def chronological_points(points):
    chapters = {}
    for point in points:
        chapters.setdefault(point.topic, []).append(point)
    result = []
    for rows in chapters.values():
        prefix, groups = [], []
        for point in rows:
            value = point.timestamp.strip().strip('[]')
            if re.fullmatch(r'\d+(?::[0-5]\d){1,2}', value):
                seconds = 0
                for part in value.split(':'):
                    seconds = seconds * 60 + int(part)
                groups.append((seconds, [point]))
            elif groups:
                groups[-1][1].append(point)
            else:
                prefix.append(point)
        result.extend(prefix)
        for _, group in sorted(groups, key=lambda group: group[0]):
            result.extend(group)
    return result
