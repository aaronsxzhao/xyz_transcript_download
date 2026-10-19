from scripts.repair_reported_screenshots import frame_references


def test_only_reported_notes_own_frame_names_are_recreated():
    markdown = '''![Screenshot](/data/screenshots/bc2c988b-2b4_00-21.jpg)
![Screenshot](https://example.com/screenshots/bc2c988b-2b4_10-54.jpg)
![Other](/data/screenshots/another_bc2c988b-2b4_01-00.jpg)
![Other](/data/screenshots/another-task_01-00.jpg)
![Invalid](/data/screenshots/bc2c988b-2b4_01-99.jpg)'''
    assert frame_references(markdown) == {'bc2c988b-2b4_00-21.jpg': 21, 'bc2c988b-2b4_10-54.jpg': 654}
