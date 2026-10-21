"""Source access is separate from transcription/summary processing status."""
import hashlib

# Shared public placeholder verified to contain only ten seconds of audio.
# Its fingerprint is not an episode ID, account credential or playable content.
RESTRICTED_AUDIO = {'bcf7e172098ce346eb2ebd141e20e27a'}
MESSAGES = {
    'purchase_required': 'Purchase required on Xiaoyuzhou. This website currently receives only a short placeholder. Open the original episode to check access, or upload the complete audio.',
    'login_required': 'The source requires a signed-in account. Check source access or upload the complete audio.',
    'restricted': 'The source provides only restricted or placeholder audio. It may require purchase or sign-in. Open the original episode to check access.',
    'unavailable': 'The original audio is unavailable. Restore the source or upload the complete audio.',
}


def source_status(audio_url: str, declared: str = 'unknown') -> str:
    if declared in MESSAGES:
        return declared
    url = (audio_url or '').split('?',1)[0].split('#',1)[0]
    if hashlib.md5(url.encode()).hexdigest() in RESTRICTED_AUDIO:
        return 'restricted'
    return 'available' if declared == 'available' else 'unknown'


def source_message(status: str) -> str:
    return MESSAGES.get(status,'')
