use std::{fs::File, io::ErrorKind, path::Path};

use symphonia::{
    core::{
        audio::SampleBuffer,
        codecs::DecoderOptions,
        errors::Error as SymphoniaError,
        formats::FormatOptions,
        io::MediaSourceStream,
        meta::MetadataOptions,
        probe::Hint,
    },
    default::{get_codecs, get_probe},
};

use crate::error::{AudioError, Result};

#[derive(Debug, Clone)]
pub struct DecodedAudio {
    pub channels: Vec<Vec<f32>>,
    pub sample_rate_hz: u32,
}

impl DecodedAudio {
    pub fn frames(&self) -> usize {
        self.channels.first().map_or(0, Vec::len)
    }
}

/// Decode a materialized local audio asset using Symphonia.
///
/// The `all` feature is enabled so the Rust evaluator can consume the same
/// common containers/codecs that the Python materializer may preserve,
/// including WAV, FLAC, MP3, AAC/M4A, AIFF/CAF, OGG/Vorbis and related PCM
/// formats. Unsupported codecs remain an explicit runtime error.
pub fn decode_audio(path: impl AsRef<Path>) -> Result<DecodedAudio> {
    let path = path.as_ref();
    let file = File::open(path).map_err(|error| AudioError::Decode {
        path: path.to_path_buf(),
        message: error.to_string(),
    })?;

    let stream = MediaSourceStream::new(Box::new(file), Default::default());
    let mut hint = Hint::new();
    if let Some(extension) = path.extension().and_then(|value| value.to_str()) {
        hint.with_extension(extension);
    }

    let probed = get_probe()
        .format(
            &hint,
            stream,
            &FormatOptions::default(),
            &MetadataOptions::default(),
        )
        .map_err(|error| AudioError::Decode {
            path: path.to_path_buf(),
            message: error.to_string(),
        })?;

    let mut format = probed.format;
    let track = format
        .default_track()
        .ok_or_else(|| AudioError::Unsupported("audio asset has no default track".into()))?;
    let track_id = track.id;
    let codec_params = track.codec_params.clone();
    let mut decoder = get_codecs()
        .make(&codec_params, &DecoderOptions::default())
        .map_err(|error| AudioError::Decode {
            path: path.to_path_buf(),
            message: error.to_string(),
        })?;

    let mut channels: Vec<Vec<f32>> = Vec::new();
    let mut sample_rate_hz = codec_params.sample_rate.unwrap_or(0);

    loop {
        let packet = match format.next_packet() {
            Ok(packet) => packet,
            Err(SymphoniaError::IoError(error)) if error.kind() == ErrorKind::UnexpectedEof => break,
            Err(SymphoniaError::ResetRequired) => {
                return Err(AudioError::Decode {
                    path: path.to_path_buf(),
                    message: "decoder reset required after stream parameter change".into(),
                });
            }
            Err(error) => {
                return Err(AudioError::Decode {
                    path: path.to_path_buf(),
                    message: error.to_string(),
                });
            }
        };

        if packet.track_id() != track_id {
            continue;
        }

        let decoded = match decoder.decode(&packet) {
            Ok(decoded) => decoded,
            Err(SymphoniaError::DecodeError(_)) => continue,
            Err(error) => {
                return Err(AudioError::Decode {
                    path: path.to_path_buf(),
                    message: error.to_string(),
                });
            }
        };

        let spec = *decoded.spec();
        sample_rate_hz = spec.rate;
        let channel_count = spec.channels.count();
        if channel_count == 0 {
            return Err(AudioError::Unsupported("decoded audio has zero channels".into()));
        }
        if channels.is_empty() {
            channels = (0..channel_count).map(|_| Vec::new()).collect();
        } else if channels.len() != channel_count {
            return Err(AudioError::Unsupported(
                "channel layout changed while decoding".into(),
            ));
        }

        let mut samples = SampleBuffer::<f32>::new(decoded.capacity() as u64, spec);
        samples.copy_interleaved_ref(decoded);
        for frame in samples.samples().chunks_exact(channel_count) {
            for (channel, sample) in channels.iter_mut().zip(frame.iter().copied()) {
                channel.push(sample.clamp(-1.0, 1.0));
            }
        }
    }

    if sample_rate_hz == 0 {
        return Err(AudioError::InvalidSampleRate(0));
    }
    if channels.is_empty() || channels.iter().all(Vec::is_empty) {
        return Err(AudioError::Empty);
    }

    Ok(DecodedAudio {
        channels,
        sample_rate_hz,
    })
}

/// Backwards-compatible name retained for callers written during the initial
/// WAV-only implementation.
pub fn decode_wav(path: impl AsRef<Path>) -> Result<DecodedAudio> {
    decode_audio(path)
}
