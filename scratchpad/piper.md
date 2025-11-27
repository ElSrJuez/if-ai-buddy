Install with:

``` sh
pip install piper-tts
```

Download a voice, for example:

``` sh
python3 -m piper.download_voices en_US-lessac-medium
```

Use `PiperVoice.synthesize_wav`:

``` python
import wave
from piper import PiperVoice

voice = PiperVoice.load("/path/to/en_US-lessac-medium.onnx")
with wave.open("test.wav", "wb") as wav_file:
    voice.synthesize_wav("Welcome to the world of speech synthesis!", wav_file)
```

Adjust synthesis:

``` python
syn_config = SynthesisConfig(
    volume=0.5,  # half as loud
    length_scale=2.0,  # twice as slow
    noise_scale=1.0,  # more audio variation
    noise_w_scale=1.0,  # more speaking variation
    normalize_audio=False, # use raw audio from voice
)

voice.synthesize_wav(..., syn_config=syn_config)
```

To use CUDA for GPU acceleration:

``` python
voice = PiperVoice.load(..., use_cuda=True)
```

This requires the `onnxruntime-gpu` package to be installed.

For streaming, use `PiperVoice.synthesize`:

``` python
for chunk in voice.synthesize("..."):
    set_audio_format(chunk.sample_rate, chunk.sample_width, chunk.sample_channels)
    write_raw_data(chunk.audio_int16_bytes)
```

Using the Python API
Relevant source files
This page documents how to use Piper's Python API for integrating text-to-speech functionality into Python applications. The Python API provides a convenient wrapper around Piper's core C++ TTS engine, allowing Python developers to easily synthesize speech from text. For information about the HTTP API, see HTTP Server.

Installation
The Piper Python API can be installed using pip:

pip install piper-tts
For GPU acceleration using CUDA, install with:

pip install -f https://synesthesiam.github.io/prebuilt-apps/ -r requirements_gpu.txt
pip install piper-tts
Sources: 
src/python_run/requirements_gpu.txt
1-2

API Overview
The PiperVoice class is the main interface for Piper's Python API. It encapsulates an ONNX model session and the associated configuration, providing methods for text-to-speech synthesis.

Sources: 
src/python_run/piper/__init__.py
1-5
 
src/python_run/piper/voice.py
19-185
 
src/python_run/piper/config.py
7-53

Basic Usage
Loading a Voice Model
from piper import PiperVoice

# Load a voice model
voice = PiperVoice.load(
    model_path="path/to/model.onnx",
    config_path=None,  # Will use model_path + .json if None
    use_cuda=False     # Set to True for GPU acceleration
)
The load method loads an ONNX model and its configuration. If config_path is not provided, it will look for a JSON file with the same name as the model file (with .json extension).

Sources: 
src/python_run/piper/voice.py
24-55

Synthesizing Speech to a WAV File
import wave

# Create a WAV file
with wave.open("output.wav", "wb") as wav_file:
    # Synthesize speech directly to the WAV file
    voice.synthesize(
        text="Hello, world!",
        wav_file=wav_file,
        speaker_id=None,  # Optional: speaker ID for multi-speaker models
        length_scale=None,  # Optional: controls speech speed (lower = faster)
        noise_scale=None,   # Optional: controls variability in speech
        noise_w=None,       # Optional: controls phoneme duration variability
        sentence_silence=0.0  # Optional: silence between sentences in seconds
    )
The synthesize method generates speech from the provided text and writes it directly to a WAV file.

Sources: 
src/python_run/piper/voice.py
89-112

TTS Data Flow


















This diagram illustrates the data flow during text-to-speech synthesis, from input text to output audio.

Sources: 
src/python_run/piper/voice.py
57-185

Advanced Usage
Streaming Audio Generation
For applications that need to process audio in chunks or deliver it incrementally, the synthesize_stream_raw method provides a streaming interface:

# Generate raw audio bytes per sentence
for audio_bytes in voice.synthesize_stream_raw(
    text="This is the first sentence. This is the second sentence.",
    speaker_id=None,
    length_scale=None,
    noise_scale=None,
    noise_w=None,
    sentence_silence=0.2  # 200ms silence between sentences
):
    # Process audio_bytes as needed
    # Each chunk is one complete sentence
    process_audio_chunk(audio_bytes)
The method yields raw audio bytes for each sentence in the input text, allowing for sentence-by-sentence processing.

Sources: 
src/python_run/piper/voice.py
114-138

Controlling Synthesis Parameters
Piper provides several parameters to control the quality and characteristics of the synthesized speech:

Parameter	Description	Default
speaker_id	Speaker ID for multi-speaker models	0
length_scale	Controls speech speed (lower = faster)	From config
noise_scale	Controls variability in speech	From config
noise_w	Controls phoneme duration variability	From config
sentence_silence	Silence between sentences in seconds	0.0
These parameters can be adjusted to customize the output speech:

# Synthesize with custom parameters
voice.synthesize(
    text="Custom speed and variability.",
    wav_file=wav_file,
    speaker_id=1,          # Use speaker ID 1 for multi-speaker models
    length_scale=0.8,      # Faster speech
    noise_scale=0.6,       # Less variability
    noise_w=0.7,           # Less duration variability
    sentence_silence=0.1   # 100ms silence between sentences
)
Sources: 
src/python_run/piper/voice.py
89-112
 
src/python_run/piper/voice.py
140-185

Low-Level Phoneme Processing
For more advanced control, Piper allows direct manipulation of phonemes:

# Get phonemes for text
sentence_phonemes = voice.phonemize("Hello, world!")

# Convert phonemes to IDs for specific sentence
phoneme_ids = voice.phonemes_to_ids(sentence_phonemes[0])

# Synthesize directly from phoneme IDs
audio_bytes = voice.synthesize_ids_to_raw(
    phoneme_ids,
    speaker_id=None,
    length_scale=None,
    noise_scale=None,
    noise_w=None
)
This allows for more precise control over the phonetic representation used for synthesis.

Sources: 
src/python_run/piper/voice.py
57-87
 
src/python_run/piper/voice.py
140-185

GPU Acceleration
Piper supports GPU acceleration using ONNX Runtime's CUDA execution provider:

# Load a voice model with GPU acceleration
voice = PiperVoice.load(
    model_path="path/to/model.onnx",
    config_path=None,
    use_cuda=True  # Enable CUDA
)
When use_cuda is set to True, the ONNX model will use the CUDA execution provider with optimized settings for neural text-to-speech.

Sources: 
src/python_run/piper/voice.py
24-55

Error Handling
Common errors when using the Python API include:

Missing phonemes: If a phoneme is not in the model's phoneme map, a warning will be logged, and the phoneme will be skipped. This can happen with unusual characters or symbols not covered in the model's training data.

Model loading errors: If the ONNX model or configuration file is not found or is invalid, an exception will be raised during the loading process.

Unsupported phoneme types: If the configured phoneme type is not supported, a ValueError will be raised.

Example error handling:

try:
    voice = PiperVoice.load("path/to/model.onnx")
    with wave.open("output.wav", "wb") as wav_file:
        voice.synthesize("Hello, world!", wav_file)
except FileNotFoundError:
    print("Model or config file not found")
except ValueError as e:
    print(f"Configuration error: {e}")
except Exception as e:
    print(f"Synthesis error: {e}")
Sources: 
src/python_run/piper/voice.py
57-70
 
src/python_run/piper/voice.py
72-87

Practical Example
Here's a complete example that demonstrates loading a voice model and synthesizing speech:

from piper import PiperVoice
import wave

# Load the voice model
voice = PiperVoice.load(
    model_path="path/to/model.onnx",
    config_path=None,
    use_cuda=False
)

# Create a WAV file
with wave.open("output.wav", "wb") as wav_file:
    # Synthesize speech
    voice.synthesize(
        text="Hello! This is Piper text-to-speech. It sounds quite natural.",
        wav_file=wav_file,
        speaker_id=None,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w=0.8,
        sentence_silence=0.2
    )

print("Speech synthesis complete. Output saved to output.wav.")
Sources: 
src/python_run/piper/voice.py
19-185