"""Specific source restrictions must not be replaced by generic login advice."""
import pytest

from video_downloader import _classify_ytdlp_error


@pytest.mark.parametrize('message,code', [
    ('Video unavailable. The uploader has not made this video available in your country', 'GEO_RESTRICTED'),
    ('HTTP Error 403: This video is not available in your region', 'GEO_RESTRICTED'),
    ('Video unavailable. Blocked on copyright grounds', 'COPYRIGHT_BLOCKED'),
    ('HTTP Error 429: Too Many Requests. Sign in to confirm you are not a bot', 'RATE_LIMITED'),
    ('Private video. Sign in if you have been granted access', 'VIDEO_PRIVATE'),
    ('This video has been removed by the uploader', 'VIDEO_UNAVAILABLE'),
    ('Video unavailable', 'VIDEO_UNAVAILABLE'),
    ('Sign in to confirm your age. This video is age-restricted', 'AGE_RESTRICTED'),
])
def test_specific_youtube_failure_is_preserved(message, code):
    result = _classify_ytdlp_error(RuntimeError(message), 'youtube')
    assert result.error_code == code
    if code not in {'AGE_RESTRICTED', 'VIDEO_PRIVATE'}:
        assert 'upload your cookies' not in str(result).lower()


@pytest.mark.parametrize('platform,code', [('youtube', 'LOGIN_REQUIRED'), ('bilibili', 'BILIBILI_LOGIN_REQUIRED')])
def test_real_authentication_failures_still_recommend_login(platform, code):
    assert _classify_ytdlp_error(RuntimeError('Sign in to confirm you are not a bot'), platform).error_code == code


def test_bilibili_anti_bot_response_retains_its_existing_recovery():
    result = _classify_ytdlp_error(RuntimeError('HTTP Error 412: Precondition failed'), 'bilibili')
    assert result.error_code == 'BILIBILI_LOGIN_REQUIRED'


def test_country_in_a_title_does_not_mean_a_geographic_restriction():
    assert _classify_ytdlp_error(RuntimeError('Country music: Sign in to confirm you are not a bot'), 'youtube').error_code == 'LOGIN_REQUIRED'
