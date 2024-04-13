## Subtitle Translator

### What's this?

subtrans can help you to extract embedded subtitle from movies or TV series and use OpenAI API to translate from any language to your native language. Or translate srt file directly.

### Requirements

- Python
- FFmpeg, FFprobe
- [OpenAI API Key](https://platform.openai.com/api-keys)
- poetry (Optional)

### Usage

```bash
export OPENAI_API_KEY=your_api_key # optional. you can input in next step
python subtrans.py -f video_or_srt_file
```

run `python subtrans.py -h` to get more details.
