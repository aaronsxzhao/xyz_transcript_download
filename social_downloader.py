"""Use the existing media pipeline for all ordered attachments of a social post."""
from pathlib import Path
from urllib.parse import urlsplit

from social_content import SocialContent, SocialSourceError, public_media_target, resolve_social_content
from video_downloader import YtdlpDownloader, VideoMetadata, VIDEO_AUDIO_DIR, VIDEO_DIR, FFMPEG_PATH
from resource_scheduler import run_media_process


class SocialDownloader:
    def __init__(self, source: SocialContent):
        self.source = source
        self.platform = source.platform
        self._public_source = None

    def get_metadata(self, url):
        return VideoMetadata(title=self.source.title, thumbnail=self.source.thumbnail,
            duration=sum(float(item.get('duration') or 0) for item in self.source.media),
            channel=self.source.author or self.source.platform, channel_url=self.source.author_url or self.source.url,
            published_at=self.source.published, platform=self.source.platform, url=self.source.url)

    def get_last_download_info(self):
        return self.get_metadata(self.source.url)

    def get_subtitles(self, url, task_id):
        return None

    def _download(self, task_id, video, quality, callback):
        if self.platform == 'web':
            return self._download_public_media(task_id, video, quality, callback)
        if video and any(item['kind'] != 'video' for item in self.source.media):
            return None  # Audio posts do not pretend to have screenshots.
        paths = []
        for index, item in enumerate(self.source.media):
            host = urlsplit(item['url']).hostname or ''
            custom = self.platform == 'substack' and host == urlsplit(self.source.url).hostname and host != 'substack.com' and not host.endswith('.substack.com')
            name = task_id if len(self.source.media)==1 else f'{task_id}_part{index}'
            progress = (lambda value, message, i=index: callback((i+value)/len(self.source.media), message)) if callback else None
            if custom:
                safe = SocialDownloader(SocialContent('web', self.source.url, self.source.title, self.source.body, media=[item]))
                try: paths.append(safe._download_public_media(name, video, quality, progress))
                finally: safe.cleanup()
                continue
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

    def _download_public_media(self, task_id, video, quality, callback):
        """Generic media never hands an arbitrary remote URL to yt-dlp/FFmpeg."""
        import hashlib
        import time
        from public_content_fetch import fetch_public
        item = self.source.media[0]
        if video and item['kind'] != 'video': return None
        root = VIDEO_DIR if video else VIDEO_AUDIO_DIR
        root.mkdir(parents=True, exist_ok=True)
        ident = hashlib.sha256(item['url'].encode()).hexdigest()[:16]
        original = VIDEO_AUDIO_DIR / f'{task_id}_{ident}_source.media'
        VIDEO_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        if callback: callback(0, 'Downloading original media…')
        downloaded = self._public_source == original and original.exists()
        self._public_source = original
        if not downloaded:
            temporary = original.with_suffix('.part')
            def progress(size, total):
                if callback:
                    # Unknown sizes stay indeterminate; callbacks also check
                    # cancellation on every streamed block.
                    ratio = min(size / total, 1) if total > 0 else 0
                    callback(.75 * ratio, f'Downloading original media — {size / 1048576:.1f} MB')
            try:
                with temporary.open('wb') as stream:
                    response = fetch_public(item['url'], deadline=time.monotonic()+180, max_bytes=1024*1024*1024, sink=stream, progress_callback=progress)
                if response.content_type not in {'audio/mpeg','audio/mp3','audio/mp4','audio/x-m4a','audio/wav','audio/x-wav','audio/flac','audio/ogg','audio/aac','audio/webm','video/mp4','video/quicktime','video/webm','video/x-matroska','video/x-msvideo'}:
                    raise SocialSourceError('This media format requires a dedicated provider adapter. Use a direct MP4/MP3/WAV/WebM file or upload the recording.')
                if not temporary.stat().st_size: raise SocialSourceError('The original media file was empty.')
                temporary.replace(original)
                self._public_source = original
            finally:
                temporary.unlink(missing_ok=True)
        if callback: callback(.8, 'Preparing original media…')
        target = root / (task_id + ('.mp4' if video else '.mp3'))
        args = [FFMPEG_PATH,'-y','-protocol_whitelist','file,pipe',
                '-format_whitelist','mov,mp4,mp3,wav,flac,ogg,aac,matroska,webm,avi','-i',str(original)]
        if video:
            args += ['-an','-c:v','libx264','-preset','veryfast']
            if str(quality) in ('360','480','720','1080'):
                args += ['-vf', f'scale=-2:min({quality}\\,ih)']
        else:
            args += ['-vn','-c:a','libmp3lame','-b:a',{'fast':'32k','medium':'64k','slow':'128k'}.get(quality,'64k')]
        run_media_process([*args,str(target)],capture_output=True,check=True,timeout=600)
        if callback: callback(1, 'Original media ready')
        return target

    def cleanup(self):
        if self._public_source:
            self._public_source.unlink(missing_ok=True)
            self._public_source = None

    def download_audio(self,url,task_id,quality='medium',progress_callback=None):
        return self._download(task_id,False,quality,progress_callback)

    def download_video(self,url,task_id,video_quality='720',progress_callback=None):
        return self._download(task_id,True,video_quality,progress_callback)


class SocialLinkDownloader:
    """Resolve on demand for screenshot recovery and other existing URL tools."""
    def __init__(self, platform=''):
        self.downloader=None
        self.platform=platform

    def _source(self,url):
        if self.downloader is None:
            if self.platform == 'web':
                from content_sources import resolve_content
                source = resolve_content(url)
            else:
                source = resolve_social_content(url)
            self.downloader=SocialDownloader(source)
        return self.downloader

    def get_metadata(self,url):return self._source(url).get_metadata(url)
    def get_subtitles(self,url,task_id):return None
    def get_last_download_info(self):return self.downloader.get_last_download_info() if self.downloader else None
    def cleanup(self):
        if self.downloader: self.downloader.cleanup()
    def download_audio(self,url,task_id,quality='medium',progress_callback=None):
        return self._source(url).download_audio(url,task_id,quality,progress_callback)
    def download_video(self,url,task_id,video_quality='720',progress_callback=None):
        return self._source(url).download_video(url,task_id,video_quality,progress_callback)
