"""Use the existing media pipeline for all ordered attachments of a social post."""
from pathlib import Path

from social_content import SocialContent, SocialSourceError, public_media_target, resolve_social_content
from video_downloader import YtdlpDownloader, VideoMetadata, VIDEO_AUDIO_DIR, VIDEO_DIR, FFMPEG_PATH
from resource_scheduler import run_media_process


class SocialDownloader:
    def __init__(self, source: SocialContent):
        self.source = source
        self.platform = source.platform

    def get_metadata(self, url):
        return VideoMetadata(title=self.source.title, thumbnail=self.source.thumbnail,
            duration=sum(float(item.get('duration') or 0) for item in self.source.media),
            channel=self.source.author or self.source.platform, channel_url=self.source.url,
            published_at=self.source.published, platform=self.source.platform, url=self.source.url)

    def get_last_download_info(self):
        return self.get_metadata(self.source.url)

    def get_subtitles(self, url, task_id):
        return None

    def _download(self, task_id, video, quality, callback):
        if video and any(item['kind'] != 'video' for item in self.source.media):
            return None  # Audio posts do not pretend to have screenshots.
        paths = []
        for index, item in enumerate(self.source.media):
            target_url=public_media_target(item['url'])
            downloader = YtdlpDownloader(self.platform,use_saved_cookies=False)
            # The resolved media URL uses yt-dlp's direct-media extractor. Source
            # IDs remain on the task; attachments never replace its source URL.
            progress = (lambda value, message, i=index: callback((i+value)/len(self.source.media), message)) if callback else None
            name = task_id if len(self.source.media)==1 else f'{task_id}_part{index}'
            path = downloader.download_video(target_url,name,video_quality=quality,progress_callback=progress) if video else downloader.download_audio(target_url,name,quality,progress_callback=progress)
            if not path: raise SocialSourceError(f'Attachment {index+1} could not be downloaded. No later attachment was silently skipped.')
            paths.append(Path(path))
        if len(paths)==1:return paths[0]
        if not paths: raise SocialSourceError('No downloadable attachment was returned by the source.')
        root=VIDEO_DIR if video else VIDEO_AUDIO_DIR
        if video:
            normalized=[]
            for index,path in enumerate(paths):
                target=root/f'{task_id}_normalized{index}.mp4'
                run_media_process([FFMPEG_PATH,'-y','-i',str(path),'-vf','scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25',
                    '-an','-c:v','libx264','-preset','veryfast',str(target)],capture_output=True,check=True,timeout=600)
                normalized.append(target)
            paths=normalized
        listing=root/f'{task_id}_concat.txt'
        listing.write_text(''.join("file '"+str(path.resolve()).replace("'","'\\''")+"'\n" for path in paths),encoding='utf-8')
        target=root/f'{task_id}{".mp4" if video else ".mp3"}'
        try:
            run_media_process([FFMPEG_PATH,'-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(target)],capture_output=True,check=True,timeout=600)
        finally: listing.unlink(missing_ok=True)
        return target

    def download_audio(self,url,task_id,quality='medium',progress_callback=None):
        return self._download(task_id,False,quality,progress_callback)

    def download_video(self,url,task_id,video_quality='720',progress_callback=None):
        return self._download(task_id,True,video_quality,progress_callback)


class SocialLinkDownloader:
    """Resolve on demand for screenshot recovery and other existing URL tools."""
    def __init__(self):
        self.downloader=None

    def _source(self,url):
        if self.downloader is None:self.downloader=SocialDownloader(resolve_social_content(url))
        return self.downloader

    def get_metadata(self,url):return self._source(url).get_metadata(url)
    def get_subtitles(self,url,task_id):return None
    def get_last_download_info(self):return self.downloader.get_last_download_info() if self.downloader else None
    def download_audio(self,url,task_id,quality='medium',progress_callback=None):
        return self._source(url).download_audio(url,task_id,quality,progress_callback)
    def download_video(self,url,task_id,video_quality='720',progress_callback=None):
        return self._source(url).download_video(url,task_id,video_quality,progress_callback)
