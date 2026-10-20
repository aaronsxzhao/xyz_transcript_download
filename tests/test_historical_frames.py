"""Historical repairs are additive and limited to the owning task's frames."""
from scripts.recover_library_media import task_frames


def test_repair_includes_versions_and_deduplicates_current_frames():
    task = {'id': 'owned-task', 'markdown': '![current](/data/screenshots/owned-task_01-00.jpg)'}
    versions = ['![old](/data/screenshots/owned-task_00-30.jpg)\n![same](/data/screenshots/owned-task_01-00.jpg)',
                '![other](/data/screenshots/another-task_02-00.jpg)']
    assert task_frames(task, versions) == {'owned-task_00-30.jpg': 30, 'owned-task_01-00.jpg': 60}
