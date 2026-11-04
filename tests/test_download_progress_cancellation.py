from unittest.mock import Mock, patch
import pytest
from video_downloader import YtdlpDownloader
from summary_errors import ProcessingCancelledError


@pytest.mark.parametrize('total', [0, 1000000000])
def test_slow_download_checks_cancellation_without_waiting_for_two_percent(total):
    callback = Mock(side_effect=[None, ProcessingCancelledError('Cancelled')])
    hook = YtdlpDownloader('youtube')._make_progress_hook(callback)[0]
    with patch('time.monotonic', side_effect=[10, 10.5, 11.1]):
        hook({'status':'downloading', 'total_bytes':total, 'downloaded_bytes':100})
        hook({'status':'downloading', 'total_bytes':total, 'downloaded_bytes':200})
        assert callback.call_count == 1
        with pytest.raises(ProcessingCancelledError):
            hook({'status':'downloading', 'total_bytes':total, 'downloaded_bytes':300})
    assert callback.call_count == 2
