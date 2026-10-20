"""Prepared NVIDIA Whisper client. Runs only when explicitly invoked."""
import argparse
import importlib.metadata
from pathlib import Path
import wave

SERVER = 'grpc.nvcf.nvidia.com:443'
FUNCTION_ID = 'b702f636-f60c-4a3d-a6f4-f3568c13bd7d'


def transcribe(path, language='multi', timeout=180):
    import grpc
    import riva.client
    from riva.client.proto import riva_asr_pb2, riva_asr_pb2_grpc
    from studio_script_nvidia import nvidia_token
    token = nvidia_token('RIVA_API_KEY')
    if not token:
        raise ValueError('Set RIVA_API_KEY in .env or the environment.')
    path = Path(path)
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError('Use a WAV file smaller than 25 MB.')
    with wave.open(str(path), 'rb') as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
            raise ValueError('Use mono, uncompressed 16-bit PCM WAV audio.')
        rate = audio.getframerate()
        data = audio.readframes(audio.getnframes())
    config = riva.client.RecognitionConfig(
        encoding=riva.client.AudioEncoding.LINEAR_PCM,
        sample_rate_hertz=rate, language_code=language,
        max_alternatives=1, enable_automatic_punctuation=True,
    )
    # Explicit deadline; no automatic transcription or unbounded SDK call.
    with grpc.secure_channel(SERVER, grpc.ssl_channel_credentials()) as channel:
        service = riva_asr_pb2_grpc.RivaSpeechRecognitionStub(channel)
        response = service.Recognize(
            riva_asr_pb2.RecognizeRequest(config=config, audio=data),
            metadata=[('function-id', FUNCTION_ID), ('authorization', 'Bearer ' + token)],
            timeout=timeout,
        )
    return ' '.join(result.alternatives[0].transcript for result in response.results if result.alternatives)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify installation/configuration without making an API call.')
    parser.add_argument('--input-file', type=Path)
    parser.add_argument('--language-code', default='multi', help='multi, en, hi, or another Whisper language code')
    args = parser.parse_args()
    if args.check:
        import riva.client
        from studio_script_nvidia import nvidia_token
        print('Riva client:', importlib.metadata.version('nvidia-riva-client'))
        print('Whisper key configured:', bool(nvidia_token('RIVA_API_KEY')))
        print('Ready for explicit use; no API request made.')
        return
    if not args.input_file:
        parser.error('Provide --input-file or --check.')
    try:
        print(transcribe(args.input_file, args.language_code))
    except Exception as exc:
        # Upstream errors can include request metadata; do not print credentials.
        from studio_script_nvidia import nvidia_token
        message = str(exc).replace(nvidia_token('RIVA_API_KEY') or '\0', '[redacted]')
        parser.exit(1, 'Transcription failed: ' + message + '\n')


if __name__ == '__main__':
    main()
